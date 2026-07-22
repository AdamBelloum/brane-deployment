#!/usr/bin/env bash
# brane_helper.sh

# ==========================================
# COLORS
# ==========================================
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ==========================================
# CONFIGURATION
# ==========================================

export PATH="$HOME/.local/bin:$PATH"

# ── Ansible role (new) ───────────────────
ANSIBLE_INVENTORY="inventory/hosts.ini"
ANSIBLE_PLAYBOOK="site.yml"
ALL_TAGS="prerequisites,branectl,worker,central,certs,start,smoke"

# ── Brane CLI settings ───────────────────
PACKAGE_DIR="./packages"
PACKAGE_NAME="hello_world"
WORKFLOW_NAME="hello_world.bs"
CONTAINER_YML="container.yml"
PACKAGE_VERSION="1.0.0"
WORKFLOW_PATH="$PACKAGE_DIR/$PACKAGE_NAME/$WORKFLOW_NAME"

# ── Infrastructure ───────────────────────
HOST_IP="145.100.135.209"
PORT_REPL="50053"
PORT_REGISTRY="50051"

INSTANCE_DOMAIN="ab-01.lab.uvalight.net"
INSTANCE_NAME="adamtest"

# ==========================================
# HELPERS
# ==========================================

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

run_cmd() {
    echo -e "${YELLOW}Command:${NC} $1"
    echo "----------------------------------------------------"
    eval "$1"
}

press_enter() {
    echo ""
    read -p "Press [Enter] to return to the menu..."
}

# ==========================================
# MENU LOOP
# ==========================================

