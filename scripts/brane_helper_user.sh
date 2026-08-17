#!/usr/bin/env bash
# =============================================================
# brane_helper_user.sh
# Version : 2.4.0
# Date    : 2026-08-17
# Desc    : Brane helper for end users.
# Usage   : bash scripts/brane_helper_user.sh
#           (or via brane_main.sh → option 1)
#
# Expected repo layout (auto-detected):
#   packages/<name>/container.yml
#   certs/<node>/ca.pem  client-id.pem  (or client.pem / client-key.pem)
#   datasets/<name>/data/data.yml
# =============================================================

set -o nounset
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${SCRIPT_DIR}/brane_lib.sh"
load_config_soft "${SCRIPT_DIR}"

CERTS_DIR="${REPO_ROOT}/certs"
DATASETS_DIR="${REPO_ROOT}/datasets"
PACKAGES_DIR="${REPO_ROOT}/packages"

# ==========================================
# HELPERS
# ==========================================

_list_subdirs() {
    local base="$1" indent="${2:-    }"
    local found=0
    while IFS= read -r d; do
        printf '%s• %s\n' "${indent}" "$(basename "${d}")"
        found=1
    done < <(find "${base}" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | sort)
    [[ "${found}" -eq 0 ]] && printf '%s(none)\n' "${indent}"
}

