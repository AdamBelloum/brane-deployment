#!/usr/bin/env bash

# ==============================================================================
# Script Name: troubleshoot_brane_deployment.sh
# Description: Interactive troubleshooting assistant separated into User Machine 
#              tests and Remote Node (SSH) tests.
# Usage:       ./troubleshoot_brane_deployment.sh
# ==============================================================================

set -euo pipefail

log_info() {
    echo -e "\033[34m[INFO]\033[0m $1"
}

log_success() {
    echo -e "\033[32m[SUCCESS]\033[0m $1"
}

log_error() {
    echo -e "\033[31m[ERROR]\033[0m $1" >&2
}

print_header() {
    echo "======================================================"
    echo "      Brane Deployment Troubleshooting Assistant        "
    echo "======================================================"
}

# ------------------------------------------------------------------------------
# CATEGORY 1: User Machine Tests (Host Machine / External perspective)
# ------------------------------------------------------------------------------
run_user_machine_tests() {
    log_info "Running tests from the user/host machine..."
    
    read -rp "Enter target node IP or hostname [default: 145.100.135.209]: " target_ip
    target_ip="${target_ip:-145.100.135.209}"

    echo "--- 1. Testing connection to port 50053 on remote node ---"
    nc -vz "$target_ip" 50053 || true

    echo -e "\n--- 2. Testing connection to port 50051 on remote node ---"
    nc -vz "$target_ip" 50051 || true
}

# ------------------------------------------------------------------------------
# CATEGORY 2: Remote Node Tests (Requires SSH to Central/Worker nodes)
# ------------------------------------------------------------------------------
run_remote_node_tests() {
    log_info "Running tests that require executing commands on the target node..."
    
    echo "Do you want to run these commands locally (if you are already logged into the node) or via SSH?"
    echo "  1) Run locally (You are currently logged into the node)"
    echo "  2) Run remotely via SSH"
    read -rp "Select execution mode [1 or 2]: " exec_mode

    local prefix=""
    if [[ "$exec_mode" == "2" ]]; then
        read -rp "Enter SSH connection string (e.g., adam@ab-01 or user@node-ip): " ssh_target
        prefix="ssh $ssh_target"
    fi

    echo -e "\n--- 1. Testing port 50051 on the control node ---"
    if [[ -n "$prefix" ]]; then
        $prefix "nc -vz localhost 50051" || true
    else
        nc -vz localhost 50051 || true
    fi

    echo -e "\n--- 2. Checking listening sockets using ss ---"
    if [[ -n "$prefix" ]]; then
        $prefix "sudo ss -tulpn | grep 5005" || echo "No matching sockets found via ss."
    else
        sudo ss -tulpn | grep 5005 || echo "No matching sockets found via ss."
    fi

    echo -e "\n--- 3. Checking listening sockets using netstat ---"
    if [[ -n "$prefix" ]]; then
        $prefix "sudo netstat -tulpn | grep 5005" || echo "No matching sockets found via netstat."
    else
        sudo netstat -tulpn | grep 5005 || echo "No matching sockets found via netstat."
    fi

    echo -e "\n--- 4. Testing HTTP endpoint via curl ---"
    if [[ -n "$prefix" ]]; then
        $prefix "curl -v http://localhost:50051" || true
    else
        curl -v http://localhost:50051 || true
    fi

    echo -e "\n--- 5. Checking Brane Docker containers on the central node ---"
    if [[ -n "$prefix" ]]; then
        $prefix "docker images | grep -i brane" || echo "No Brane images found."
        echo ""
        $prefix "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
    else
        docker images | grep -i brane || echo "No Brane images found."
        echo ""
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    fi
}

# ------------------------------------------------------------------------------
# CATEGORY 3: clean the brane enviroment 
# ------------------------------------------------------------------------------

run_clean_brane_environment() {
    log_info "Cleaning Brane environment on the target node (containers, volumes, networks, local config)..."
    echo ""
    echo "WARNING: This will DELETE Brane containers, volumes, networks and some local config."
    echo "Only run this on the Brane central node when you want a clean slate for re-deployment."
    echo ""

    echo "Do you want to run these commands locally (if you are already logged into the node) or via SSH?"
    echo "  1) Run locally (You are currently logged into the Brane central node)"
    echo "  2) Run remotely via SSH"
    read -rp "Select execution mode [1 or 2]: " exec_mode

    local prefix=""
    if [[ "$exec_mode" == "2" ]]; then
        read -rp "Enter SSH connection string (e.g., adam@ab-01 or user@node-ip): " ssh_target
        prefix="ssh $ssh_target"
    fi

    echo "=== Stopping and removing Brane containers ==="
    if [[ -n "$prefix" ]]; then
        $prefix 'BRANE_CONTAINERS=$(docker ps -a --filter "name=brane" -q);
                 if [ -n "$BRANE_CONTAINERS" ]; then
                     docker rm -f $BRANE_CONTAINERS;
                 else
                     echo "No Brane containers found.";
                 fi'
    else
        BRANE_CONTAINERS=$(docker ps -a --filter "name=brane" -q)
        if [ -n "$BRANE_CONTAINERS" ]; then
            docker rm -f $BRANE_CONTAINERS
        else
            echo "No Brane containers found."
        fi
    fi

    echo "=== Removing Brane volumes ==="
    if [[ -n "$prefix" ]]; then
        $prefix 'BRANE_VOLUMES=$(docker volume ls --filter "name=brane" -q);
                 if [ -n "$BRANE_VOLUMES" ]; then
                     docker volume rm $BRANE_VOLUMES;
                 else
                     echo "No Brane volumes found.";
                 fi'
    else
        BRANE_VOLUMES=$(docker volume ls --filter "name=brane" -q)
        if [ -n "$BRANE_VOLUMES" ]; then
            docker volume rm $BRANE_VOLUMES
        else
            echo "No Brane volumes found."
        fi
    fi

    echo "=== Removing Brane networks ==="
    if [[ -n "$prefix" ]]; then
        $prefix 'BRANE_NETWORKS=$(docker network ls --filter "name=brane" -q);
                 if [ -n "$BRANE_NETWORKS" ]; then
                     docker network rm $BRANE_NETWORKS;
                 else
                     echo "No Brane networks found.";
                 fi'
    else
        BRANE_NETWORKS=$(docker network ls --filter "name=brane" -q)
        if [ -n "$BRANE_NETWORKS" ]; then
            docker network rm $BRANE_NETWORKS
        else
            echo "No Brane networks found."
        fi
    fi

    echo "=== System pruning Docker cache ==="
    if [[ -n "$prefix" ]]; then
        $prefix "docker system prune -f"
    else
        docker system prune -f
    fi

    echo "=== Cleaning local directory targets (brane-central config) ==="
    if [[ -n "$prefix" ]]; then
        $prefix "rm -rf ~/brane-central/config/infra.yml ~/brane-central/config/proxy.yml"
    else
        rm -rf ~/brane-central/config/infra.yml ~/brane-central/config/proxy.yml
    fi

    echo "Done! The VM environment is clean and ready for Ansible."
}

