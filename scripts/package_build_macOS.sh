#!/usr/bin/env bash

# ==============================================================================
# Script Name: package_build_macos.sh
# Description: Production-ready wrapper script for building Brane packages on 
#              macOS (Docker Desktop) and Linux. It automatically provisions 
#              and targets an isolated BuildKit container builder to bypass 
#              native macOS buildx tar export restrictions.
# ==============================================================================

# Exit immediately if any command exits with a non-zero status, 
# if any unset variable is used, or if a failure occurs in a pipeline.
set -euo pipefail

# Define a unique builder name for this software ecosystem
readonly BUILDER_NAME="brane_project_builder"

# ANSI color codes for clean, professional terminal output
readonly COLOR_INFO="\033[34m[INFO]\033[0m"
readonly COLOR_SUCCESS="\033[32m[SUCCESS]\033[0m"
readonly COLOR_ERROR="\033[31m[ERROR]\033[0m"
readonly COLOR_RESET="\033[0m"

# ------------------------------------------------------------------------------
# Function: log_info
# Purpose: Prints formatted informational messages to standard output.
# ------------------------------------------------------------------------------
log_info() {
    echo -e "${COLOR_INFO} $1"
}

# ------------------------------------------------------------------------------
# Function: log_success
# Purpose: Prints formatted success messages to standard output.
# ------------------------------------------------------------------------------
log_success() {
    echo -e "${COLOR_SUCCESS} $1"
}

# ------------------------------------------------------------------------------
# Function: log_error
# Purpose: Prints formatted error messages to standard error.
# ------------------------------------------------------------------------------
log_error() {
    echo -e "${COLOR_ERROR} $1" >&2
}

# ------------------------------------------------------------------------------
# Function: check_dependencies
# Purpose: Ensures required binaries (docker and brane) are installed and 
#          available in the user's executable path.
# ------------------------------------------------------------------------------
check_dependencies() {
    log_info "Verifying system dependencies..."

    for cmd in docker brane; do
        if ! command -v "$cmd" &>/dev/null; then
            log_error "Required dependency '$cmd' is not installed or not in PATH."
            exit 1
        fi
    done

    log_success "All system dependencies are present."
}

# ------------------------------------------------------------------------------
# Function: setup_docker_buildx
# Purpose: Inspects the local Docker buildx environment. If our dedicated 
#          containerized builder does not exist, it provisions, boots, and 
#          bootstraps it automatically.
# ------------------------------------------------------------------------------
setup_docker_buildx() {
    log_info "Checking Docker buildx configuration..."

    # Check if the builder instance already exists in Docker config
    if ! docker buildx inspect "$BUILDER_NAME" &>/dev/null; then
        log_info "Builder '$BUILDER_NAME' not found. Creating a containerized builder..."

        # Create a new buildx instance using the docker-container driver 
        # which supports advanced multi-platform and tarball exports on macOS.
        if ! docker buildx create --name "$BUILDER_NAME" --driver docker-container --use >/dev/null 2>&1; then
            log_error "Failed to create buildx builder instance."
            exit 1
        fi

        log_info "Bootstrapping BuildKit daemon for '$BUILDER_NAME'..."
        docker buildx inspect --bootstrap >/dev/null 2>&1
        log_success "Successfully created and initialized '$BUILDER_NAME'."
    else
        log_info "Builder '$BUILDER_NAME' exists. Setting it as active..."
        docker buildx use "$BUILDER_NAME" >/dev/null 2>&1
        log_success "Active buildx builder set to '$BUILDER_NAME'."
    fi
}

# ------------------------------------------------------------------------------
# Function: execute_brane_build
# Purpose: Safely intercepts the raw Docker buildx calls executed internally 
#          by the Brane CLI subprocess by injecting the correct builder target 
#          via a transient shell environment override.
# ------------------------------------------------------------------------------
execute_brane_build() {
    local target_yml="${1:-./packages/hello_world/container.yml}"

    if [[ ! -f "$target_yml" ]]; then
        log_error "Specified container configuration file not found: '$target_yml'"
        exit 1
    fi

    log_info "Building Brane package using config: '$target_yml'"

    # Running the native Brane build command directly now that the correct
    # buildx builder is set as the active default context.
    if brane package build "$target_yml"; then
        log_success "Brane package built successfully!"
    else
        log_error "Package build failed. Review the output logs above."
        exit 1
    fi
}

# ------------------------------------------------------------------------------
# Main Execution Flow
# ------------------------------------------------------------------------------
main() {
    log_info "Initializing Brane build wrapper script..."

    # Step 1: Validate toolchain availability
    check_dependencies

    # Step 2: Provision or switch to the correct multi-platform builder
    setup_docker_buildx

    # Step 3: Trigger the actual build process with the user-provided or default path
    execute_brane_build "$1"
}

# Invoke the main entry point with all passed command-line arguments
main "$@"
