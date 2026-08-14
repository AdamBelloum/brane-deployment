#!/usr/bin/env bash
# brane_helper.sh
# Interactive helper menu for Brane deployment and CLI operations.
#
# Usage:
#   bash scripts/brane_helper.sh
#
# Configuration:
#   Copy scripts/.brane_helper.env.example to scripts/.brane_helper.env
#   and fill in your values before running this script.

set -o nounset
set -o pipefail

# ── PATH ──────────────────────────────────────────────────
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    export PATH="$HOME/.local/bin:$PATH"
fi

# ==========================================
# RESOLVE REPO ROOT & LOAD CONFIG
# ==========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CONFIG_FILE="${BRANE_HELPER_CONFIG:-${SCRIPT_DIR}/.brane_helper.env}"

if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "[ERROR] Config file not found: ${CONFIG_FILE}"
    echo ""
    echo "  Create it from the example:"
    echo "    cp scripts/.brane_helper.env.example scripts/.brane_helper.env"
    echo "    \$EDITOR scripts/.brane_helper.env"
    exit 1
fi

# shellcheck source=/dev/null
source "${CONFIG_FILE}"

# ==========================================
# DEFAULTS
# ==========================================

BRANE_DEPLOY_HOME="${BRANE_DEPLOY_HOME:-${REPO_ROOT}/docker-deployment}"
PACKAGE_DIR="${PACKAGE_DIR:-${REPO_ROOT}/frontend/packages}"

ANSIBLE_INVENTORY="${BRANE_DEPLOY_HOME}/inventories/production/hosts.ini"
ANSIBLE_PLAYBOOK="${BRANE_DEPLOY_HOME}/site.yml"
ALL_TAGS="prerequisites,branectl,workers,central,certs,start,smoke"

PACKAGE_NAME="${PACKAGE_NAME:-hello_world}"
WORKFLOW_NAME="${WORKFLOW_NAME:-hello_world.bs}"
CONTAINER_YML="${CONTAINER_YML:-container.yml}"
PACKAGE_VERSION="${PACKAGE_VERSION:-1.0.0}"
WORKFLOW_PATH="${PACKAGE_DIR}/${PACKAGE_NAME}/${WORKFLOW_NAME}"

HOST_IP="${HOST_IP:?HOST_IP must be set in ${CONFIG_FILE}}"
PORT_REPL="${PORT_REPL:-50053}"
PORT_REGISTRY="${PORT_REGISTRY:-50051}"
INSTANCE_NAME="${INSTANCE_NAME:-my-brane}"

# ==========================================
# COLORS
# ==========================================

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ==========================================
# HELPERS
# ==========================================

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

run_cmd() {
    echo -e "${YELLOW}▶ ${NC}$1"
    echo "----------------------------------------------------"
    bash -c "$1"
}

press_enter() {
    echo ""
    read -r -p "Press [Enter] to return to the menu..."
}

# ==========================================
# PREFLIGHT CHECK
# ==========================================

preflight_check() {
    local missing=0
    [[ ! -f "${ANSIBLE_INVENTORY}" ]]       && log_error "Inventory not found: ${ANSIBLE_INVENTORY}"       && missing=1
    [[ ! -f "${ANSIBLE_PLAYBOOK}" ]]        && log_error "Playbook not found: ${ANSIBLE_PLAYBOOK}"         && missing=1
    ! command -v ansible-playbook &>/dev/null && log_error "ansible-playbook not found. Activate your venv." && missing=1
    if [[ "${missing}" -eq 1 ]]; then
        echo ""
        log_error "Preflight checks failed. Fix the issues above before continuing."
        press_enter
        return 1
    fi
    return 0
}

# ==========================================
# INSTANCE HELPERS
# ==========================================