# ------------------------------------------------------------------------------
# CATEGORY 4: Ansible Deployment Checks (run from operator/control machine)
# ------------------------------------------------------------------------------
run_ansible_checks() {
    log_info "Running Ansible deployment checks from the control machine..."

    # Guard: ensure we are in the Ansible project root
    if [[ ! -f "site.yml" || ! -d "inventories" || ! -d "roles" ]]; then
        log_error "This option must be run from the Ansible project root."
        log_error "Expected to find: site.yml, inventories/, roles/ in the current directory."
        log_error "Current directory: $(pwd)"
        log_error "Please cd into the Ansible project root and re-run this script."
        return
    fi    

    echo ""
    echo "Select Ansible check to run:"
    echo "  1) Syntax check (no SSH needed)"
    echo "  2) Dry run (connects to hosts, no changes made)"
    echo "  3) Full deployment"
    echo "  4) Rerun a single stage (by tag)"
    echo "  5) Verbose output"
    echo "  6) Recommended first-run sequence"
    echo "  7) Back to main menu"
    echo ""
    read -rp "Enter your choice [1-7]: " ansible_choice

    case "$ansible_choice" in
        1)
            log_info "Running syntax check..."
            ansible-playbook -i inventories/production/hosts.ini site.yml --syntax-check
            ;;
        2)
            log_info "Running dry run..."
            ansible-playbook -i inventories/production/hosts.ini site.yml --check --diff
            ;;
        3)
            log_info "Running full deployment..."
            ansible-playbook -i inventories/production/hosts.ini site.yml
            ;;
        4)
            echo ""
            echo "Available tags:"
            echo "  prerequisites, branectl, worker, central, certs, start, smoke"
            echo ""
            read -rp "Enter tag to run: " tag
            log_info "Running playbook with tag: $tag"
            ansible-playbook -i inventories/production/hosts.ini site.yml --tags "$tag"
            ;;
        5)
            echo ""
            echo "Select verbosity level:"
            echo "  1) -v    (task-level output)"
            echo "  2) -vv   (includes variable values)"
            echo "  3) -vvv  (includes SSH debug)"
            echo ""
            read -rp "Enter verbosity [1-3]: " verbosity
            case "$verbosity" in
                1) ansible-playbook -i inventories/production/hosts.ini site.yml -v ;;
                2) ansible-playbook -i inventories/production/hosts.ini site.yml -vv ;;
                3) ansible-playbook -i inventories/production/hosts.ini site.yml -vvv ;;
                *) log_error "Invalid verbosity level." ;;
            esac
            ;;
        6)
            log_info "Step 1 — Syntax check (catch YAML/template errors locally)..."
            ansible-playbook -i inventories/production/hosts.ini site.yml --syntax-check

            log_info "Step 2 — Verify connectivity and variable resolution..."
            ansible -i inventories/production/hosts.ini all -m ping

            log_info "Step 3 — Full deployment..."
            ansible-playbook -i inventories/production/hosts.ini site.yml
            ;;
        7)
            return
            ;;
        *)
            log_error "Invalid selection."
            ;;
    esac
}


# ------------------------------------------------------------------------------
# Main Menu
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        clear
        print_header
        echo "Select diagnostic category:"
        echo "  1) User Machine Tests        (Test external connectivity to remote nodes)"
        echo "  2) Remote Node Tests         (Port bindings, netstat/ss, Brane Docker containers)"
        echo "  3) Clean Brane environment   (Purge containers, volumes, networks on target VM)"
        echo "  4) Ansible Deployment Checks (Syntax check, dry run, tags, verbose)"
        echo "  5) Exit"
        echo ""

        read -rp "Enter your choice [1-5]: " choice

        case "$choice" in
            1) 
                echo "" 
                run_user_machine_tests 
                read -rp "Press Enter to return to the menu..." 
                ;;
            2) echo "" 
                run_remote_node_tests 
                read -rp "Press Enter to return to the menu..." 
                ;;
            3) echo "" 
                run_clean_brane_environment 
                read -rp "Press Enter to return to the menu..." 
                ;; 
            4) echo "" 
                run_ansible_checks 
                read -rp "Press Enter to return to the menu..." 
                ;;
            5) echo "Exiting troubleshooting assistant. Goodbye!" 
                exit 0 
                ;;
            *) log_error "Invalid selection. Please choose between 1 and 5." 
                sleep 2 
                ;;
         esac;
      done
  }

main_menu
