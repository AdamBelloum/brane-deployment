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



#!/usr/bin/env bash
# Ensure ~/.local/bin is in PATH for brane/branectl

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
  export PATH="$HOME/.local/bin:$PATH"
  echo "[OK] Added ~/.local/bin to PATH"
else
  echo "[OK] ~/.local/bin already in PATH"
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
# APPLY DEFAULTS (if not set in .env)
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
INSTANCE_DOMAIN="${INSTANCE_DOMAIN:?INSTANCE_DOMAIN must be set in ${CONFIG_FILE}}"
INSTANCE_NAME="${INSTANCE_NAME:-my-brane}"

# ==========================================
# COLORS
# ==========================================

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ==========================================
# HELPERS
# ==========================================

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

run_cmd() {
    echo -e "${YELLOW}Command:${NC} $1"
    echo "----------------------------------------------------"
    # Use bash -c to avoid eval on arbitrary input
    bash -c "$1"
}

press_enter() {
    echo ""
    read -r -p "Press [Enter] to return to the menu..."
}

# ==========================================
# PREFLIGHT CHECKS
# ==========================================

preflight_check() {
    local missing=0

    if [[ ! -f "${ANSIBLE_INVENTORY}" ]]; then
        log_error "Inventory not found: ${ANSIBLE_INVENTORY}"
        missing=1
    fi
    if [[ ! -f "${ANSIBLE_PLAYBOOK}" ]]; then
        log_error "Playbook not found: ${ANSIBLE_PLAYBOOK}"
        missing=1
    fi
    if ! command -v ansible-playbook &>/dev/null; then
        log_error "ansible-playbook not found in PATH. Run: pip install -r docker-deployment/requirements.txt"
        missing=1
    fi

    if [[ "${missing}" -eq 1 ]]; then
        echo ""
        log_error "Preflight checks failed. Fix the issues above before continuing."
        press_enter
        return 1
    fi
    return 0
}

# ==========================================
# MENU LOOP
# ==========================================

