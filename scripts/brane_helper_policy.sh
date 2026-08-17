#!/usr/bin/env bash
# =============================================================
# brane_helper_policy.sh
# Version : 2.1.0
# Date    : 2026-08-17
# Desc    : Brane helper for domain policy managers.
#           Covers adding and activating eFLINT policies
#           on a worker domain node via SSH.
# Usage   : bash scripts/brane_helper_policy.sh
#           (or via brane_main.sh → option 3)
#
# Assumptions:
#   • SSH access to the worker node is already configured
#   • Policy expert token is stored in policy_tokens/<file>.json
#   • branectl is available on the worker node
#   • Ansible inventory at docker-deployment/inventories/production/hosts.ini
# =============================================================

set -o nounset
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${SCRIPT_DIR}/brane_lib.sh"
load_config_soft "${SCRIPT_DIR}"

TOKEN_DIR="${REPO_ROOT}/policy_tokens"
REMOTE_WORK_DIR="/tmp/brane_policy"

# ==========================================
# INVENTORY PARSER
# Reads hosts.ini without requiring ansible CLI.
# ==========================================

# Parse hosts.ini and extract all worker node hostnames/IPs.
# Looks for lines under [workers] that are not comments or group headers.
# Sets INV_WORKER_HOSTS array and INV_SSH_USER.
_parse_inventory() {
    INV_WORKER_HOSTS=()
    INV_CENTRAL_HOST=""
    INV_SSH_USER="${WORKER_SSH_USER:-${USER}}"

    if [[ ! -f "${ANSIBLE_INVENTORY}" ]]; then
        return 1
    fi

    local in_workers=0 in_central=0

    while IFS= read -r line; do
        # Skip blank lines and comments
        [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue

        # Detect group headers
        if [[ "${line}" =~ ^\[workers\] ]]; then
            in_workers=1; in_central=0; continue
        elif [[ "${line}" =~ ^\[central\] ]]; then
            in_central=1; in_workers=0; continue
        elif [[ "${line}" =~ ^\[ ]]; then
            in_workers=0; in_central=0; continue
        fi

        # Extract ansible_host value from the line
        local host=""
        if [[ "${line}" =~ ansible_host=([^[:space:]]+) ]]; then
            host="${BASH_REMATCH[1]}"
        else
            # First token is the hostname/IP if no ansible_host= key
            host=$(printf '%s' "${line}" | awk '{print $1}')
        fi

        # Extract ansible_user if present
        if [[ "${line}" =~ ansible_user=([^[:space:]]+) ]]; then
            INV_SSH_USER="${BASH_REMATCH[1]}"
        fi

        [[ -z "${host}" ]] && continue

        if [[ "${in_workers}" -eq 1 ]]; then
            INV_WORKER_HOSTS+=("${host}")
        elif [[ "${in_central}" -eq 1 && -z "${INV_CENTRAL_HOST}" ]]; then
            INV_CENTRAL_HOST="${host}"
        fi
    done < "${ANSIBLE_INVENTORY}"

    return 0
}

# Pick a worker node interactively from inventory + free-text fallback.
# Sets: WORKER_HOST
_pick_worker_host() {
    _parse_inventory

    local options=()

    if [[ "${#INV_WORKER_HOSTS[@]}" -gt 0 ]]; then
        printf '  Worker nodes from inventory (%s):\n\n' "${ANSIBLE_INVENTORY}"
        local idx=0
        while [[ $idx -lt ${#INV_WORKER_HOSTS[@]} ]]; do
            printf '    [%d] %s\n' "$((idx+1))" "${INV_WORKER_HOSTS[$idx]}"
            options+=("${INV_WORKER_HOSTS[$idx]}")
            idx=$((idx+1))
        done
        printf '\n'
        read -r -p "  Select number or type a hostname/IP: " choice
        if [[ "${choice}" =~ ^[0-9]+$ ]] && \
           [[ "${choice}" -ge 1 ]] && \
           [[ "${choice}" -le "${#options[@]}" ]]; then
            WORKER_HOST="${options[$((choice-1))]}"
        else
            WORKER_HOST="${choice}"
        fi
    else
        log_warn "No worker nodes found in inventory (or inventory not found)."
        read -r -p "  Worker node IP or hostname [${WORKER_NODE_IP:-}]: " input_host
        WORKER_HOST="${input_host:-${WORKER_NODE_IP:-}}"
    fi

    [[ -z "${WORKER_HOST}" ]] && { log_error "Worker host required."; return 1; }
    return 0
}

# ==========================================
# TOKEN HELPERS
# ==========================================

_list_tokens() {
    local found=0
    while IFS= read -r f; do
        printf '    • %s\n' "$(basename "${f}")"
        found=1
    done < <(find "${TOKEN_DIR}" -maxdepth 1 -name "*.json" -type f 2>/dev/null | sort)
    [[ "${found}" -eq 0 ]] && printf '    (none)\n'
}

# Pick a token file; sets SEL_TOKEN_PATH
_pick_token() {
    local files=()
    while IFS= read -r f; do
        files+=("${f}")
    done < <(find "${TOKEN_DIR}" -maxdepth 1 -name "*.json" -type f 2>/dev/null | sort)

    if [[ "${#files[@]}" -eq 0 ]]; then
        log_error "No token files found in ${TOKEN_DIR}"
        log_error "Ask your Brane admin for a policy expert token (.json)."
        return 1
    fi

    if [[ "${#files[@]}" -eq 1 ]]; then
        SEL_TOKEN_PATH="${files[0]}"
        log_info "Using token: $(basename "${SEL_TOKEN_PATH}")"
        return 0
    fi

    printf '  Available tokens in policy_tokens/:\n\n'
    local idx=0
    while [[ $idx -lt ${#files[@]} ]]; do
        printf '    [%d] %s\n' "$((idx+1))" "$(basename "${files[$idx]}")"
        idx=$((idx+1))
    done
    printf '\n'

    local choice
    while true; do
        read -r -p "  Select token [1-${#files[@]}]: " choice
        [[ "${choice}" =~ ^[0-9]+$ ]] && \
            [[ "${choice}" -ge 1 ]] && \
            [[ "${choice}" -le "${#files[@]}" ]] && break
        log_error "Invalid choice."
    done
    SEL_TOKEN_PATH="${files[$((choice-1))]}"
}

# Extract raw JWT string from a token JSON file
_read_token() {
    local path="$1"
    python3 -c "
import json, sys
try:
    data = json.load(open('${path}'))
    token = data.get('token') or data.get('access_token') or list(data.values())[0]
    print(token.strip())
except Exception:
    print(open('${path}').read().strip())
" 2>/dev/null
}

# Check and print token expiry
_check_token_expiry() {
    local path="$1"
    local result
    result=$(python3 -c "
import json, time, base64 as b64
try:
    data = json.load(open('${path}'))
    token = data.get('token') or data.get('access_token') or list(data.values())[0]
    payload = token.split('.')[1]
    payload += '=' * (4 - len(payload) % 4)
    claims = json.loads(b64.urlsafe_b64decode(payload))
    exp = claims.get('exp', 0)
    remaining = exp - time.time()
    if remaining <= 0:
        print('EXPIRED')
    else:
        days = int(remaining // 86400)
        hours = int((remaining % 86400) // 3600)
        print('VALID:' + str(days) + 'd ' + str(hours) + 'h')
except Exception as e:
    print('ERROR:' + str(e))
" 2>/dev/null)

    case "${result}" in
        VALID:*)  log_success "Token valid — expires in ${result#VALID:}"; return 0 ;;
        EXPIRED)  log_error   "Token EXPIRED. Request a new one from your Brane admin."; return 1 ;;
        ERROR:*)  log_warn    "Could not parse expiry: ${result#ERROR:}"; return 0 ;;
        *)        log_warn    "Could not determine token expiry."; return 0 ;;
    esac
}

# ==========================================
# CONNECTION PROMPT
# Sets: WORKER_HOST, WORKER_USER, WORKER_PORT
# ==========================================

_get_worker_connection() {
    printf '\n'
    _pick_worker_host || return 1

    # SSH user — prefer inventory value, then config, then $USER
    _parse_inventory
    local default_user="${INV_SSH_USER:-${WORKER_SSH_USER:-${USER}}}"
    read -r -p "  SSH user [${default_user}]: " input_user
    WORKER_USER="${input_user:-${default_user}}"

    read -r -p "  brane-chk port [${PORT_CHK}]: " input_port
    WORKER_PORT="${input_port:-${PORT_CHK}}"
}

# ==========================================
# 1. CHECK ENVIRONMENT & REPORT
# ==========================================

check_environment() {
    clear
    section_header "Policy Manager — Environment"

    # ── Tools ─────────────────────────────────────────────
    printf '  %sRequired tools%s\n\n' "${BOLD}" "${NC}"
    check_bin "ssh"     "SSH client required."
    check_bin "scp"     "SCP required (bundled with SSH)."
    check_bin "python3" "Required for token parsing."
    printf '\n'

    # ── Inventory ─────────────────────────────────────────
    printf '  %sInventory%s  (%s)\n\n' "${BOLD}" "${NC}" "${ANSIBLE_INVENTORY}"
    if [[ -f "${ANSIBLE_INVENTORY}" ]]; then
        _parse_inventory
        printf '  %s✓%s hosts.ini found\n' "${GREEN}" "${NC}"
        if [[ -n "${INV_CENTRAL_HOST}" ]]; then
            printf '      Central : %s\n' "${INV_CENTRAL_HOST}"
        fi
        if [[ "${#INV_WORKER_HOSTS[@]}" -gt 0 ]]; then
            printf '      Workers :\n'
            for h in "${INV_WORKER_HOSTS[@]}"; do
                printf '        • %s\n' "${h}"
            done
        else
            printf '      Workers : (none found)\n'
        fi
        printf '      SSH user: %s\n' "${INV_SSH_USER}"
    else
        printf '  %s✗%s hosts.ini not found: %s\n' "${RED}" "${NC}" "${ANSIBLE_INVENTORY}"
        log_warn "Worker nodes will need to be entered manually."
    fi
    printf '\n'

    # ── Token directory ───────────────────────────────────
    printf '  %sPolicy tokens%s  (%s)\n\n' "${BOLD}" "${NC}" "${TOKEN_DIR}"
    if [[ -d "${TOKEN_DIR}" ]]; then
        printf '  %s✓%s policy_tokens/\n' "${GREEN}" "${NC}"
        _list_tokens
    else
        printf '  %s✗%s policy_tokens/  not found\n' "${RED}" "${NC}"
        printf '\n'
        read -r -p "  Create it now? [Y/n]: " yn
        if [[ "${yn}" != "n" && "${yn}" != "N" ]]; then
            mkdir -p "${TOKEN_DIR}"
            log_success "Created: ${TOKEN_DIR}"
            printf '  → Place your policy_token.json file inside it.\n'
        fi
    fi
    printf '\n'

    # ── Token validity ────────────────────────────────────
    printf '  %sToken validity%s\n\n' "${BOLD}" "${NC}"
    if [[ -d "${TOKEN_DIR}" ]]; then
        local found=0
        while IFS= read -r f; do
            printf '  Checking: %s\n' "$(basename "${f}")"
            _check_token_expiry "${f}"
            found=1
        done < <(find "${TOKEN_DIR}" -maxdepth 1 -name "*.json" -type f 2>/dev/null | sort)
        [[ "${found}" -eq 0 ]] && log_warn "No token files found."
    else
        log_warn "policy_tokens/ does not exist."
    fi
    printf '\n'

    # ── SSH connectivity ──────────────────────────────────
    printf '  %sSSH connectivity%s\n\n' "${BOLD}" "${NC}"
    _parse_inventory
    if [[ "${#INV_WORKER_HOSTS[@]}" -gt 0 ]]; then
        for h in "${INV_WORKER_HOSTS[@]}"; do
            printf '  %s▶%s ssh %s@%s exit\n' "${YELLOW}" "${NC}" "${INV_SSH_USER}" "${h}"
            printf '  %s\n' "$(printf '─%.0s' $(seq 1 50))"
            if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -q \
                "${INV_SSH_USER}@${h}" "exit" 2>/dev/null; then
                log_success "SSH to ${INV_SSH_USER}@${h} OK."
            else
                log_error "SSH to ${INV_SSH_USER}@${h} failed."
            fi
            printf '\n'
        done
    elif [[ -n "${WORKER_NODE_IP}" ]]; then
        printf '  %s▶%s ssh %s@%s exit\n' "${YELLOW}" "${NC}" "${WORKER_SSH_USER}" "${WORKER_NODE_IP}"
        printf '  %s\n' "$(printf '─%.0s' $(seq 1 50))"
        if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -q \
            "${WORKER_SSH_USER}@${WORKER_NODE_IP}" "exit" 2>/dev/null; then
            log_success "SSH to ${WORKER_SSH_USER}@${WORKER_NODE_IP} OK."
        else
            log_error "SSH to ${WORKER_SSH_USER}@${WORKER_NODE_IP} failed."
        fi
    else
        log_warn "No worker nodes found — skipping SSH check."
    fi
    printf '\n'

    # ── Summary ───────────────────────────────────────────
    printf '%s%s%s\n' "${CYAN}" "$(printf '─%.0s' $(seq 1 54))" "${NC}"
    printf '  %sSummary%s\n' "${BOLD}" "${NC}"
    printf '%s%s%s\n\n' "${CYAN}" "$(printf '─%.0s' $(seq 1 54))" "${NC}"
    printf '  Steps to activate a policy on your domain:\n\n'
    printf '   2)  Add policy    → upload .eflint file to brane-chk\n'
    printf '   3)  Activate      → set the uploaded version as active\n'
    printf '\n'
    printf '%s%s%s\n' "${CYAN}" "$(printf '─%.0s' $(seq 1 54))" "${NC}"

    press_enter
}

# ==========================================
# 2. ADD POLICY
# ==========================================

add_policy() {
    clear
    section_header "Add Policy to Domain"
    printf '\n'

    # ── Step 1: Token ─────────────────────────────────────
    printf '  %sStep 1: Select policy token%s\n\n' "${BOLD}" "${NC}"
    if [[ ! -d "${TOKEN_DIR}" ]]; then
        log_error "policy_tokens/ not found: ${TOKEN_DIR}"
        printf '  → Create it and place your token JSON file inside.\n'
        press_enter
        return 1
    fi
    _pick_token || { press_enter; return 1; }
    _check_token_expiry "${SEL_TOKEN_PATH}" || { press_enter; return 1; }
    local token
    token=$(_read_token "${SEL_TOKEN_PATH}")
    [[ -z "${token}" ]] && { log_error "Could not read token."; press_enter; return 1; }
    printf '\n'

    # ── Step 2: Policy file ───────────────────────────────
    printf '  %sStep 2: Select policy file%s\n\n' "${BOLD}" "${NC}"
    printf '  Available .eflint files in repo:\n\n'
    local eflint_files=()
    while IFS= read -r f; do
        eflint_files+=("${f}")
        printf '    [%d] %s\n' "${#eflint_files[@]}" "${f#${REPO_ROOT}/}"
    done < <(find "${REPO_ROOT}" -name "*.eflint" 2>/dev/null | sort)
    printf '\n'

    local policy_path=""
    if [[ "${#eflint_files[@]}" -gt 0 ]]; then
        read -r -p "  Select number or type a path: " pol_choice
        if [[ "${pol_choice}" =~ ^[0-9]+$ ]] && \
           [[ "${pol_choice}" -ge 1 ]] && \
           [[ "${pol_choice}" -le "${#eflint_files[@]}" ]]; then
            policy_path="${eflint_files[$((pol_choice-1))]}"
        else
            policy_path="${pol_choice}"
        fi
    else
        log_warn "No .eflint files found in repo."
        read -r -e -p "  Enter path to .eflint policy file: " policy_path
    fi

    if [[ -z "${policy_path}" || ! -f "${policy_path}" ]]; then
        log_error "Policy file not found: ${policy_path:-<empty>}"
        press_enter
        return 1
    fi
    log_success "Policy file: ${policy_path}"
    printf '\n'

    # ── Step 3: Worker connection ─────────────────────────
    printf '  %sStep 3: Worker node connection%s\n' "${BOLD}" "${NC}"
    _get_worker_connection || { press_enter; return 1; }
    printf '\n'

    # ── Step 4: Upload and add ────────────────────────────
    printf '  %sStep 4: Upload and add policy%s\n\n' "${BOLD}" "${NC}"
    local remote_file="${REMOTE_WORK_DIR}/$(basename "${policy_path}")"

    printf '  %s▶%s ssh %s@%s mkdir -p %s\n' \
        "${YELLOW}" "${NC}" "${WORKER_USER}" "${WORKER_HOST}" "${REMOTE_WORK_DIR}"
    printf '  %s\n' "$(printf '─%.0s' $(seq 1 50))"
    ssh -o StrictHostKeyChecking=no "${WORKER_USER}@${WORKER_HOST}" \
        "mkdir -p ${REMOTE_WORK_DIR}" 2>/dev/null
    printf '\n'

    printf '  %s▶%s scp %s → %s@%s:%s\n' "${YELLOW}" "${NC}" \
        "$(basename "${policy_path}")" "${WORKER_USER}" "${WORKER_HOST}" "${remote_file}"
    printf '  %s\n' "$(printf '─%.0s' $(seq 1 50))"
    scp -o StrictHostKeyChecking=no "${policy_path}" \
        "${WORKER_USER}@${WORKER_HOST}:${remote_file}"
    if [[ $? -ne 0 ]]; then
        log_error "Failed to copy policy file to worker node."
        press_enter
        return 1
    fi
    log_success "Policy file uploaded."
    printf '\n'

    run_cmd "ssh -o StrictHostKeyChecking=no ${WORKER_USER}@${WORKER_HOST} \
\"branectl policies add '${remote_file}' \
--token '${token}' \
--address localhost:${WORKER_PORT}\""

    if [[ $? -eq 0 ]]; then
        printf '\n'
        log_success "Policy added. Note the version ID above."
        printf '  → Use option 3 to activate it.\n'
    fi

    press_enter
}

# ==========================================
# 3. ACTIVATE POLICY
# ==========================================

activate_policy() {
    clear
    section_header "Activate Policy Version"
    printf '\n'

    # ── Step 1: Token ─────────────────────────────────────
    printf '  %sStep 1: Select policy token%s\n\n' "${BOLD}" "${NC}"
    if [[ ! -d "${TOKEN_DIR}" ]]; then
        log_error "policy_tokens/ not found: ${TOKEN_DIR}"
        press_enter
        return 1
    fi
    _pick_token || { press_enter; return 1; }
    _check_token_expiry "${SEL_TOKEN_PATH}" || { press_enter; return 1; }
    local token
    token=$(_read_token "${SEL_TOKEN_PATH}")
    [[ -z "${token}" ]] && { log_error "Could not read token."; press_enter; return 1; }
    printf '\n'

    # ── Step 2: Worker connection ─────────────────────────
    printf '  %sStep 2: Worker node connection%s\n' "${BOLD}" "${NC}"
    _get_worker_connection || { press_enter; return 1; }
    printf '\n'

    # ── Step 3: List available versions ───────────────────
    printf '  %sStep 3: Available policy versions%s\n\n' "${BOLD}" "${NC}"
    printf '  %s▶%s ssh %s@%s branectl policies list ...\n' \
        "${YELLOW}" "${NC}" "${WORKER_USER}" "${WORKER_HOST}"
    printf '  %s\n' "$(printf '─%.0s' $(seq 1 50))"

    local versions_raw
    versions_raw=$(ssh -o StrictHostKeyChecking=no "${WORKER_USER}@${WORKER_HOST}" \
        "branectl policies list \
--token '${token}' \
--address localhost:${WORKER_PORT} 2>/dev/null || \
curl -s -H 'Authorization: Bearer ${token}' \
http://localhost:${WORKER_PORT}/v1/policies 2>/dev/null" 2>/dev/null || true)

    if [[ -n "${versions_raw}" ]]; then
        printf '%s\n' "${versions_raw}" | sed 's/^/    /'
    else
        log_warn "Could not retrieve policy list — enter a version ID manually."
    fi
    printf '\n'

    # ── Step 4: Activate ──────────────────────────────────
    printf '  %sStep 4: Activate version%s\n\n' "${BOLD}" "${NC}"
    local version_id
    read -r -p "  Policy version ID to activate: " version_id
    [[ -z "${version_id}" ]] && { log_error "Version ID required."; press_enter; return 1; }
    printf '\n'

    run_cmd "ssh -o StrictHostKeyChecking=no ${WORKER_USER}@${WORKER_HOST} \
\"branectl policies activate '${version_id}' \
--token '${token}' \
--address localhost:${WORKER_PORT} 2>/dev/null || \
curl -s -X POST \
-H 'Authorization: Bearer ${token}' \
http://localhost:${WORKER_PORT}/v1/policies/${version_id}/activate\""

    if [[ $? -eq 0 ]]; then
        printf '\n'
        log_success "Policy version ${version_id} activated."
        printf '\n'

        # ── Verification ──────────────────────────────────
        printf '  %sVerification — active policy%s\n\n' "${BOLD}" "${NC}"
        printf '  %s▶%s ssh %s@%s curl .../v1/policies/active\n' \
            "${YELLOW}" "${NC}" "${WORKER_USER}" "${WORKER_HOST}"
        printf '  %s\n' "$(printf '─%.0s' $(seq 1 50))"
        ssh -o StrictHostKeyChecking=no "${WORKER_USER}@${WORKER_HOST}" \
            "curl -s -H 'Authorization: Bearer ${token}' \
http://localhost:${WORKER_PORT}/v1/policies/active 2>/dev/null \
| python3 -m json.tool 2>/dev/null || echo '(no response)'" 2>/dev/null \
            | sed 's/^/    /'
    fi

    printf '\n'
    printf '  Note: if workflow execution is still denied, check that\n'
    printf '  the policy permits the task and user in question.\n'

    press_enter
}

# ==========================================
# MENU LOOP
# ==========================================

while true; do
    clear
    section_header "BRANE — Policy Manager"

    # Show inventory summary in status bar
    _parse_inventory 2>/dev/null || true
    local_workers="${INV_WORKER_HOSTS[*]:-not found in inventory}"

    printf '  %sInventory    :%s %s\n' "${YELLOW}" "${NC}" \
        "$( [[ -f "${ANSIBLE_INVENTORY}" ]] && printf 'found' || printf 'not found' )"
    printf '  %sWorker nodes :%s %s\n' "${YELLOW}" "${NC}" "${local_workers}"
    printf '  %sSSH user     :%s %s\n' "${YELLOW}" "${NC}" "${INV_SSH_USER:-${WORKER_SSH_USER:-${USER}}}"
    printf '  %sToken dir    :%s %s\n' "${YELLOW}" "${NC}" "${TOKEN_DIR}"
    printf '\n'

    section_divider "Status"
    printf '   1)  Check environment & token validity\n'
    printf '\n'

    section_divider "Policy Lifecycle"
    printf '   2)  Add policy to domain\n'
    printf '   3)  Activate policy version\n'
    printf '\n'

    printf '  %s\n' "$(printf '─%.0s' $(seq 1 52))"
    printf '   q)  Back to main menu\n'
    printf '\n'
    read -r -p "  Choose an option [1-3 or q]: " choice
    printf '\n'

    case "${choice}" in
        1) check_environment ;;
        2) add_policy        ;;
        3) activate_policy   ;;
        q|Q)
            exec bash "${SCRIPT_DIR}/brane_main.sh"
            ;;
        *)
            log_error "Invalid option '${choice}'."
            sleep 1
            ;;
    esac
done

