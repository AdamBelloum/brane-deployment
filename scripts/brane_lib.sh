#!/usr/bin/env bash
# =============================================================
# brane_lib.sh
# Version : 1.0.5
# Date    : 2026-08-17
# Desc    : Shared library sourced by all Brane helper scripts.
#           Do NOT execute this file directly.
# =============================================================

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "[ERROR] brane_lib.sh is a library — source it, do not run it directly."
    exit 1
fi

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    export PATH="$HOME/.local/bin:$PATH"
fi

# ==========================================
# COLORS
# ==========================================

GREEN=$'\033[0;32m'
RED=$'\033[0;31m'
BLUE=$'\033[0;34m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'
BOLD=$'\033[1m'
NC=$'\033[0m'

# ==========================================
# LOGGING
# ==========================================

log_info()    { printf '%s[INFO]%s %s\n'    "${BLUE}"   "${NC}" "$1"; }
log_success() { printf '%s[OK]%s   %s\n'    "${GREEN}"  "${NC}" "$1"; }
log_warn()    { printf '%s[WARN]%s %s\n'    "${YELLOW}" "${NC}" "$1"; }
log_error()   { printf '%s[ERROR]%s %s\n'   "${RED}"    "${NC}" "$1"; }
log_step()    { printf '%s[STEP %s]%s %s\n' "${CYAN}"   "$1" "${NC}" "$2"; }

# ==========================================
# UI HELPERS
# ==========================================

press_enter() {
    printf '\n'
    read -r -p "  Press [Enter] to return to the menu..."
}

press_enter_or_back() {
    printf '\n'
    read -r -p "  Press [Enter] to continue or [q] to go back: " _ans
    [[ "${_ans}" == "q" || "${_ans}" == "Q" ]] && return 1
    return 0
}

