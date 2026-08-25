#!/usr/bin/env bash
# =============================================================
# brane_helper_admin.sh
# Version : 1.0.0
# Date    : 2026-08-16
# Desc    : Brane helper for infrastructure admins.
#           Full deployment, certificate management, token
#           generation, health checks across all nodes,
#           and user/policy manager onboarding support.
# Usage   : bash scripts/brane_helper_admin.sh
#           (or via brane_main.sh → option 2)
# =============================================================

set -o nounset
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/brane_lib.sh"
load_config "${SCRIPT_DIR}"

# ==========================================
# HEALTH CHECK ENGINE
# (integrated from brane_healthcheck.sh)
# ==========================================

_hc_record() {
    local status="$1" node="$2" category="$3" message="$4"
    if [[ "${status}" == "OK" ]]; then
        HC_RESULTS+=("${GREEN}[OK]${NC}   [${node}] [${category}] ${message}")
        HC_PASS=$((HC_PASS + 1))
    else
        HC_RESULTS+=("${RED}[FAIL]${NC} [${node}] [${category}] ${message}")
        HC_FAIL=$((HC_FAIL + 1))
    fi
}

_hc_remote() {
    local host="$1"; shift
    local cmd
    cmd=$(printf '%s ' "$@")
    ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=5 \
        "${ANSIBLE_USER}@${host}" "${cmd}" 2>/dev/null || true
}

_hc_ansible_var() {
    local group="$1" var="$2" tmpfile result
    tmpfile=$(mktemp)
    ansible "${group}" -i "${ANSIBLE_INVENTORY}" \
        -m debug -a "msg={{ ${var} }}" --one-line 2>/dev/null > "${tmpfile}" || true
    result=$(sed -n 's/.*"msg": "\([^"]*\)".*/\1/p' "${tmpfile}" | head -1)
    rm -f "${tmpfile}"
    case "${result}" in
        *" "*) echo "" ;;
        *)     echo "${result}" ;;
    esac
}

_hc_ansible_var_all() {
    local group="$1" var="$2" tmpfile
    tmpfile=$(mktemp)
    ansible "${group}" -i "${ANSIBLE_INVENTORY}" \
        -m debug -a "msg={{ ${var} }}" --one-line 2>/dev/null > "${tmpfile}" || true
    sed -n 's/.*"msg": "\([^"]*\)".*/\1/p' "${tmpfile}" | grep -v ' ' || true
    rm -f "${tmpfile}"
}

_hc_check_container() {
    local node="$1" host="$2" name="$3" status
    status=$(_hc_remote "${host}" docker inspect --format '{{.State.Status}}' "${name}" 2>/dev/null || echo "missing")
    status=$(echo "${status}" | tr -d '[:space:]')
    if [[ "${status}" == "running" ]]; then
        _hc_record "OK"   "${node}" "container" "${name} is running"
    else
        _hc_record "FAIL" "${node}" "container" "${name} is ${status:-missing}"
    fi
}

_hc_check_port() {
    local node="$1" host="$2" port="$3" label="$4" result
    result=$(_hc_remote "${host}" ss -tlnp | grep ":${port}" || true)
    if [[ -n "${result}" ]]; then
        _hc_record "OK"   "${node}" "port" "${port} (${label}) is listening"
    else
        _hc_record "FAIL" "${node}" "port" "${port} (${label}) is NOT listening"
    fi
}

_hc_check_mount() {
    local node="$1" host="$2" container="$3" path="$4" mounted
    mounted=$(_hc_remote "${host}" \
        "docker inspect --format '{{range .Mounts}}{{.Destination}}|{{end}}' ${container}" \
        2>/dev/null || echo "")
    if echo "${mounted}" | grep -qF "${path}|"; then
        _hc_record "OK"   "${node}" "mount" "${container} → ${path}"
    else
        _hc_record "FAIL" "${node}" "mount" "${container} → ${path} (MISSING)"
    fi
}

