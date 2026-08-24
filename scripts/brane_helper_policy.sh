#!/usr/bin/env bash
# =============================================================
# brane_helper_policy.sh
# Version : 2.2.1
# Date    : 2026-08-22
# Desc    : Brane helper for domain policy managers.
#
# Policies are domain-local. A policy manager selects a worker
# host and explicitly identifies its Brane domain (for example,
# client-node-2). The helper then operates on that worker's
# brane-chk-<domain> checker.
# =============================================================

set -o nounset
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${SCRIPT_DIR}/brane_lib.sh"
load_config_soft "${SCRIPT_DIR}"

TOKEN_DIR="${REPO_ROOT}/policy_tokens"
REMOTE_WORK_DIR="/tmp/brane_policy"
CHECKER_PORT="${POLICY_CHECKER_PORT:-50054}"

_parse_inventory() {
    INV_WORKER_HOSTS=()
    INV_SSH_USER="${WORKER_SSH_USER:-${USER}}"
    [[ -f "${ANSIBLE_INVENTORY}" ]] || return 1

    local in_workers=0 line host
    while IFS= read -r line; do
        [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
        if [[ "${line}" =~ ^\[workers\] ]]; then
            in_workers=1; continue
        elif [[ "${line}" =~ ^\[ ]]; then
            in_workers=0; continue
        fi
        [[ "${in_workers}" -eq 1 ]] || continue
        if [[ "${line}" =~ ansible_host=([^[:space:]]+) ]]; then
            host="${BASH_REMATCH[1]}"
        else
            host="$(printf '%s' "${line}" | awk '{print $1}')"
        fi
        if [[ "${line}" =~ ansible_user=([^[:space:]]+) ]]; then
            INV_SSH_USER="${BASH_REMATCH[1]}"
        fi
        [[ -n "${host}" ]] && INV_WORKER_HOSTS+=("${host}")
    done < "${ANSIBLE_INVENTORY}"
}

_pick_worker_host() {
    _parse_inventory || true
    local choice idx=0 host
    if [[ "${#INV_WORKER_HOSTS[@]}" -gt 0 ]]; then
        printf '  Worker hosts:\n\n'
        for host in "${INV_WORKER_HOSTS[@]}"; do
            idx=$((idx + 1)); printf '    [%d] %s\n' "${idx}" "${host}"
        done
        printf '\n'
        read -r -p "  Select number or type a hostname/IP: " choice
        if [[ "${choice}" =~ ^[0-9]+$ ]] && [[ "${choice}" -ge 1 ]] && [[ "${choice}" -le "${#INV_WORKER_HOSTS[@]}" ]]; then
            WORKER_HOST="${INV_WORKER_HOSTS[$((choice - 1))]}"
        else
            WORKER_HOST="${choice}"
        fi
    else
        read -r -p "  Worker hostname/IP: " WORKER_HOST
    fi
    [[ -n "${WORKER_HOST}" ]] || { log_error "A worker host is required."; return 1; }
}

_pick_token() {
    local files=() f choice idx=0
    [[ -d "${TOKEN_DIR}" ]] || { log_error "Token directory not found: ${TOKEN_DIR}"; return 1; }
    while IFS= read -r f; do files+=("${f}"); done < <(find "${TOKEN_DIR}" -maxdepth 1 -type f -name '*.json' 2>/dev/null | sort)
    [[ "${#files[@]}" -gt 0 ]] || { log_error "No policy-token JSON files found in ${TOKEN_DIR}."; return 1; }
    if [[ "${#files[@]}" -eq 1 ]]; then
        SEL_TOKEN_PATH="${files[0]}"; log_info "Using token: $(basename "${SEL_TOKEN_PATH}")"; return 0
    fi
    printf '  Available policy tokens:\n\n'
    for f in "${files[@]}"; do idx=$((idx + 1)); printf '    [%d] %s\n' "${idx}" "$(basename "${f}")"; done
    while true; do
        read -r -p "  Select token [1-${#files[@]}]: " choice
        if [[ "${choice}" =~ ^[0-9]+$ ]] && [[ "${choice}" -ge 1 ]] && [[ "${choice}" -le "${#files[@]}" ]]; then
            SEL_TOKEN_PATH="${files[$((choice - 1))]}"; return 0
        fi
        log_error "Invalid token selection."
    done
}

_read_token() {
    python3 - "$1" <<'PY'
import json, sys
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f: data = json.load(f)
    token = (data.get("token") or data.get("access_token") or next(iter(data.values()))) if isinstance(data, dict) else data
    print(str(token).strip())
except Exception:
    with open(path, encoding="utf-8") as f: print(f.read().strip())
PY
}

_check_token_expiry() {
    local result
    result=$(python3 - "$1" <<'PY'
import base64, json, sys, time
try:
    with open(sys.argv[1], encoding="utf-8") as f: data = json.load(f)
    token = data.get("token") or data.get("access_token") or next(iter(data.values()))
    payload = token.split(".")[1]; payload += "=" * (-len(payload) % 4)
    remaining = json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0) - time.time()
    print("EXPIRED" if remaining <= 0 else f"VALID:{int(remaining // 86400)}d {int((remaining % 86400) // 3600)}h")
except Exception as exc:
    print(f"ERROR:{exc}")
PY
)
    case "${result}" in
        VALID:*) log_success "Token valid — expires in ${result#VALID:}" ;;
        EXPIRED) log_error "Token expired. Request a replacement from the administrator."; return 1 ;;
        *)       log_warn "Could not validate expiry (${result#ERROR:}). Continuing." ;;
    esac
}