while true; do
    clear
    echo "===================================================="
    echo "               BRANE WORKFLOW HELPER                "
    echo "===================================================="
    echo ""
    echo "  ── Ansible Deployment ──────────────────────────"
    echo "  1)  Full deployment (all tags)"
    echo "  2)  Prerequisites only"
    echo "  3)  Install branectl only"
    echo "  4)  Configure workers only"
    echo "  5)  Configure central only"
    echo "  6)  Exchange certificates only"
    echo "  7)  Start services only"
    echo "  8)  Run smoke test only"
    echo "  9)  Custom tags (prompt)"
    echo "  10) Dry run / check mode (prompt for tags)"
    echo "  11) Syntax check"
    echo ""
    echo "  ── Brane CLI ───────────────────────────────────"
    echo "  12) Test connections to remote host ($HOST_IP)"
    echo "  13) List Brane instances"
    echo "  14) List Brane instances (with status)"
    echo "  15) Add & use Brane instance ($INSTANCE_NAME)"
    echo "  16) Build package ($CONTAINER_YML)"
    echo "  17) Load package ($PACKAGE_NAME)"
    echo "  18) List Brane packages"
    echo "  19) Test package locally ($PACKAGE_NAME)"
    echo "  20) Push package to remote registry ($PACKAGE_NAME)"
    echo "  21) Start REPL on remote server"
    echo "  22) Run local workflow test ($WORKFLOW_PATH)"
    echo "  23) Run remote workflow test ($WORKFLOW_PATH)"
    echo "  24) List Brane certificates"
    echo "  25) Add Brane certificates (prompt for domain & paths)"
    echo "  26) Build dataset (prompt for data.yml)"
    echo ""
    echo "  ── Docs ────────────────────────────────────────"
    echo "  27) Generate Brane CLI help documentation"
    echo ""
    echo "----------------------------------------------------"
    echo "  q)  Exit"
    echo "===================================================="
    read -p "Choose an option [1-27 or q]: " choice

    case $choice in

        # ── Ansible ──────────────────────────────────────────

        1)
            log_info "Running full Brane deployment..."
            run_cmd "ansible-playbook -i $ANSIBLE_INVENTORY $ANSIBLE_PLAYBOOK"
            press_enter
            ;;
        2)
            log_info "Running prerequisites..."
            run_cmd "ansible-playbook -i $ANSIBLE_INVENTORY $ANSIBLE_PLAYBOOK --tags prerequisites"
            press_enter
            ;;
        3)
            log_info "Installing branectl..."
            run_cmd "ansible-playbook -i $ANSIBLE_INVENTORY $ANSIBLE_PLAYBOOK --tags branectl"
            press_enter
            ;;
        4)
            log_info "Configuring worker nodes..."
            run_cmd "ansible-playbook -i $ANSIBLE_INVENTORY $ANSIBLE_PLAYBOOK --tags worker"
            press_enter
            ;;
        5)
            log_info "Configuring central node..."
            run_cmd "ansible-playbook -i $ANSIBLE_INVENTORY $ANSIBLE_PLAYBOOK --tags central"
            press_enter
            ;;
        6)
            log_info "Exchanging certificates..."
            run_cmd "ansible-playbook -i $ANSIBLE_INVENTORY $ANSIBLE_PLAYBOOK --tags certs"
            press_enter
            ;;
        7)
            log_info "Starting Brane services..."
            run_cmd "ansible-playbook -i $ANSIBLE_INVENTORY $ANSIBLE_PLAYBOOK --tags start"
            press_enter
            ;;
        8)
            log_info "Running smoke test..."
            run_cmd "ansible-playbook -i $ANSIBLE_INVENTORY $ANSIBLE_PLAYBOOK --tags smoke"
            press_enter
            ;;
        9)
            echo ""
            log_info "Available tags: $ALL_TAGS"
            read -p "Enter tags (comma-separated) [default: $ALL_TAGS]: " USER_TAGS
            if [ -z "$USER_TAGS" ]; then
                USER_TAGS="$ALL_TAGS"
            fi
            run_cmd "ansible-playbook -i $ANSIBLE_INVENTORY $ANSIBLE_PLAYBOOK --tags '$USER_TAGS'"
            press_enter
            ;;
        10)
            echo ""
            log_info "Available tags: $ALL_TAGS"
            read -p "Enter tags for dry run [default: all]: " USER_TAGS
            if [ -z "$USER_TAGS" ]; then
                run_cmd "ansible-playbook -i $ANSIBLE_INVENTORY $ANSIBLE_PLAYBOOK --check --diff"
            else
                run_cmd "ansible-playbook -i $ANSIBLE_INVENTORY $ANSIBLE_PLAYBOOK --check --diff --tags '$USER_TAGS'"
            fi
            press_enter
            ;;
        11)
            log_info "Running syntax check..."
            run_cmd "ansible-playbook -i $ANSIBLE_INVENTORY $ANSIBLE_PLAYBOOK --syntax-check"
            press_enter
            ;;

        # ── Brane CLI ─────────────────────────────────────────

        12)
            log_info "Testing connections to $HOST_IP..."
            run_cmd "nc -vz $HOST_IP $PORT_REPL"
            run_cmd "nc -vz $HOST_IP $PORT_REGISTRY"
            run_cmd "curl -v http://$HOST_IP:$PORT_REPL"
            run_cmd "curl -v http://$HOST_IP:$PORT_REGISTRY"
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
            run_cmd "brane instance add $INSTANCE_DOMAIN --name $INSTANCE_NAME --use"
            press_enter
            ;;
        16)
            if [[ "$(uname)" == "Darwin" ]]; then
                read -e -p "Enter path to macOS build script [default: scripts/package_build_macOS.sh]: " BUILD_SCRIPT
                if [ -z "$BUILD_SCRIPT" ]; then
                    BUILD_SCRIPT="scripts/package_build_macOS.sh"
                fi
                run_cmd "$BUILD_SCRIPT $PACKAGE_DIR/$PACKAGE_NAME/$CONTAINER_YML"
            else
                run_cmd "brane package build $PACKAGE_DIR/$PACKAGE_NAME/$CONTAINER_YML"
            fi
            press_enter
            ;;
        17)
            run_cmd "brane package load $PACKAGE_NAME"
            press_enter
            ;;
        18)
            run_cmd "brane package list"
            press_enter
            ;;
        19)
            run_cmd "brane package test $PACKAGE_NAME"
            press_enter
            ;;
        20)
            run_cmd "brane package push $PACKAGE_NAME:$PACKAGE_VERSION"
            press_enter
            ;;
        21)
            run_cmd "brane workflow repl --remote http://$HOST_IP:$PORT_REPL"
            press_enter
            ;;
        22)
            run_cmd "brane workflow run test $WORKFLOW_PATH"
            press_enter
            ;;
        23)
            run_cmd "brane workflow run --remote test $WORKFLOW_PATH"
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
            read -p "Enter the domain: " USER_DOMAIN
            read -e -p "Enter path to ca.pem: " CA_PATH
            read -e -p "Enter path to client-id.pem: " CLIENT_PATH
            if [ -z "$USER_DOMAIN" ] || [ -z "$CA_PATH" ] || [ -z "$CLIENT_PATH" ]; then
                log_error "Domain and both certificate paths are required. Aborting."
            else
                run_cmd "brane certs add --domain $USER_DOMAIN $CA_PATH/ca.pem $CLIENT_PATH/client-id.pem"
            fi
            press_enter
            ;;
        26)
            echo ""
            log_info "Preparing to build a dataset..."
            read -e -p "Enter path to data.yml [default: datasets/minmax/data/data.yml]: " DATA_YML_PATH
            if [ -z "$DATA_YML_PATH" ]; then
                DATA_YML_PATH="datasets/minmax/data/data.yml"
            fi
            if [ -f "$DATA_YML_PATH" ]; then
                log_info "Building dataset: $DATA_YML_PATH (Debug Mode)"
                run_cmd "brane data build --debug $DATA_YML_PATH"
            else
                log_error "File '$DATA_YML_PATH' does not exist. Aborting."
            fi
            press_enter
            ;;

        # ── Docs ──────────────────────────────────────────────

        27)
            log_info "Generating complete Brane CLI help documentation..."
            {
                echo "# Brane CLI Help Documentation"
                echo -e "\n## Top-Level Help\n"
                echo '```text'
                brane --help
                echo '```'
                for cmd in certs instance package workflow data; do
                    echo -e "\n## brane $cmd\n"
                    echo '```text'
                    brane "$cmd" --help
                    echo '```'
                done
            } > brane_all_helps.md
            log_success "Markdown manual saved to: brane_all_helps.md"
            press_enter
            ;;

        q|Q)
            log_success "Exiting. Goodbye!"
            exit 0
            ;;
        *)
            log_error "Invalid option. Please try again."
            sleep 1
            ;;
    esac
done