while true; do
    clear
    echo "===================================================="
    echo "          BRANE DEPLOYMENT HELPER                   "
    echo "===================================================="
    echo ""
    echo "  Config : ${CONFIG_FILE}"
    echo "  Repo   : ${REPO_ROOT}"
    echo "  Host   : ${HOST_IP}"
    echo ""
    echo "  ── Ansible Deployment ──────────────────────────"
    echo "  Recommended order: prerequisites → branectl →"
    echo "    workers → central → certs → start → smoke"
    echo ""
    echo "   1) Full deployment (all tags)"
    echo "   2) Prerequisites only"
    echo "   3) Install branectl only"
    echo "   4) Configure workers only"
    echo "   5) Configure central only"
    echo "   6) Exchange certificates only"
    echo "   7) Start services only"
    echo "   8) Run smoke test only"
    echo "   9) Custom tags (prompt)"
    echo "  10) Dry run / check mode (prompt for tags)"
    echo "  11) Syntax check"
    echo ""
    echo "  ── Brane CLI ───────────────────────────────────"
    echo "  12) Test connections to remote host (${HOST_IP})"
    echo "  13) List Brane instances"
    echo "  14) List Brane instances (with status)"
    echo "  15) Add & use Brane instance (${INSTANCE_NAME})"
    echo "  16) Build package (${CONTAINER_YML})"
    echo "  17) Load package (${PACKAGE_NAME})"
    echo "  18) List Brane packages"
    echo "  19) Test package locally (${PACKAGE_NAME})"
    echo "  20) Push package to remote registry (${PACKAGE_NAME})"
    echo "  21) Start REPL on remote server"
    echo "  22) Run local workflow test"
    echo "  23) Run remote workflow test"
    echo "  24) List Brane certificates"
    echo "  25) Add Brane certificates (prompt for domain & paths)"
    echo "  26) Build dataset (prompt for data.yml)"
    echo ""
    echo "  ── Docs ────────────────────────────────────────"
    echo "  27) Generate Brane CLI help documentation"
    echo ""
    echo "----------------------------------------------------"
    echo "   q) Exit"
    echo "===================================================="
    read -r -p "Choose an option [1-27 or q]: " choice

    case "${choice}" in

    # ── Ansible ──────────────────────────────────────────

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
        log_info "Exchanging certificates..."
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

    # ── Brane CLI ─────────────────────────────────────────

    12)
        log_info "Testing connections to ${HOST_IP}..."
        run_cmd "nc -vz '${HOST_IP}' '${PORT_REPL}'"
        run_cmd "nc -vz '${HOST_IP}' '${PORT_REGISTRY}'"
        run_cmd "curl -sv --max-time 5 'http://${HOST_IP}:${PORT_REPL}'"
        run_cmd "curl -sv --max-time 5 'http://${HOST_IP}:${PORT_REGISTRY}'"
        press_enter
        ;;
    13)
        run_cmd "brane instance list"
        press_enter
        ;;
    14)
        run_cmd "brane instance list --show-status"
        press_enter
        ;;
    15)
        run_cmd "brane instance add '${INSTANCE_DOMAIN}' --name '${INSTANCE_NAME}' --use"
        press_enter
        ;;
    16)
        if [[ "$(uname)" == "Darwin" ]]; then
            read -r -e -p "Enter path to macOS build script [default: ${SCRIPT_DIR}/package_build_macOS.sh]: " BUILD_SCRIPT
            BUILD_SCRIPT="${BUILD_SCRIPT:-${SCRIPT_DIR}/package_build_macOS.sh}"
            run_cmd "'${BUILD_SCRIPT}' '${PACKAGE_DIR}/${PACKAGE_NAME}/${CONTAINER_YML}'"
        else
            run_cmd "brane package build --arch x86_64 '${PACKAGE_DIR}/${PACKAGE_NAME}/${CONTAINER_YML}'"
	    --arch x86_64
        fi
        press_enter
        ;;
    17)
        run_cmd "brane package load '${PACKAGE_NAME}'"
        press_enter
        ;;
    18)
        run_cmd "brane package list"
        press_enter
        ;;
    19)
        run_cmd "brane package test '${PACKAGE_NAME}'"
        press_enter
        ;;
    20)
        run_cmd "brane package push '${PACKAGE_NAME}:${PACKAGE_VERSION}'"
        press_enter
        ;;
    21)
        run_cmd "brane workflow repl --remote 'http://${HOST_IP}:${PORT_REPL}'"
        press_enter
        ;;
    22)
        run_cmd "brane workflow run test '${WORKFLOW_PATH}'"
        press_enter
        ;;
    23)
        run_cmd "brane workflow run --remote test '${WORKFLOW_PATH}'"
        press_enter
        ;;
    24)
        log_info "Listing Brane certificates..."
        run_cmd "brane certs list"
        press_enter
        ;;
    25)
        echo ""
        log_info "Adding Brane certificates to active instance."
        read -r -p "Enter the domain: " USER_DOMAIN
        read -r -e -p "Enter path to ca.pem: " CA_PATH
        read -r -e -p "Enter path to client-id.pem: " CLIENT_PATH
        if [[ -z "${USER_DOMAIN}" || -z "${CA_PATH}" || -z "${CLIENT_PATH}" ]]; then
            log_error "Domain and both certificate paths are required. Aborting."
        else
            run_cmd "brane certs add --domain '${USER_DOMAIN}' '${CA_PATH}/ca.pem' '${CLIENT_PATH}/client-id.pem'"
        fi
        press_enter
        ;;
    26)
        echo ""
        log_info "Preparing to build a dataset..."
        read -r -e -p "Enter path to data.yml [default: datasets/minmax/data/data.yml]: " DATA_YML_PATH
        DATA_YML_PATH="${DATA_YML_PATH:-datasets/minmax/data/data.yml}"
        if [[ -f "${DATA_YML_PATH}" ]]; then
            log_info "Building dataset: ${DATA_YML_PATH} (Debug Mode)"
            run_cmd "brane data build --debug '${DATA_YML_PATH}'"
        else
            log_error "File '${DATA_YML_PATH}' does not exist. Aborting."
        fi
        press_enter
        ;;

    # ── Docs ──────────────────────────────────────────────

    27)
        log_info "Generating complete Brane CLI help documentation..."
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
        log_success "Markdown manual saved to: brane_all_helps.md"
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