_get_domain_connection() {
    _pick_worker_host || return 1
    _parse_inventory || true
    local default_user="${INV_SSH_USER:-${WORKER_SSH_USER:-${USER}}}" input_user input_node_config input_port
    read -r -p "  SSH user [${default_user}]: " input_user
    WORKER_USER="${input_user:-${default_user}}"
    printf '\n  The domain ID is the Brane location identifier, not merely the SSH host.\n'
    read -r -p "  Brane domain ID (e.g. client-node-2): " DOMAIN_ID
    [[ "${DOMAIN_ID}" =~ ^[A-Za-z0-9._-]+$ ]] || { log_error "Invalid domain ID."; return 1; }
    CHECKER_CONTAINER="brane-chk-${DOMAIN_ID}"
    REMOTE_NODE_CONFIG="/home/${WORKER_USER}/brane-worker/node.yml"
    read -r -p "  Remote node.yml [${REMOTE_NODE_CONFIG}]: " input_node_config
    REMOTE_NODE_CONFIG="${input_node_config:-${REMOTE_NODE_CONFIG}}"
    read -r -p "  Checker policy port [${CHECKER_PORT}]: " input_port
    CHECKER_ADDRESS="127.0.0.1:${input_port:-${CHECKER_PORT}}"
    printf '\n'
    log_info "Worker host       : ${WORKER_USER}@${WORKER_HOST}"
    log_info "Brane domain      : ${DOMAIN_ID}"
    log_info "Checker container : ${CHECKER_CONTAINER}"
    log_info "Checker endpoint  : ${CHECKER_ADDRESS} (inside checker network namespace)"
}

# Executes the documented CLI commands in the selected brane-chk network
# namespace. TOKEN is passed through `env` after nsenter so sudo does not
# discard it through its normal environment reset.
_remote_branectl() {
    local operation="$1" payload="${2:-}" remote_token="$3"
    local runner_local="${SCRIPT_DIR}/brane_policy_remote_runner.sh"
    local runner_remote="${REMOTE_WORK_DIR}/runner-${RANDOM}-${RANDOM}.sh"
    local remote_cmd rc

    [[ -f "${runner_local}" ]] || {
        log_error "Remote policy runner not found: ${runner_local}"
        return 1
    }

    # Upload the runner as a file. This avoids feeding source text through
    # an SSH pseudo-terminal, which otherwise echoes it to the user.
    if ! LC_ALL=C LANG=C scp \
        -o StrictHostKeyChecking=accept-new \
        -o LogLevel=ERROR \
        "${runner_local}" \
        "${WORKER_USER}@${WORKER_HOST}:${runner_remote}"; then
        log_error "Could not upload the remote policy runner."
        return 1
    fi

    # The remote login shell is Bash on the deployed workers. printf %q
    # preserves each argument, including an optional empty payload.
    printf -v remote_cmd \
        'bash %q %q %q %q %q %q %q' \
        "${runner_remote}" \
        "${CHECKER_CONTAINER}" \
        "${REMOTE_NODE_CONFIG}" \
        "${CHECKER_ADDRESS}" \
        "${remote_token}" \
        "${operation}" \
        "${payload}"

    LC_ALL=C LANG=C ssh -tt \
        -o StrictHostKeyChecking=accept-new \
        -o LogLevel=ERROR \
        "${WORKER_USER}@${WORKER_HOST}" \
        "${remote_cmd}"
    rc=$?

    # The runner itself removes the staged JWT. This removes only its
    # temporary executable file, irrespective of command success.
    LC_ALL=C LANG=C ssh \
        -o StrictHostKeyChecking=accept-new \
        -o LogLevel=ERROR \
        "${WORKER_USER}@${WORKER_HOST}" \
        "rm -f -- '${runner_remote}'" >/dev/null 2>&1 || true

    return "${rc}"
}
_stage_token() {
    local raw_token remote_token
    raw_token="$(_read_token "${SEL_TOKEN_PATH}")"
    [[ -n "${raw_token}" ]] || { log_error "Could not read JWT from ${SEL_TOKEN_PATH}."; return 1; }
    remote_token="${REMOTE_WORK_DIR}/token-${RANDOM}-${RANDOM}.jwt"
    if ! ssh -o StrictHostKeyChecking=no "${WORKER_USER}@${WORKER_HOST}" \
        "umask 077 && mkdir -p '${REMOTE_WORK_DIR}' && cat > '${remote_token}' && chmod 600 '${remote_token}'" <<< "${raw_token}"; then
        log_error "Could not stage the policy token on the worker."; return 1
    fi
    printf '%s\n' "${remote_token}"
}