run_healthcheck() {
    local node_filter="${1:-}"
    local full_report="${2:-false}"

    preflight_admin || return 1

    HC_RESULTS=()
    HC_PASS=0
    HC_FAIL=0

    log_info "Reading infrastructure from: ${ANSIBLE_INVENTORY}"
    [[ -n "${node_filter}" ]] && log_info "Node filter: ${node_filter}"
    echo ""

    local CENTRAL_HOST ANSIBLE_USER CENTRAL_INSTALL_DIR WORKER_INSTALL_DIR
    local CENTRAL_API_PORT CENTRAL_DRV_PORT WORKER_REG_PORT WORKER_JOB_PORT
    local WORKER_IPS=() WORKER_HOSTNAMES=()

    CENTRAL_HOST=$(_hc_ansible_var        "central" "ansible_host")
    ANSIBLE_USER=$(_hc_ansible_var        "central" "ansible_user")
    CENTRAL_INSTALL_DIR=$(_hc_ansible_var "central" "brane_central_install_dir")
    WORKER_INSTALL_DIR=$(_hc_ansible_var  "workers" "brane_worker_install_dir")

    CENTRAL_API_PORT=$(_hc_ansible_var "central" "brane_api_port")
    CENTRAL_DRV_PORT=$(_hc_ansible_var "central" "brane_drv_port")
    WORKER_REG_PORT=$(_hc_ansible_var  "workers" "brane_reg_port")
    WORKER_JOB_PORT=$(_hc_ansible_var  "workers" "brane_job_port")

    [[ -z "${CENTRAL_API_PORT}" ]] && CENTRAL_API_PORT="50051"
    [[ -z "${CENTRAL_DRV_PORT}" ]] && CENTRAL_DRV_PORT="50053"
    [[ -z "${WORKER_REG_PORT}"  ]] && WORKER_REG_PORT="50051"
    [[ -z "${WORKER_JOB_PORT}"  ]] && WORKER_JOB_PORT="50052"

    while IFS= read -r line; do
        [[ -n "${line}" ]] && WORKER_IPS+=("${line}")
    done <<< "$(_hc_ansible_var_all "workers" "ansible_host")"

    while IFS= read -r line; do
        [[ -n "${line}" ]] && WORKER_HOSTNAMES+=("${line}")
    done <<< "$(_hc_ansible_var_all "workers" "inventory_hostname")"

    if [[ -z "${CENTRAL_HOST}" ]]; then
        log_error "Could not resolve central host from inventory."
        press_enter
        return 1
    fi

    echo -e "  ${YELLOW}Central     :${NC} ${CENTRAL_HOST}"
    echo -e "  ${YELLOW}Workers     :${NC} ${WORKER_IPS[*]:-none}"
    echo -e "  ${YELLOW}Brane user  :${NC} ${ANSIBLE_USER}"
    echo ""

    _hc_should_check() { [[ -z "${node_filter}" || "${node_filter}" == "$1" ]]; }

    # ── Central node ──────────────────────────────────────
    if _hc_should_check "central"; then
        log_info "Checking central node (${CENTRAL_HOST})..."
        local CDIR="${CENTRAL_INSTALL_DIR}"

        _hc_check_container "central" "${CENTRAL_HOST}" "brane-api"
        _hc_check_container "central" "${CENTRAL_HOST}" "brane-drv"
        _hc_check_container "central" "${CENTRAL_HOST}" "brane-plr"
        _hc_check_container "central" "${CENTRAL_HOST}" "brane-prx"

        _hc_check_port "central" "${CENTRAL_HOST}" "${CENTRAL_API_PORT}" "brane-api"
        _hc_check_port "central" "${CENTRAL_HOST}" "${CENTRAL_DRV_PORT}" "brane-drv"

        _hc_check_mount "central" "${CENTRAL_HOST}" "brane-api" "/node.yml"
        _hc_check_mount "central" "${CENTRAL_HOST}" "brane-api" "${CDIR}/packages"
        _hc_check_mount "central" "${CENTRAL_HOST}" "brane-api" "${CDIR}/config/infra.yml"
        _hc_check_mount "central" "${CENTRAL_HOST}" "brane-api" "${CDIR}/config/certs"
        _hc_check_mount "central" "${CENTRAL_HOST}" "brane-drv" "/node.yml"
        _hc_check_mount "central" "${CENTRAL_HOST}" "brane-drv" "${CDIR}/config/certs"
        _hc_check_mount "central" "${CENTRAL_HOST}" "brane-drv" "${CDIR}/config/infra.yml"
        _hc_check_mount "central" "${CENTRAL_HOST}" "brane-plr" "/node.yml"
        _hc_check_mount "central" "${CENTRAL_HOST}" "brane-plr" "${CDIR}/config/infra.yml"
        _hc_check_mount "central" "${CENTRAL_HOST}" "brane-prx" "/node.yml"
        _hc_check_mount "central" "${CENTRAL_HOST}" "brane-prx" "${CDIR}/config/proxy.yml"
        _hc_check_mount "central" "${CENTRAL_HOST}" "brane-prx" "${CDIR}/config/certs"
    fi

    # ── Worker nodes ──────────────────────────────────────
    local i=0
    while [[ $i -lt ${#WORKER_IPS[@]} ]]; do
        local HOST="${WORKER_IPS[$i]}"
        local NODE="${WORKER_HOSTNAMES[$i]}"
        local WDIR="${WORKER_INSTALL_DIR}"
        local LOCATION_ID
        LOCATION_ID=$(_hc_ansible_var "${NODE}" "location_id")
        if [[ -z "${LOCATION_ID}" ]]; then
            _hc_record "FAIL" "${NODE}" "configuration" "location_id is missing from inventory"
            i=$((i + 1))
            continue
        fi

        local JOB_NAME="brane-job-${LOCATION_ID}"
        local CHK_NAME="brane-chk-${LOCATION_ID}"

        if _hc_should_check "${NODE}"; then
            log_info "Checking worker node: ${NODE} (${HOST})..."

            _hc_check_container "${NODE}" "${HOST}" "brane-prx"
            _hc_check_container "${NODE}" "${HOST}" "brane-reg"
            _hc_check_container "${NODE}" "${HOST}" "${JOB_NAME}"
            _hc_check_container "${NODE}" "${HOST}" "${CHK_NAME}"

            _hc_check_port "${NODE}" "${HOST}" "${WORKER_REG_PORT}" "brane-reg"
            _hc_check_port "${NODE}" "${HOST}" "${WORKER_JOB_PORT}" "brane-chk / brane-job shared endpoint"

            _hc_check_mount "${NODE}" "${HOST}" "brane-prx"    "/node.yml"
            _hc_check_mount "${NODE}" "${HOST}" "brane-prx"    "${WDIR}/config/certs"
            _hc_check_mount "${NODE}" "${HOST}" "brane-reg"    "/node.yml"
            _hc_check_mount "${NODE}" "${HOST}" "brane-reg"    "${WDIR}/config/certs"
            _hc_check_mount "${NODE}" "${HOST}" "brane-reg"    "${WDIR}/config/secrets"
            _hc_check_mount "${NODE}" "${HOST}" "brane-reg"    "${WDIR}/policies.db"
            _hc_check_mount "${NODE}" "${HOST}" "brane-reg"    "${WDIR}/data"
            _hc_check_mount "${NODE}" "${HOST}" "brane-reg"    "${WDIR}/results"
            _hc_check_mount "${NODE}" "${HOST}" "${CHK_NAME}"  "/node.yml"
            _hc_check_mount "${NODE}" "${HOST}" "${CHK_NAME}"  "${WDIR}/config/certs"
            _hc_check_mount "${NODE}" "${HOST}" "${CHK_NAME}"  "${WDIR}/config/secrets"
            _hc_check_mount "${NODE}" "${HOST}" "${CHK_NAME}"  "/home/brane/policy/policies.db"
            _hc_check_mount "${NODE}" "${HOST}" "${JOB_NAME}"  "/node.yml"
            _hc_check_mount "${NODE}" "${HOST}" "${JOB_NAME}"  "${WDIR}/config/certs"
            _hc_check_mount "${NODE}" "${HOST}" "${JOB_NAME}"  "${WDIR}/packages"
            _hc_check_mount "${NODE}" "${HOST}" "${JOB_NAME}"  "${WDIR}/data"
            _hc_check_mount "${NODE}" "${HOST}" "${JOB_NAME}"  "${WDIR}/results"
            _hc_check_mount "${NODE}" "${HOST}" "${JOB_NAME}"  "/var/run/docker.sock"
        fi

        i=$((i + 1))
    done

    # ── Report ────────────────────────────────────────────
    echo ""
    echo -e "${CYAN}$(printf '─%.0s' $(seq 1 70))${NC}"
    echo -e "  ${BOLD}Health report — $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo -e "${CYAN}$(printf '─%.0s' $(seq 1 70))${NC}"
    echo ""

    if [[ "${full_report}" == "true" ]]; then
        for line in "${HC_RESULTS[@]}"; do
            echo -e "  ${line}"
        done
        echo ""
        echo -e "${CYAN}$(printf '─%.0s' $(seq 1 70))${NC}"
        echo ""
    fi

    local ALL_NODES=("central")
    for h in "${WORKER_HOSTNAMES[@]}"; do ALL_NODES+=("${h}"); done

    for NODE in "${ALL_NODES[@]}"; do
        _hc_should_check "${NODE}" || continue
        for CAT in container port mount; do
            local CAT_PASS=0 CAT_FAIL=0
            for line in "${HC_RESULTS[@]}"; do
                echo "${line}" | grep -q "\[${NODE}\]" || continue
                echo "${line}" | grep -q "\[${CAT}\]"  || continue
                if echo "${line}" | grep -q "\[OK\]"; then
                    CAT_PASS=$((CAT_PASS + 1))
                else
                    CAT_FAIL=$((CAT_FAIL + 1))
                fi
            done
            if [[ "${CAT_FAIL}" -gt 0 ]]; then
                echo -e "  ${RED}[FAIL]${NC} ${NODE} | ${CAT}: ${CAT_PASS} ok, ${CAT_FAIL} failed"
            else
                echo -e "  ${GREEN}[OK]${NC}   ${NODE} | ${CAT}: ${CAT_PASS} ok"
            fi
        done
    done

    echo ""
    echo -e "  ${BOLD}Total: ${GREEN}${HC_PASS} passed${NC}  ${BOLD}${RED}${HC_FAIL} failed${NC}"
    echo -e "${CYAN}$(printf '─%.0s' $(seq 1 70))${NC}"
    echo ""

    if [[ "${HC_FAIL}" -gt 0 ]]; then
        log_error "Deployment is UNHEALTHY."
        [[ "${full_report}" != "true" ]] && \
            echo "  → Re-run with full report (option 13) for details."
    else
        log_success "Deployment is HEALTHY."
    fi
}

# ==========================================
# CERTIFICATE OPERATIONS
# ==========================================

gen_client_cert() {
    echo ""
    log_info "Issue a Brane user certificate bundle."
    echo ""
    local cert_script="${SCRIPT_DIR}/brane_gen_cert.sh"
    if [[ ! -f "${cert_script}" ]]; then
        log_error "Certificate generation script not found: ${cert_script}"
        press_enter
        return 1
    fi
    run_cmd "bash '${cert_script}' --inventory '${ANSIBLE_INVENTORY}'"
    press_enter
}

list_certs() {
    run_cmd "brane certs list"
    press_enter
}

add_certs() {
    echo ""
    log_info "Add certificates to a Brane instance."
    echo ""
    log_info "Select target instance:"
    _pick_instance || { press_enter; return 1; }

    echo ""
    local USER_DOMAIN CA_PATH CLIENT_PATH CLIENT_KEY_PATH
    read -r    -p "  Domain (IP or hostname of the worker node): " USER_DOMAIN
    read -r -e -p "  Path to ca.pem:                             " CA_PATH
    read -r -e -p "  Path to client.pem:                         " CLIENT_PATH
    read -r -e -p "  Path to client-key.pem:                     " CLIENT_KEY_PATH

    if [[ -z "${USER_DOMAIN}" || -z "${CA_PATH}" || -z "${CLIENT_PATH}" || -z "${CLIENT_KEY_PATH}" ]]; then
        log_error "All fields are required. Aborting."
        press_enter
        return 1
    fi

    run_cmd "brane certs add '${CA_PATH}' '${CLIENT_PATH}' '${CLIENT_KEY_PATH}' \
--instance '${SEL_INSTANCE}' --domain '${USER_DOMAIN}'"
    press_enter
}

# ==========================================
# TOKEN GENERATION
# ==========================================

gen_policy_token() {
    echo ""
    log_info "Generate a policy-manager token on a domain worker."
    echo ""
    echo "  The domain ID becomes the token's SYSTEM claim."
    echo "  The worker inventory host selects where the token is signed."
    echo ""

    local name domain_id worker_alias validity output_path
    local repo_root token_dir default_output
    local worker_json connection worker_host worker_user
    local remote_token remote_cmd

    read -r -p "  Policy manager name (e.g. alice)            : " name
    read -r -p "  Domain ID / SYSTEM claim (e.g. ab-02...)     : " domain_id
    read -r -p "  Worker inventory host (e.g. worker-vm-2)    : " worker_alias
    read -r -p "  Validity period [default: 30d]              : " validity
    validity="${validity:-30d}"

    if [[ -z "${name}" || -z "${domain_id}" || -z "${worker_alias}" ]]; then
        log_error "Policy-manager name, domain ID, and worker inventory host are required."
        press_enter
        return 1
    fi

    if [[ ! "${name}" =~ ^[A-Za-z0-9._-]+$ ]] \
        || [[ ! "${domain_id}" =~ ^[A-Za-z0-9._:-]+$ ]] \
        || [[ ! "${worker_alias}" =~ ^[A-Za-z0-9._-]+$ ]]; then
        log_error "Name, domain ID, and worker alias may contain only letters, digits, dots, underscores, hyphens, and (for the domain ID) colons."
        press_enter
        return 1
    fi

    repo_root="$(cd "${SCRIPT_DIR}/.." && pwd)"
    token_dir="${repo_root}/policy_tokens"
    default_output="${token_dir}/policy_token_${name}_${domain_id}.json"

    read -r -e -p "  Output path [default: ${default_output}]: " output_path
    output_path="${output_path:-${default_output}}"

    if [[ -e "${output_path}" ]]; then
        log_error "Refusing to overwrite existing token: ${output_path}"
        press_enter
        return 1
    fi

    preflight_admin || return 1
    if ! command -v ansible-inventory >/dev/null 2>&1 \
        || ! command -v ssh >/dev/null 2>&1 \
        || ! command -v scp >/dev/null 2>&1 \
        || ! command -v python3 >/dev/null 2>&1; then
        log_error "Token generation requires ansible-inventory, ssh, scp, and python3."
        press_enter
        return 1
    fi

    if ! worker_json="$(ansible-inventory -i "${ANSIBLE_INVENTORY}" --host "${worker_alias}")"; then
        log_error "Could not resolve inventory host: ${worker_alias}"
        press_enter
        return 1
    fi

    connection="$(
        python3 -c '
import json, sys
host = json.load(sys.stdin)
print("{}|{}".format(host.get("ansible_host", ""), host.get("ansible_user", "")))
' <<< "${worker_json}"
    )"
    IFS='|' read -r worker_host worker_user <<< "${connection}"

    if [[ -z "${worker_host}" || -z "${worker_user}" ]]; then
        log_error "Inventory host '${worker_alias}' has no ansible_host or ansible_user."
        press_enter
        return 1
    fi

    mkdir -p "$(dirname "${output_path}")"
    remote_token="/tmp/brane-policy-token-${name}-$(date +%s)-${RANDOM}.json"

    printf -v remote_cmd \
        'set -eu; umask 077; cd "$HOME/brane-worker"; "$HOME/.local/bin/branectl" generate policy_token %q %q %q --secret-path ./config/secrets/policy_expert_secret.json --path %q; chmod 600 %q' \
        "${name}" "${domain_id}" "${validity}" "${remote_token}" "${remote_token}"

    echo ""
    log_info "Domain claim : ${domain_id}"
    log_info "Worker       : ${worker_alias} (${worker_user}@${worker_host})"

    if ! run_remote "${worker_host}" "${worker_user}" "${remote_cmd}"; then
        ssh -o StrictHostKeyChecking=no "${worker_user}@${worker_host}" \
            "rm -f -- '${remote_token}'" >/dev/null 2>&1 || true
        press_enter
        return 1
    fi

    log_info "Copying token to: ${output_path}"
    if ! scp -o StrictHostKeyChecking=no \
        "${worker_user}@${worker_host}:${remote_token}" "${output_path}"; then
        log_error "Token copy failed; removing the remote temporary token."
        ssh -o StrictHostKeyChecking=no "${worker_user}@${worker_host}" \
            "rm -f -- '${remote_token}'" >/dev/null 2>&1 || true
        press_enter
        return 1
    fi

    chmod 600 "${output_path}"
    if ! ssh -o StrictHostKeyChecking=no "${worker_user}@${worker_host}" \
        "rm -f -- '${remote_token}'"; then
        log_error "Local token was saved, but remote temporary-token cleanup failed: ${remote_token}"
        press_enter
        return 1
    fi

    echo ""
    log_success "Token saved securely to: ${output_path}"
    echo "  → Send this file securely to the policy manager."
    echo "  → It is ignored by Git; do not commit it."
    press_enter
}

# ==========================================
# INSTANCE OPERATIONS
# ==========================================

select_instance_menu() {
    echo ""
    log_info "Select a Brane instance to activate:"
    echo ""
    _pick_instance || { press_enter; return 1; }
    run_cmd "brane instance select '${SEL_INSTANCE}'"
    press_enter
}

# ==========================================
# ANSIBLE DEPLOYMENT
# ==========================================

run_playbook() {
    local tags="${1:-}"
    local extra_args="${2:-}"
    preflight_admin || return 1
    if [[ -n "${tags}" ]]; then
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' \
--tags '${tags}' ${extra_args}"
    else
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' ${extra_args}"
    fi
    press_enter
}

custom_tags() {
    preflight_admin || return 1
    echo ""
    log_info "Available tags: ${ALL_TAGS}"
    read -r -p "  Enter tags (comma-separated) [default: ${ALL_TAGS}]: " USER_TAGS
    USER_TAGS="${USER_TAGS:-${ALL_TAGS}}"
    run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' \
--tags '${USER_TAGS}'"
    press_enter
}

dry_run() {
    preflight_admin || return 1
    echo ""
    log_info "Available tags: ${ALL_TAGS}"
    read -r -p "  Enter tags for dry run [leave blank for all]: " USER_TAGS
    if [[ -z "${USER_TAGS}" ]]; then
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' \
--check --diff"
    else
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' \
--check --diff --tags '${USER_TAGS}'"
    fi
    press_enter
}

# ==========================================
# PACKAGE & WORKFLOW OPERATIONS
# ==========================================

build_package() {
    echo ""
    log_info "Building package: ${PACKAGE_NAME}"
    if [[ ! -f "${PACKAGE_DIR}/${PACKAGE_NAME}/${CONTAINER_YML}" ]]; then
        log_error "container.yml not found: ${PACKAGE_DIR}/${PACKAGE_NAME}/${CONTAINER_YML}"
        press_enter
        return 1
    fi
    if [[ "$(uname)" == "Darwin" ]]; then
        local build_script="${SCRIPT_DIR}/package_build_macOS.sh"
        run_cmd "'${build_script}' '${PACKAGE_DIR}/${PACKAGE_NAME}/${CONTAINER_YML}'"
    else
        run_cmd "brane package build --arch x86_64 \
'${PACKAGE_DIR}/${PACKAGE_NAME}/${CONTAINER_YML}'"
    fi
    press_enter
}

gen_docs() {
    log_info "Generating Brane CLI help documentation..."
    {
        echo "# Brane CLI Help Documentation"
        echo ""
        echo "## Top-Level Help"
        echo ""
        echo '```text'
        brane --help 2>&1 || echo "(brane CLI not found)"
        echo '```'
        for cmd in certs instance package workflow data; do
            echo ""
            echo "## brane ${cmd}"
            echo ""
            echo '```text'
            brane "${cmd}" --help 2>&1 || echo "(brane CLI not found)"
            echo '```'
        done
    } > brane_all_helps.md
    log_success "Saved to: brane_all_helps.md"
    press_enter
}

# ==========================================
# MENU LOOP
# ==========================================

while true; do
    clear
    section_header "BRANE — Admin"

    echo -e "  ${YELLOW}Inventory :${NC} ${ANSIBLE_INVENTORY}"
    echo -e "  ${YELLOW}Host      :${NC} ${HOST_IP}"
    echo -e "  ${YELLOW}Package   :${NC} ${PACKAGE_NAME}  v${PACKAGE_VERSION}"
    echo ""

    section_divider "1. Ansible Deployment"
    echo    "   Recommended order: prerequisites → branectl → workers"
    echo    "                      → central → certs → start → smoke"
    echo ""
    echo    "   1)  Full deployment (all tags)"
    echo    "   2)  Prerequisites only"
    echo    "   3)  Install branectl only"
    echo    "   4)  Configure workers only"
    echo    "   5)  Configure central only"
    echo    "   6)  Exchange node certificates"
    echo    "   7)  Start services"
    echo    "   8)  Run smoke test"
    echo    "   9)  Custom tags"
    echo    "  10)  Dry run / check mode"
    echo    "  11)  Syntax check"
    echo ""

    section_divider "2. Health Checks"
    echo    "  12)  Health check — all nodes (summary)"
    echo    "  13)  Health check — all nodes (full report)"
    echo    "  14)  Health check — central node only"
    echo    "  15)  Health check — single worker (prompt)"
    echo    "  16)  Connectivity test (ports)"
    echo ""

    section_divider "3. Certificates"
    echo    "  17)  Issue a user certificate bundle"
    echo    "  18)  List certificates"
    echo    "  19)  Add certificates to instance"
    echo ""

    section_divider "4. Tokens"
    echo    "  20)  Generate policy expert token for policy manager"
    echo ""

    section_divider "5. Instance"
    echo    "  21)  List instances"
    echo    "  22)  Select active instance"
    echo ""

    section_divider "6. Packages & Workflows"
    echo    "  23)  Build package"
    echo    "  24)  Load package"
    echo    "  25)  List packages"
    echo    "  26)  Test package locally"
    echo    "  27)  Push package to remote registry"
    echo    "  28)  Run local workflow"
    echo    "  29)  Run remote workflow"
    echo    "  30)  Build dataset"
    echo ""

    section_divider "7. Docs"
    echo    "  31)  Generate Brane CLI help documentation"
    echo ""

    echo -e "  ────────────────────────────────────────────────────"
    echo    "   q)  Back to main menu"
    echo ""
    read -r -p "  Choose an option [1-31 or q]: " choice
    echo ""

    case "${choice}" in
    1)  run_playbook ""                  ;;
    2)  run_playbook "prerequisites"     ;;
    3)  run_playbook "branectl"          ;;
    4)  run_playbook "workers"           ;;
    5)  run_playbook "central"           ;;
    6)  run_playbook "certs"             ;;
    7)  run_playbook "start"             ;;
    8)  run_playbook "smoke"             ;;
    9)  custom_tags                      ;;
    10) dry_run                          ;;
    11) preflight_admin && \
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' \
'${ANSIBLE_PLAYBOOK}' --syntax-check" && press_enter ;;

    12) run_healthcheck "" "false"       ; press_enter ;;
    13) run_healthcheck "" "true"        ; press_enter ;;
    14) run_healthcheck "central" "true" ; press_enter ;;
    15)
        echo ""
        log_info "Available worker nodes:"
        _hc_ansible_var_all "workers" "inventory_hostname"
        echo ""
        read -r -p "  Enter worker hostname: " wnode
        run_healthcheck "${wnode}" "true"
        press_enter
        ;;
    16)
        log_info "Testing connectivity to ${HOST_IP}..."
        check_port "${HOST_IP}" "${PORT_REGISTRY}" "Registry (${HOST_IP}:${PORT_REGISTRY})"
        check_port "${HOST_IP}" "${PORT_REPL}"     "Driver   (${HOST_IP}:${PORT_REPL})"
        press_enter
        ;;

    17) gen_client_cert   ;;
    18) list_certs        ;;
    19) add_certs         ;;

    20) gen_policy_token  ;;

    21) run_cmd "brane instance list" ; press_enter ;;
    22) select_instance_menu          ;;

    23) build_package                 ;;
    24) run_cmd "brane package load '${PACKAGE_NAME}'"                         ; press_enter ;;
    25) run_cmd "brane package list"                                            ; press_enter ;;
    26) run_cmd "brane package test '${PACKAGE_NAME}'"                         ; press_enter ;;
    27) run_cmd "brane package push '${PACKAGE_NAME}:${PACKAGE_VERSION}'"      ; press_enter ;;
    28) run_cmd "brane workflow run '${BRANE_USER:-test}' '${WORKFLOW_PATH}'"  ; press_enter ;;
    29) run_cmd "brane workflow run --remote '${BRANE_USER:-test}' '${WORKFLOW_PATH}'" ; press_enter ;;
    30)
        echo ""
        log_info "Preparing to build a dataset..."
        read -r -e -p "  Path to data.yml [default: datasets/minmax/data/data.yml]: " DATA_YML
        DATA_YML="${DATA_YML:-datasets/minmax/data/data.yml}"
        if [[ -f "${DATA_YML}" ]]; then
            run_cmd "brane data build --debug '${DATA_YML}'"
        else
            log_error "File not found: ${DATA_YML}"
        fi
        press_enter
        ;;

    31) gen_docs ;;

    q|Q)
        exec bash "${SCRIPT_DIR}/brane_main.sh"
        ;;
    *)
        log_error "Invalid option '${choice}'."
        sleep 1
        ;;
    esac
done

