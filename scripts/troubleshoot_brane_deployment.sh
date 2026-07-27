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
# Main Menu
# ------------------------------------------------------------------------------
main_menu() {
    while true; do
        clear
        print_header
        echo "Select diagnostic category:"
        echo "  1) User Machine Tests (Test external connectivity to remote nodes)"
        echo "  2) Remote Node Tests (Port bindings, netstat/ss, and Brane Docker containers via SSH)"
        echo "  3) Exit"
        echo ""
        read -rp "Enter your choice [1-3]: " choice

        case "$choice" in
            1)
                echo ""
                run_user_machine_tests
                read -rp "Press Enter to return to the menu..."
                ;;
            2)
                echo ""
                run_remote_node_tests
                read -rp "Press Enter to return to the menu..."
                ;;
            3)
                echo "Exiting troubleshooting assistant. Goodbye!"
                exit 0
                ;;
            *)
                log_error "Invalid selection. Please choose between 1 and 3."
                sleep 2
                ;;
        esac
    done
}

main_menu