section_header() {
    local title="$1"
    local width=52
    local pad=$(( (width - ${#title} - 2) / 2 ))
    local line
    line=$(printf '═%.0s' $(seq 1 $width))
    printf '\n'
    printf '%s╔%s╗%s\n' "${CYAN}" "${line}" "${NC}"
    printf '%s║%s%*s%s%s%s%*s%s║%s\n' \
        "${CYAN}" "${NC}" \
        $pad "" \
        "${BOLD}" "${title}" "${NC}" \
        $(( width - pad - ${#title} )) "" \
        "${CYAN}" "${NC}"
    printf '%s╚%s╝%s\n' "${CYAN}" "${line}" "${NC}"
    printf '\n'
}

section_divider() {
    local label="$1"
    local dashes
    dashes=$(printf '─%.0s' $(seq 1 $(( 44 - ${#label} )) ))
    printf '%s  ┌─ %s %s┐%s\n' "${CYAN}" "${label}" "${dashes}" "${NC}"
    printf '%s  └%s┘%s\n'      "${CYAN}" "$(printf '─%.0s' $(seq 1 50))" "${NC}"
}

# ==========================================
# COMMAND EXECUTION
# ==========================================

run_cmd() {
    printf '\n'
    printf '  %s▶%s %s\n' "${YELLOW}" "${NC}" "$1"
    printf '  %s\n' "$(printf '─%.0s' $(seq 1 50))"
    bash -c "$1"
    local rc=$?
    printf '\n'
    [[ $rc -eq 0 ]] && log_success "Command completed." || log_error "Command exited with code ${rc}."
    return $rc
}

run_quiet() { bash -c "$1" &>/dev/null; }

run_remote() {
    local host="$1" user="$2" cmd="$3"
    printf '\n'
    printf '  %s▶ [%s@%s]%s %s\n' "${YELLOW}" "${user}" "${host}" "${NC}" "${cmd}"
    printf '  %s\n' "$(printf '─%.0s' $(seq 1 50))"
    ssh -o StrictHostKeyChecking=no "${user}@${host}" "${cmd}"
    local rc=$?
    printf '\n'
    [[ $rc -eq 0 ]] && log_success "Remote command completed." || log_error "Remote command exited with code ${rc}."
    return $rc
}

copy_to_remote() {
    local src="$1" host="$2" user="$3" dest="$4"
    log_info "Copying ${src} → ${user}@${host}:${dest}"
    scp -o StrictHostKeyChecking=no "${src}" "${user}@${host}:${dest}"
}

# ==========================================
# CONFIG LOADING
# ==========================================

_apply_defaults() {
    local script_dir="$1"
    local repo_root
    repo_root="$(cd "${script_dir}/.." && pwd)"

    BRANE_DEPLOY_HOME="${BRANE_DEPLOY_HOME:-${repo_root}/docker-deployment}"
    PACKAGE_DIR="${PACKAGE_DIR:-${repo_root}/packages}"

    ANSIBLE_INVENTORY="${BRANE_DEPLOY_HOME}/inventories/production/hosts.ini"
    ANSIBLE_PLAYBOOK="${BRANE_DEPLOY_HOME}/site.yml"
    ALL_TAGS="prerequisites,branectl,workers,central,certs,start,smoke"

    PACKAGE_NAME="${PACKAGE_NAME:-hello_world}"
    WORKFLOW_NAME="${WORKFLOW_NAME:-hello_world.bs}"
    CONTAINER_YML="${CONTAINER_YML:-container.yml}"
    PACKAGE_VERSION="${PACKAGE_VERSION:-1.0.0}"
    WORKFLOW_PATH="${PACKAGE_DIR}/${PACKAGE_NAME}/${WORKFLOW_NAME}"

    PORT_REPL="${PORT_REPL:-50053}"
    PORT_REGISTRY="${PORT_REGISTRY:-50051}"
    PORT_CHK="${PORT_CHK:-50054}"
    INSTANCE_NAME="${INSTANCE_NAME:-my-brane}"

    HOST_IP="${HOST_IP:-}"
    BRANE_USER="${BRANE_USER:-}"
    WORKER_NODE_IP="${WORKER_NODE_IP:-}"
    WORKER_SSH_USER="${WORKER_SSH_USER:-${USER}}"
    POLICY_TOKEN_PATH="${POLICY_TOKEN_PATH:-}"
    POLICY_EXPERT_SECRET="${POLICY_EXPERT_SECRET:-./config/secrets/policy_expert_secret.json}"
}

load_config() {
    local script_dir="$1"
    local config_file="${BRANE_HELPER_CONFIG:-${script_dir}/.brane_helper.env}"
    if [[ ! -f "${config_file}" ]]; then
        printf '\n'
        log_error "Config file not found: ${config_file}"
        printf '  Create it: cp scripts/.brane_helper.env.example scripts/.brane_helper.env\n'
        exit 1
    fi
    # shellcheck source=/dev/null
    source "${config_file}"
    _apply_defaults "${script_dir}"
    : "${HOST_IP:?HOST_IP must be set in ${config_file}}"
}

load_config_soft() {
    local script_dir="$1"
    local config_file="${BRANE_HELPER_CONFIG:-${script_dir}/.brane_helper.env}"
    [[ -f "${config_file}" ]] && source "${config_file}"
    _apply_defaults "${script_dir}"
}

# ==========================================
# DEPENDENCY CHECKS
# ==========================================

check_bin() {
    local bin="$1" hint="${2:-}"
    if ! command -v "${bin}" &>/dev/null; then
        log_error "'${bin}' not found in PATH."
        [[ -n "${hint}" ]] && printf '  → %s\n' "${hint}"
        return 1
    fi
    log_success "'${bin}' found: $(command -v "${bin}")"
    return 0
}

check_deps_user() {
    local ok=0
    printf '\n'
    log_info "Checking required tools..."
    printf '\n'
    check_bin "brane"  "Install from: https://github.com/epi-project/brane/releases" || ok=1
    check_bin "docker" "Install Docker Desktop: https://docs.docker.com/get-docker/"  || ok=1
    printf '\n'
    return $ok
}

check_deps_policy() {
    local ok=0
    printf '\n'
    log_info "Checking required tools for Policy Manager role..."
    printf '\n'
    check_bin "ssh"     "SSH client required."                      || ok=1
    check_bin "scp"     "SCP required (usually bundled with SSH)."  || ok=1
    check_bin "curl"    "Install via: brew install curl  (macOS)"   || ok=1
    check_bin "python3" "Required for JWT expiry check."            || ok=1
    printf '\n'
    return $ok
}

check_deps_admin() {
    local ok=0
    printf '\n'
    log_info "Checking required tools for Admin role..."
    printf '\n'
    check_bin "ansible-playbook" "Run: pip install -r docker-deployment/requirements.txt"      || ok=1
    check_bin "branectl"         "Install from: https://github.com/epi-project/brane/releases"  || ok=1
    check_bin "brane"            "Install from: https://github.com/epi-project/brane/releases"  || ok=1
    check_bin "ssh"              "SSH client required."                                          || ok=1
    printf '\n'
    return $ok
}

# ==========================================
# CONNECTIVITY CHECK
# Uses Bash /dev/tcp with a background job + hard timeout.
# Reliable on macOS and Linux without nc flag differences.
# ==========================================

check_port() {
    local host="$1" port="$2" label="${3:-${host}:${port}}"
    local timeout_sec=3

    ( exec 3<>"/dev/tcp/${host}/${port}" 2>/dev/null ) &
    local probe_pid=$!

    local elapsed=0
    while kill -0 "${probe_pid}" 2>/dev/null; do
        sleep 0.5
        elapsed=$(( elapsed + 1 ))
        if [[ "${elapsed}" -ge $(( timeout_sec * 2 )) ]]; then
            kill "${probe_pid}" 2>/dev/null
            wait "${probe_pid}" 2>/dev/null
            log_error "${label} timed out after ${timeout_sec}s."
            return 1
        fi
    done

    wait "${probe_pid}"
    local rc=$?
    if [[ $rc -eq 0 ]]; then
        log_success "${label} reachable."
        return 0
    else
        log_error "${label} not reachable."
        return 1
    fi
}

check_ssh() {
    local host="$1" user="$2"
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -q "${user}@${host}" "exit" 2>/dev/null; then
        log_success "SSH to ${user}@${host} OK."
        return 0
    else
        log_error "SSH to ${user}@${host} failed."
        return 1
    fi
}

# ==========================================
# INSTANCE PICKER
# Parses `brane instance list` robustly:
# skips header/separator lines and extracts the first
# non-empty token from each data row.
# Sets SEL_INSTANCE.
# ==========================================

_pick_instance() {
    # Capture raw output
    local raw
    raw=$(brane instance list 2>/dev/null || true)

    if [[ -z "${raw}" ]]; then
        log_error "No instances found. Add one first (option 2)."
        return 1
    fi

    # Parse: skip lines that are headers or separators (contain only dashes, pipes, spaces, =)
    local INSTANCE_NAMES=()
    while IFS= read -r line; do
        # Skip blank lines and separator/header lines
        [[ -z "${line}" ]]                          && continue
        [[ "${line}" =~ ^[[:space:]]*[-=|+]+[[:space:]]*$ ]] && continue
        [[ "${line}" =~ ^[[:space:]]*(Name|NAME|Instance|INSTANCE)[[:space:]] ]] && continue

        # Extract first whitespace-delimited token
        local token
        token=$(printf '%s' "${line}" | awk '{print $1}')
        [[ -n "${token}" ]] && INSTANCE_NAMES+=("${token}")
    done <<< "${raw}"

    if [[ "${#INSTANCE_NAMES[@]}" -eq 0 ]]; then
        log_error "Could not parse any instance names from output:"
        printf '%s\n' "${raw}" | sed 's/^/    /'
        printf '\n'
        log_error "Add an instance first (option 2)."
        return 1
    fi

    if [[ "${#INSTANCE_NAMES[@]}" -eq 1 ]]; then
        SEL_INSTANCE="${INSTANCE_NAMES[0]}"
        log_info "Using instance: ${SEL_INSTANCE}"
        return 0
    fi

    local idx=0
    while [[ $idx -lt ${#INSTANCE_NAMES[@]} ]]; do
        printf '    [%d] %s\n' "$((idx+1))" "${INSTANCE_NAMES[$idx]}"
        idx=$((idx + 1))
    done
    printf '\n'

    local CHOICE
    while true; do
        read -r -p "  Select instance [1-${#INSTANCE_NAMES[@]}]: " CHOICE
        [[ "${CHOICE}" =~ ^[0-9]+$ ]] && \
            [[ "${CHOICE}" -ge 1 ]] && \
            [[ "${CHOICE}" -le "${#INSTANCE_NAMES[@]}" ]] && break
        log_error "Invalid choice, try again."
    done

    SEL_INSTANCE="${INSTANCE_NAMES[$((CHOICE-1))]}"
}

# ==========================================
# JWT TOKEN HELPERS
# ==========================================

check_token_expiry() {
    local token_path="$1"
    if [[ ! -f "${token_path}" ]]; then
        log_error "Token file not found: ${token_path}"
        return 1
    fi

    local result
    result=$(python3 -c "
import json, sys, time, base64
try:
    data = json.load(open('${token_path}'))
    token = data.get('token') or data.get('access_token') or list(data.values())[0]
    payload = token.split('.')[1]
    payload += '=' * (4 - len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
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
        VALID:*)  log_success "Token is valid (expires in ${result#VALID:})."; return 0 ;;
        EXPIRED)  log_error "Token is expired. Request a new one from your Brane admin."; return 1 ;;
        ERROR:*)  log_error "Could not parse token: ${result#ERROR:}"; return 1 ;;
        *)        log_error "Unexpected token check result."; return 1 ;;
    esac
}

# ==========================================
# ADMIN PREFLIGHT
# ==========================================

preflight_admin() {
    local missing=0
    [[ ! -f "${ANSIBLE_INVENTORY}" ]] \
        && log_error "Inventory not found: ${ANSIBLE_INVENTORY}" && missing=1
    [[ ! -f "${ANSIBLE_PLAYBOOK}" ]] \
        && log_error "Playbook not found: ${ANSIBLE_PLAYBOOK}" && missing=1
    ! command -v ansible-playbook &>/dev/null \
        && log_error "ansible-playbook not found. Activate your venv." && missing=1
    if [[ "${missing}" -eq 1 ]]; then
        printf '\n'
        log_error "Preflight failed. Fix the issues above before continuing."
        press_enter
        return 1
    fi
    return 0
}