_pick_subdir() {
    local base="$1" prompt="$2"
    local dirs=()
    while IFS= read -r d; do
        dirs+=("$(basename "${d}")")
    done < <(find "${base}" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | sort)

    if [[ "${#dirs[@]}" -eq 0 ]]; then
        log_warn "No subdirectories found in ${base}"
        return 1
    fi

    local idx=0
    while [[ $idx -lt ${#dirs[@]} ]]; do
        printf '    [%d] %s\n' "$((idx+1))" "${dirs[$idx]}"
        idx=$((idx+1))
    done
    printf '\n'

    local choice
    while true; do
        read -r -p "  ${prompt} [1-${#dirs[@]}]: " choice
        [[ "${choice}" =~ ^[0-9]+$ ]] && \
            [[ "${choice}" -ge 1 ]] && \
            [[ "${choice}" -le "${#dirs[@]}" ]] && break
        log_error "Invalid choice."
    done
    SEL_DIR="${dirs[$((choice-1))]}"
}

# ==========================================
# 1. CHECK ENVIRONMENT & REPORT
# ==========================================

check_environment() {
    clear
    section_header "Environment Check & Report"

    printf '  %sRequired tools%s\n\n' "${BOLD}" "${NC}"
    local tools_ok=0
    check_bin "brane"  "Install from: https://github.com/epi-project/brane/releases" || tools_ok=1
    check_bin "docker" "Install from: https://docs.docker.com/get-docker/"           || tools_ok=1
    printf '\n'

    printf '  %sConnectivity%s\n\n' "${BOLD}" "${NC}"
    local conn_ok=0
    if [[ -n "${HOST_IP}" ]]; then
        check_port "${HOST_IP}" "${PORT_REGISTRY}" "Registry (${HOST_IP}:${PORT_REGISTRY})" || conn_ok=1
        check_port "${HOST_IP}" "${PORT_REPL}"     "Driver   (${HOST_IP}:${PORT_REPL})"     || conn_ok=1
    else
        log_warn "No HOST_IP configured — skipping port check."
        log_warn "Use option 2 to add an instance first."
        conn_ok=1
    fi
    printf '\n'

    printf '  %sBrane instances%s\n\n' "${BOLD}" "${NC}"
    local instance_out=""
    if command -v brane &>/dev/null; then
        printf '  %s▶%s brane instance list\n' "${YELLOW}" "${NC}"
        printf '  %s\n' "$(printf '─%.0s' $(seq 1 50))"
        instance_out=$(brane instance list 2>/dev/null || true)
        if [[ -n "${instance_out}" ]]; then
            printf '%s\n' "${instance_out}" | sed 's/^/    /'
        else
            log_warn "No instances found."
        fi
    fi
    printf '\n'

    printf '  %sDirectories%s  (repo: %s)\n\n' "${BOLD}" "${NC}" "${REPO_ROOT}"
    local dirs_missing=0

    if [[ -d "${PACKAGES_DIR}" ]]; then
        printf '  %s✓%s packages/\n' "${GREEN}" "${NC}"
        _list_subdirs "${PACKAGES_DIR}" "      "
    else
        printf '  %s✗%s packages/  not found\n' "${RED}" "${NC}"
        dirs_missing=1
    fi
    printf '\n'

    if [[ -d "${CERTS_DIR}" ]]; then
        printf '  %s✓%s certs/\n' "${GREEN}" "${NC}"
        _list_subdirs "${CERTS_DIR}" "      "
    else
        printf '  %s✗%s certs/  not found\n' "${RED}" "${NC}"
        dirs_missing=1
    fi
    printf '\n'

    if [[ -d "${DATASETS_DIR}" ]]; then
        printf '  %s✓%s datasets/\n' "${GREEN}" "${NC}"
        _list_subdirs "${DATASETS_DIR}" "      "
    else
        printf '  %s✗%s datasets/  not found\n' "${RED}" "${NC}"
        dirs_missing=1
    fi
    printf '\n'

    if [[ "${dirs_missing}" -eq 1 ]]; then
        read -r -p "  Create missing directories now? [Y/n]: " yn
        if [[ "${yn}" != "n" && "${yn}" != "N" ]]; then
            for d in packages certs datasets; do
                [[ ! -d "${REPO_ROOT}/${d}" ]] && mkdir -p "${REPO_ROOT}/${d}" \
                    && log_success "Created: ${REPO_ROOT}/${d}"
            done
        fi
        printf '\n'
    fi

    printf '  %sLocal brane packages%s\n\n' "${BOLD}" "${NC}"
    local pkg_out=""
    if command -v brane &>/dev/null; then
        printf '  %s▶%s brane package list\n' "${YELLOW}" "${NC}"
        printf '  %s\n' "$(printf '─%.0s' $(seq 1 50))"
        pkg_out=$(brane package list 2>/dev/null || true)
        if [[ -n "${pkg_out}" ]]; then
            printf '%s\n' "${pkg_out}" | sed 's/^/    /'
        else
            log_warn "No brane packages built yet. Use option 4 to build one."
        fi
    fi
    printf '\n'

    printf '%s%s%s\n' "${CYAN}" "$(printf '─%.0s' $(seq 1 54))" "${NC}"
    printf '  %sSummary%s\n' "${BOLD}" "${NC}"
    printf '%s%s%s\n\n' "${CYAN}" "$(printf '─%.0s' $(seq 1 54))" "${NC}"

    [[ "${tools_ok}"  -eq 0 ]] \
        && printf '  %s✓%s Tools       : all installed\n'                   "${GREEN}" "${NC}" \
        || printf '  %s✗%s Tools       : some missing\n'                    "${RED}"   "${NC}"
    [[ "${conn_ok}"   -eq 0 ]] \
        && printf '  %s✓%s Connection  : central node reachable\n'          "${GREEN}" "${NC}" \
        || printf '  %s✗%s Connection  : not reachable or not configured\n' "${RED}"   "${NC}"
    [[ -n "${instance_out}" ]] \
        && printf '  %s✓%s Instances   : configured\n'                      "${GREEN}" "${NC}" \
        || printf '  %s✗%s Instances   : none — use option 2\n'             "${RED}"   "${NC}"
    [[ -d "${PACKAGES_DIR}" ]] \
        && printf '  %s✓%s packages/   : found\n'  "${GREEN}" "${NC}" \
        || printf '  %s✗%s packages/   : missing\n' "${RED}"  "${NC}"
    [[ -d "${CERTS_DIR}" ]] \
        && printf '  %s✓%s certs/      : found\n'  "${GREEN}" "${NC}" \
        || printf '  %s✗%s certs/      : missing\n' "${RED}"  "${NC}"
    [[ -d "${DATASETS_DIR}" ]] \
        && printf '  %s✓%s datasets/   : found\n'  "${GREEN}" "${NC}" \
        || printf '  %s✗%s datasets/   : missing\n' "${RED}"  "${NC}"

    printf '\n'
    printf '%s%s%s\n' "${CYAN}" "$(printf '─%.0s' $(seq 1 54))" "${NC}"
    press_enter
}

# ==========================================
# 2. ADD INSTANCE
# ==========================================

add_instance() {
    clear
    section_header "Add Brane Instance"
    printf '\n'
    printf '  Your admin provides:\n'
    printf '    • Central node IP or hostname\n'
    printf '    • Instance name\n'
    printf '\n'

    local host instance_name
    read -r -p "  Central node IP or hostname : " host
    read -r -p "  Instance name               : " instance_name

    if [[ -z "${host}" || -z "${instance_name}" ]]; then
        log_error "Both fields are required."
        press_enter
        return 1
    fi

    run_cmd "brane instance add '${host}' --name '${instance_name}' --use --unchecked --force"

    if [[ $? -eq 0 ]]; then
        HOST_IP="${host}"
        INSTANCE_NAME="${instance_name}"
        if [[ -f "${SCRIPT_DIR}/.brane_helper.env" ]]; then
            sed -i.bak \
                -e "s|^HOST_IP=.*|HOST_IP=${host}|" \
                -e "s|^INSTANCE_NAME=.*|INSTANCE_NAME=${instance_name}|" \
                "${SCRIPT_DIR}/.brane_helper.env" 2>/dev/null \
                || log_warn "Could not update .brane_helper.env — update it manually."
        fi
        log_success "Instance '${instance_name}' added and set as active."
    fi

    press_enter
}

# ==========================================
# 3. ADD CERTIFICATE
# ==========================================

add_certificate() {
    clear
    section_header "Add Certificate"
    printf '\n'
    printf '  Certificates live in:  %s/<node>/\n' "${CERTS_DIR}"
    printf '\n'

    if [[ ! -d "${CERTS_DIR}" ]]; then
        log_warn "certs/ not found: ${CERTS_DIR}"
        read -r -p "  Create it now? [Y/n]: " yn
        [[ "${yn}" == "n" || "${yn}" == "N" ]] && { press_enter; return 1; }
        mkdir -p "${CERTS_DIR}"
        log_success "Created: ${CERTS_DIR}"
        printf '\n'
    fi

    printf '  Existing cert directories:\n'
    _list_subdirs "${CERTS_DIR}"
    printf '\n'

    printf '  Select instance to attach certificate to:\n\n'
    _pick_instance || { press_enter; return 1; }
    printf '\n'

    local worker_domain
    read -r -p "  Worker node IP or hostname : " worker_domain
    [[ -z "${worker_domain}" ]] && { log_error "Worker domain required."; press_enter; return 1; }

    # ── Auto-detect cert files in certs/<worker_domain>/ ──
    local ca_path="" client_path="" client_key_path=""
    local node_dir="${CERTS_DIR}/${worker_domain}"

    if [[ -d "${node_dir}" ]]; then
        log_info "Found cert directory: ${node_dir}"
        printf '  Contents:\n'
        find "${node_dir}" -maxdepth 1 -type f | sort | sed 's/^/    /'
        printf '\n'

        # Classify each .pem file:
        #   ca.pem                → CA cert
        #   *-key.pem             → client private key
        #   client.pem / client-id.pem / client-*.pem (non-key) → client cert
        while IFS= read -r f; do
            local fname
            fname="$(basename "${f}")"
            if [[ "${fname}" == "ca.pem" ]]; then
                ca_path="${f}"
            elif [[ "${fname}" == *-key.pem ]]; then
                client_key_path="${f}"
            elif [[ "${fname}" == client*.pem ]]; then
                client_path="${f}"
            fi
        done < <(find "${node_dir}" -maxdepth 1 -name "*.pem" -type f | sort)

        printf '  Auto-detected:\n'
        printf '    CA cert      : %s\n' "${ca_path:-(not found)}"
        printf '    Client cert  : %s\n' "${client_path:-(not found)}"
        printf '    Client key   : %s\n' "${client_key_path:-(not found)}"
        printf '\n'

        read -r -p "  Use these paths? [Y/n]: " yn
        if [[ "${yn}" == "n" || "${yn}" == "N" ]]; then
            ca_path="" client_path="" client_key_path=""
        fi
    fi

    # Prompt for any still-missing paths
    [[ -z "${ca_path}" ]]         && read -r -e -p "  Path to ca.pem             : " ca_path
    [[ -z "${client_path}" ]]     && read -r -e -p "  Path to client cert (.pem) : " client_path
    [[ -z "${client_key_path}" ]] && read -r -e -p "  Path to client-key.pem     : " client_key_path

    if [[ -z "${ca_path}" || -z "${client_path}" || -z "${client_key_path}" ]]; then
        log_error "All three certificate files are required."
        press_enter
        return 1
    fi

    for f in "${ca_path}" "${client_path}" "${client_key_path}"; do
        if [[ ! -f "${f}" ]]; then
            log_error "File not found: ${f}"
            press_enter
            return 1
        fi
    done

    run_cmd "brane certs add '${ca_path}' '${client_path}' '${client_key_path}' \
--instance '${SEL_INSTANCE}' --domain '${worker_domain}'"

    if [[ $? -ne 0 ]]; then
        printf '\n'
        printf '  Common causes:\n'
        printf '    • Certificate missing keyUsage = digitalSignature\n'
        printf '    • Certificate missing extendedKeyUsage = clientAuth\n'
        printf '    → Ask your admin to regenerate the certificate.\n'
    fi

    press_enter
}

# ==========================================
# 4. BUILD PACKAGE
# ==========================================

build_package() {
    clear
    section_header "Build Package"
    printf '\n'

    if [[ ! -d "${PACKAGES_DIR}" ]]; then
        log_warn "packages/ not found: ${PACKAGES_DIR}"
        read -r -p "  Create it now? [Y/n]: " yn
        [[ "${yn}" == "n" || "${yn}" == "N" ]] && { press_enter; return 1; }
        mkdir -p "${PACKAGES_DIR}"
        log_success "Created: ${PACKAGES_DIR}"
        printf '\n'
    fi

    printf '  Available packages:\n\n'
    _pick_subdir "${PACKAGES_DIR}" "Select package" || { press_enter; return 1; }
    local pkg_name="${SEL_DIR}"
    local container_yml="${PACKAGES_DIR}/${pkg_name}/container.yml"

    if [[ ! -f "${container_yml}" ]]; then
        log_error "container.yml not found: ${container_yml}"
        press_enter
        return 1
    fi

    log_info "Building package: ${pkg_name}"
    printf '\n'

    if [[ "$(uname)" == "Darwin" ]]; then
        local build_script="${SCRIPT_DIR}/package_build_macOS.sh"
        if [[ ! -f "${build_script}" ]]; then
            log_error "macOS build script not found: ${build_script}"
            press_enter
            return 1
        fi
        run_cmd "'${build_script}' '${container_yml}'"
    else
        run_cmd "brane package build --arch x86_64 '${container_yml}'"
    fi

    press_enter
}

# ==========================================
# 5. LIST PACKAGES
# ==========================================

list_packages() {
    clear
    section_header "List Packages"
    printf '\n'
    run_cmd "brane package list"
    press_enter
}

# ==========================================
# 6. LIST INSTANCES
# ==========================================

list_instances() {
    clear
    section_header "List Instances"
    printf '\n'
    run_cmd "brane instance list"
    press_enter
}

# ==========================================
# WORKFLOW PICKER (shared by 7 and 8)
# ==========================================

_pick_workflow() {
    printf '  Available workflows in packages/:\n\n'
    local wf_files=()
    while IFS= read -r f; do
        wf_files+=("${f}")
        printf '    [%d] %s\n' "${#wf_files[@]}" "${f#${REPO_ROOT}/}"
    done < <(find "${PACKAGES_DIR}" -name "*.bs" 2>/dev/null | sort)
    printf '\n'

    if [[ "${#wf_files[@]}" -eq 0 ]]; then
        log_warn "No .bs workflow files found in packages/."
        read -r -e -p "  Enter path to workflow file: " SEL_WORKFLOW
    else
        local wf_choice
        read -r -p "  Select number or type a path: " wf_choice
        if [[ "${wf_choice}" =~ ^[0-9]+$ ]] && \
           [[ "${wf_choice}" -ge 1 ]] && \
           [[ "${wf_choice}" -le "${#wf_files[@]}" ]]; then
            SEL_WORKFLOW="${wf_files[$((wf_choice-1))]}"
        else
            SEL_WORKFLOW="${wf_choice}"
        fi
    fi
}

# ==========================================
# 7. RUN WORKFLOW LOCALLY
# ==========================================

run_local_workflow() {
    clear
    section_header "Run Workflow Locally"
    printf '\n'

    _pick_workflow

    if [[ -z "${SEL_WORKFLOW}" || ! -f "${SEL_WORKFLOW}" ]]; then
        log_error "Workflow file not found: ${SEL_WORKFLOW:-<empty>}"
        press_enter
        return 1
    fi

    local username
    read -r -p "  Username [${BRANE_USER:-test}]: " username
    username="${username:-${BRANE_USER:-test}}"

    run_cmd "brane workflow run '${username}' '${SEL_WORKFLOW}'"
    press_enter
}

# ==========================================
# 8. RUN WORKFLOW REMOTELY
# ==========================================

run_remote_workflow() {
    clear
    section_header "Run Workflow on Remote Domain"
    printf '\n'

    if [[ -z "${HOST_IP}" ]]; then
        log_warn "No instance configured. Use option 2 to add one first."
        press_enter
        return 1
    fi

    log_info "Checking connectivity to ${HOST_IP}..."
    printf '\n'
    local conn_ok=0
    check_port "${HOST_IP}" "${PORT_REGISTRY}" "Registry (${HOST_IP}:${PORT_REGISTRY})" || conn_ok=1
    check_port "${HOST_IP}" "${PORT_REPL}"     "Driver   (${HOST_IP}:${PORT_REPL})"     || conn_ok=1
    printf '\n'

    if [[ "${conn_ok}" -eq 1 ]]; then
        log_warn "Central node not reachable."
        read -r -p "  Submit anyway? [y/N]: " yn
        [[ "${yn}" != "y" && "${yn}" != "Y" ]] && return
    fi

    _pick_workflow

    if [[ -z "${SEL_WORKFLOW}" || ! -f "${SEL_WORKFLOW}" ]]; then
        log_error "Workflow file not found: ${SEL_WORKFLOW:-<empty>}"
        press_enter
        return 1
    fi

    local username
    read -r -p "  Username [${BRANE_USER:-test}]: " username
    username="${username:-${BRANE_USER:-test}}"

    printf '\n'
    log_info "Select the instance to submit to:"
    printf '\n'
    _pick_instance || { press_enter; return 1; }

    printf '\n'
    run_cmd "brane instance select '${SEL_INSTANCE}'"
    run_cmd "brane workflow run --remote '${username}' '${SEL_WORKFLOW}'"

    printf '\n'
    printf '  Note: if execution is denied, the policy manager for\n'
    printf '  that domain needs to activate a policy on the worker node.\n'
    press_enter
}

# ==========================================
# MENU LOOP
# ==========================================

while true; do
    clear
    section_header "BRANE — User"

    printf '  %sInstance :%s %s  (%s)\n' "${YELLOW}" "${NC}" "${INSTANCE_NAME:-not set}" "${HOST_IP:-no host}"
    printf '  %sUsername :%s %s\n'        "${YELLOW}" "${NC}" "${BRANE_USER:-not set}"
    printf '\n'

    section_divider "Status"
    printf '   1)  Check environment, connection & report\n'
    printf '\n'

    section_divider "Setup"
    printf '   2)  Add instance\n'
    printf '   3)  Add certificate\n'
    printf '\n'

    section_divider "Packages"
    printf '   4)  Build package\n'
    printf '   5)  List packages\n'
    printf '\n'

    section_divider "Instances"
    printf '   6)  List instances\n'
    printf '\n'

    section_divider "Workflows"
    printf '   7)  Run workflow locally\n'
    printf '   8)  Run workflow on remote domain\n'
    printf '\n'

    printf '  %s\n' "$(printf '─%.0s' $(seq 1 52))"
    printf '   q)  Back to main menu\n'
    printf '\n'
    read -r -p "  Choose an option [1-8 or q]: " choice
    printf '\n'

    case "${choice}" in
        1) check_environment   ;;
        2) add_instance        ;;
        3) add_certificate     ;;
        4) build_package       ;;
        5) list_packages       ;;
        6) list_instances      ;;
        7) run_local_workflow  ;;
        8) run_remote_workflow ;;
        q|Q)
            exec bash "${SCRIPT_DIR}/brane_main.sh"
            ;;
        *)
            log_error "Invalid option '${choice}'."
            sleep 1
            ;;
    esac
done