# Print a numbered list of brane instances and return the selected name in SEL_INSTANCE
_pick_instance() {
    local INSTANCE_LIST
    INSTANCE_LIST=$(brane instance list 2>/dev/null | tail -n +2 | awk '{print $1}' | grep -v '^$')

    if [[ -z "${INSTANCE_LIST}" ]]; then
        log_error "No instances found. Add one first via 'brane instance add'."
        return 1
    fi

    local INSTANCE_NAMES=()
    while IFS= read -r line; do
        [ -n "$line" ] && INSTANCE_NAMES+=("$line")
    done <<< "${INSTANCE_LIST}"

    local idx=0
    while [ $idx -lt ${#INSTANCE_NAMES[@]} ]; do
        printf "    [%d] %s\n" "$((idx+1))" "${INSTANCE_NAMES[$idx]}"
        idx=$((idx + 1))
    done
    echo ""

    local CHOICE
    while true; do
        read -r -p "  Select instance [1-${#INSTANCE_NAMES[@]}]: " CHOICE
        [[ "$CHOICE" =~ ^[0-9]+$ ]] && \
            [ "$CHOICE" -ge 1 ] && [ "$CHOICE" -le "${#INSTANCE_NAMES[@]}" ] && break
        log_error "Invalid choice."
    done

    SEL_INSTANCE="${INSTANCE_NAMES[$((CHOICE-1))]}"
}

select_instance() {
    echo ""
    log_info "Select a Brane instance to activate:"
    echo ""
    _pick_instance || return 1
    run_cmd "brane instance select '${SEL_INSTANCE}'"
}

# ==========================================
# CERTIFICATE HELPERS
# ==========================================

add_certs() {
    echo ""
    log_info "Add certificates to a Brane instance."
    echo ""
    log_info "Select target instance:"
    _pick_instance || return 1

    echo ""
    local USER_DOMAIN CA_PATH CLIENT_PATH CLIENT_KEY_PATH
    read -r    -p "  Domain (IP or hostname of the worker node): " USER_DOMAIN
    read -r -e -p "  Path to ca.pem:                             " CA_PATH
    read -r -e -p "  Path to client.pem:                         " CLIENT_PATH
    read -r -e -p "  Path to client-key.pem:                     " CLIENT_KEY_PATH

    if [[ -z "${USER_DOMAIN}" || -z "${CA_PATH}" || -z "${CLIENT_PATH}" || -z "${CLIENT_KEY_PATH}" ]]; then
        log_error "All fields are required. Aborting."
        return 1
    fi

    run_cmd "brane certs add '${CA_PATH}' '${CLIENT_PATH}' '${CLIENT_KEY_PATH}' \
--instance '${SEL_INSTANCE}' --domain '${USER_DOMAIN}'"
}

gen_client_cert() {
    bash "${SCRIPT_DIR}/brane_gen_cert.sh" --inventory "${ANSIBLE_INVENTORY}"
}

# ==========================================
# MENU LOOP
# ==========================================

while true; do
    clear
    echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║         BRANE DEPLOYMENT HELPER                  ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${YELLOW}Config :${NC} ${CONFIG_FILE}"
    echo -e "  ${YELLOW}Repo   :${NC} ${REPO_ROOT}"
    echo -e "  ${YELLOW}Host   :${NC} ${HOST_IP}"
    echo ""

    # ── Section 1: Deployment ────────────────────────────
    echo -e "${CYAN}  ┌─ 1. Ansible Deployment ──────────────────────────┐${NC}"
    echo    "  │  Recommended order:                               │"
    echo    "  │  prerequisites → branectl → workers → central     │"
    echo    "  │  → certs → start → smoke                          │"
    echo -e "${CYAN}  └───────────────────────────────────────────────────┘${NC}"
    echo    "   1) Full deployment (all tags)"
    echo    "   2) Prerequisites only"
    echo    "   3) Install branectl only"
    echo    "   4) Configure workers only"
    echo    "   5) Configure central only"
    echo    "   6) Exchange certificates (nodes)"
    echo    "   7) Start services"
    echo    "   8) Run smoke test"
    echo    "   9) Custom tags (prompt)"
    echo    "  10) Dry run / check mode"
    echo    "  11) Syntax check"
    echo ""

    # ── Section 2: Certificates ──────────────────────────
    echo -e "${CYAN}  ┌─ 2. Certificates ─────────────────────────────────┐${NC}"
    echo -e "${CYAN}  └───────────────────────────────────────────────────┘${NC}"
    echo    "  12) Generate & fetch client certificate from node"
    echo    "  13) List certificates"
    echo    "  14) Add certificates to instance"
    echo ""

    # ── Section 3: Instance & Connectivity ───────────────
    echo -e "${CYAN}  ┌─ 3. Instance & Connectivity ───────────────────────┐${NC}"
    echo -e "${CYAN}  └───────────────────────────────────────────────────┘${NC}"
    echo    "  15) Test connectivity to central node (${HOST_IP})"
    echo    "  16) List instances"
    echo    "  17) Select active instance"
    echo ""

    # ── Section 4: Packages & Workflows ──────────────────
    echo -e "${CYAN}  ┌─ 4. Packages & Workflows ──────────────────────────┐${NC}"
    echo -e "${CYAN}  └───────────────────────────────────────────────────┘${NC}"
    echo    "  18) Build package   (${CONTAINER_YML})"
    echo    "  19) Load package    (${PACKAGE_NAME})"
    echo    "  20) List packages"
    echo    "  21) Test package locally"
    echo    "  22) Push package to remote registry"
    echo    "  23) Run local workflow"
    echo    "  24) Run remote workflow"
    echo    "  25) Build dataset"
    echo ""

    # ── Section 5: Docs ───────────────────────────────────
    echo -e "${CYAN}  ┌─ 5. Docs ──────────────────────────────────────────┐${NC}"
    echo -e "${CYAN}  └───────────────────────────────────────────────────┘${NC}"
    echo    "  26) Generate Brane CLI help documentation"
    echo ""

    echo -e "  ────────────────────────────────────────────────────"
    echo    "   q) Exit"
    echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
    read -r -p "  Choose an option [1-26 or q]: " choice
    echo ""

    case "${choice}" in

    # ── 1. Ansible Deployment ────────────────────────────

    1)
        preflight_check || continue
        log_info "Running full Brane deployment..."
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}'"
        press_enter
        ;;
    2)
        preflight_check || continue
        log_info "Running prerequisites..."
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' --tags prerequisites"
        press_enter
        ;;
    3)
        preflight_check || continue
        log_info "Installing branectl..."
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' --tags branectl"
        press_enter
        ;;
    4)
        preflight_check || continue
        log_info "Configuring worker nodes..."
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' --tags workers"
        press_enter
        ;;
    5)
        preflight_check || continue
        log_info "Configuring central node..."
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' --tags central"
        press_enter
        ;;
    6)
        preflight_check || continue
        log_info "Exchanging node certificates..."
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' --tags certs"
        press_enter
        ;;
    7)
        preflight_check || continue
        log_info "Starting Brane services..."
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' --tags start"
        press_enter
        ;;
    8)
        preflight_check || continue
        log_info "Running smoke test..."
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' --tags smoke"
        press_enter
        ;;
    9)
        preflight_check || continue
        echo ""
        log_info "Available tags: ${ALL_TAGS}"
        read -r -p "Enter tags (comma-separated) [default: ${ALL_TAGS}]: " USER_TAGS
        USER_TAGS="${USER_TAGS:-${ALL_TAGS}}"
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' --tags '${USER_TAGS}'"
        press_enter
        ;;
    10)
        preflight_check || continue
        echo ""
        log_info "Available tags: ${ALL_TAGS}"
        read -r -p "Enter tags for dry run [leave blank for all]: " USER_TAGS
        if [[ -z "${USER_TAGS}" ]]; then
            run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' --check --diff"
        else
            run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' --check --diff --tags '${USER_TAGS}'"
        fi
        press_enter
        ;;
    11)
        preflight_check || continue
        log_info "Running syntax check..."
        run_cmd "ansible-playbook -i '${ANSIBLE_INVENTORY}' '${ANSIBLE_PLAYBOOK}' --syntax-check"
        press_enter
        ;;

    # ── 2. Certificates ───────────────────────────────────

    12)
        gen_client_cert
        press_enter
        ;;
    13)
        log_info "Listing Brane certificates..."
        run_cmd "brane certs list"
        press_enter
        ;;
    14)
        add_certs
        press_enter
        ;;

    # ── 3. Instance & Connectivity ────────────────────────

    15)
        log_info "Testing connectivity to ${HOST_IP}..."
        run_cmd "nc -vz '${HOST_IP}' '${PORT_REPL}'"
        run_cmd "nc -vz '${HOST_IP}' '${PORT_REGISTRY}'"
        press_enter
        ;;
    16)
        run_cmd "brane instance list"
        press_enter
        ;;
    17)
        select_instance
        press_enter
        ;;

    # ── 4. Packages & Workflows ───────────────────────────

    18)
        if [[ "$(uname)" == "Darwin" ]]; then
            read -r -e -p "Path to macOS build script [default: ${SCRIPT_DIR}/package_build_macOS.sh]: " BUILD_SCRIPT
            BUILD_SCRIPT="${BUILD_SCRIPT:-${SCRIPT_DIR}/package_build_macOS.sh}"
            run_cmd "'${BUILD_SCRIPT}' '${PACKAGE_DIR}/${PACKAGE_NAME}/${CONTAINER_YML}'"
        else
            run_cmd "brane package build --arch x86_64 '${PACKAGE_DIR}/${PACKAGE_NAME}/${CONTAINER_YML}'"
        fi
        press_enter
        ;;
    19)
        run_cmd "brane package load '${PACKAGE_NAME}'"
        press_enter
        ;;
    20)
        run_cmd "brane package list"
        press_enter
        ;;
    21)
        run_cmd "brane package test '${PACKAGE_NAME}'"
        press_enter
        ;;
    22)
        run_cmd "brane package push '${PACKAGE_NAME}:${PACKAGE_VERSION}'"
        press_enter
        ;;
    23)
        run_cmd "brane workflow run test '${WORKFLOW_PATH}'"
        press_enter
        ;;
    24)
        run_cmd "brane workflow run --remote test '${WORKFLOW_PATH}'"
        press_enter
        ;;
    25)
        echo ""
        log_info "Preparing to build a dataset..."
        read -r -e -p "Path to data.yml [default: datasets/minmax/data/data.yml]: " DATA_YML_PATH
        DATA_YML_PATH="${DATA_YML_PATH:-datasets/minmax/data/data.yml}"
        if [[ -f "${DATA_YML_PATH}" ]]; then
            run_cmd "brane data build --debug '${DATA_YML_PATH}'"
        else
            log_error "File '${DATA_YML_PATH}' does not exist. Aborting."
        fi
        press_enter
        ;;

    # ── 5. Docs ───────────────────────────────────────────

    26)
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
        ;;

    q | Q)
        log_success "Exiting. Goodbye!"
        exit 0
        ;;
    *)
        log_error "Invalid option '${choice}'. Please try again."
        sleep 1
        ;;
    esac
done