add_policy() {
    clear; section_header "Add Policy to Domain"; printf '\n'
    _pick_token || { press_enter; return 1; }
    _check_token_expiry "${SEL_TOKEN_PATH}" || { press_enter; return 1; }
    local policy_path remote_policy remote_token
    read -r -e -p "  Path to .eflint policy: " policy_path
    [[ -f "${policy_path}" ]] || { log_error "Policy file not found: ${policy_path:-<empty>}"; press_enter; return 1; }
    _get_domain_connection || { press_enter; return 1; }
    remote_policy="${REMOTE_WORK_DIR}/policy-${RANDOM}-${RANDOM}.eflint"
    if ! ssh -o StrictHostKeyChecking=no "${WORKER_USER}@${WORKER_HOST}" "mkdir -p '${REMOTE_WORK_DIR}'" || \
       ! scp -o StrictHostKeyChecking=no "${policy_path}" "${WORKER_USER}@${WORKER_HOST}:${remote_policy}"; then
        log_error "Policy upload failed."; press_enter; return 1
    fi
    remote_token="$(_stage_token)" || { press_enter; return 1; }
    printf '\n'; log_info "Adding policy to domain '${DOMAIN_ID}'..."
    printf '  The checker will return a policy version. Record it for activation.\n\n'
    if _remote_branectl add "${remote_policy}" "${remote_token}"; then
        log_success "Policy was added to ${DOMAIN_ID}."
    else
        log_error "Policy add failed; no policy was activated."
    fi
    ssh -o StrictHostKeyChecking=no "${WORKER_USER}@${WORKER_HOST}" "rm -f -- '${remote_policy}'" >/dev/null 2>&1 || true
    press_enter
}

activate_policy() {
    clear; section_header "Activate Policy Version"; printf '\n'
    _pick_token || { press_enter; return 1; }
    _check_token_expiry "${SEL_TOKEN_PATH}" || { press_enter; return 1; }
    _get_domain_connection || { press_enter; return 1; }
    local version remote_token
    read -r -p "  Policy version to activate [blank = choose interactively]: " version
    remote_token="$(_stage_token)" || { press_enter; return 1; }
    printf '\n'; log_info "Activating policy on domain '${DOMAIN_ID}'..."
    if _remote_branectl activate "${version}" "${remote_token}"; then
        log_success "Activation command completed for ${DOMAIN_ID}."
    else
        log_error "Policy activation failed."
    fi
    press_enter
}

inspect_policies() {
    clear; section_header "Inspect Policies in a Domain"; printf '\n'
    _pick_token || { press_enter; return 1; }
    _check_token_expiry "${SEL_TOKEN_PATH}" || { press_enter; return 1; }
    _get_domain_connection || { press_enter; return 1; }
    local remote_token
    remote_token="$(_stage_token)" || { press_enter; return 1; }
    printf '\n'; log_info "The checker may present an interactive version selector."
    _remote_branectl list "" "${remote_token}" || log_error "Could not inspect policies."
    press_enter
}

check_environment() {
    clear; section_header "Policy Manager — Environment"; printf '\n'
    check_bin ssh "SSH client required."
    check_bin scp "SCP required."
    check_bin python3 "Python 3 required for token parsing."
    printf '\n'
    if [[ -d "${TOKEN_DIR}" ]]; then
        printf '  Policy tokens in %s:\n' "${TOKEN_DIR}"
        find "${TOKEN_DIR}" -maxdepth 1 -type f -name '*.json' -exec basename {} \; 2>/dev/null | sed 's/^/    • /' || true
    else
        log_warn "Token directory does not exist: ${TOKEN_DIR}"
    fi
    printf '\n  Policy operations require SSH access, Docker inspection, and sudo nsenter\n'
    printf '  privileges on the selected worker host.\n'
    press_enter
}

while true; do
    clear; section_header "BRANE — Policy Manager"
    printf '  %sToken directory:%s %s\n' "${YELLOW}" "${NC}" "${TOKEN_DIR}"
    printf '  %sPolicy model:%s domain-local checker policy stores\n\n' "${YELLOW}" "${NC}"
    section_divider "Policy Lifecycle"
    printf '   1)  Check environment\n'
    printf '   2)  Add policy to a domain\n'
    printf '   3)  Activate policy version\n'
    printf '   4)  Inspect policies in a domain\n'
    printf '\n   q)  Back to main menu\n\n'
    read -r -p "  Choose an option [1-4 or q]: " choice
    case "${choice}" in
        1) check_environment ;;
        2) add_policy ;;
        3) activate_policy ;;
        4) inspect_policies ;;
        q|Q) exec bash "${SCRIPT_DIR}/brane_main.sh" ;;
        *) log_error "Invalid option '${choice}'."; sleep 1 ;;
    esac
done

