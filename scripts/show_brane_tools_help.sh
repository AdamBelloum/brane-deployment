#!/usr/bin/env bash

# ==============================================================================
# Script Name: generate_cli_docs.sh
# Description: Recursively explores a specified CLI tool ('brane' or 'branectl'),
#              captures its help text across all subcommands, and saves 
#              the complete reference manual into a Markdown file.
# Usage:       ./generate_cli_docs.sh [brane|branectl]
# Requirements: The target CLI must be installed and available in your $PATH.
# ==============================================================================

set -euo pipefail

# Simple logging helpers
log_success() {
    echo -e "\033[32m[SUCCESS]\033[0m $1"
}

log_error() {
    echo -e "\033[31m[ERROR]\033[0m $1" >&2
}

# Check if an argument was provided; if not, guide the user interactively
if [[ $# -eq 0 ]]; then
    echo "Welcome! This script generates comprehensive Markdown documentation for Brane CLI tools."
    echo ""
    echo "Please select which tool you would like to document:"
    echo "  1) brane"
    echo "  2) branectl"
    echo ""
    read -rp "Enter your choice [1 or 2]: " choice

    case "$choice" in
        1|brane)
            CLI_TOOL="brane"
            ;;
        2|branectl)
            CLI_TOOL="branectl"
            ;;
        *)
            log_error "Invalid selection."
            print_usage
            exit 1
            ;;
    esac
else
    CLI_TOOL="$1"
fi

# Determine which tool to document (default to 'brane' if not specified)
CLI_TOOL="${1:-brane}"

# Validate the tool choice
if [[ "$CLI_TOOL" != "brane" && "$CLI_TOOL" != "branectl" ]]; then
    log_error "Invalid tool specified: '$CLI_TOOL'."
    echo "Usage: $0 [brane|branectl]"
    exit 1
fi

# Ensure the selected CLI exists and is available in the system PATH before proceeding
if ! command -v "$CLI_TOOL" &> /dev/null; then
    log_error "'$CLI_TOOL' command does not exist or is not installed in your PATH."
    echo "Please install '$CLI_TOOL' or ensure your environment/virtual environment is activated." >&2
    exit 1
fi

OUTPUT_FILE="${CLI_TOOL}_all_helps.md"

# Recursive function to fetch help and discover subcommands
get_help_recursive() {
    local cmd_path=("$@")
    
    # Format the header name for Markdown (e.g., "brane package create")
    echo -e "\n## ${cmd_path[*]}\n"
    echo '```text'
    
    # Run the help command and capture the output safely
    local help_output
    help_output=$("${cmd_path[@]}" --help 2>&1)
    echo "$help_output"
    echo '```'
    
    # Parse the help output to find subcommands.
    # It looks for lines after 'Commands:' or 'Available Commands:' and extracts the first word.
    local subcommands
    subcommands=$(echo "$help_output" | awk '
        /Commands:/ || /Available Commands:/ { flag=1; next }
        /^[A-Z]/ || /^$/ { flag=0 }
        flag { 
            # Clean up leading spaces/tabs and grab the command name
            gsub(/^[ \t]+/, ""); 
            if ($1 != "" && $1 !~ /^\[/ && $1 !~ /^-/) print $1 
        }
    ')
    
    # If subcommands were found, loop through them recursively
    if [[ -n "$subcommands" ]]; then
        while read -r sub; do
            [[ -z "$sub" ]] && continue
            # Recursive call adding the new subcommand to the path
            get_help_recursive "${cmd_path[@]}" "$sub"
        done <<< "$subcommands"
    fi  
}

echo "Generating complete $CLI_TOOL CLI help documentation recursively..."

{
    # Capitalize the tool name for the document title
    TITLE_NAME=$(echo "$CLI_TOOL" | awk '{print toupper(substr($0,1,1)) substr($0,2)}')
    echo "# $TITLE_NAME Complete Recursive Help Documentation"
    echo "Generated on: $(date)"
    
    # Kick off the recursion with the chosen base command
    get_help_recursive "$CLI_TOOL"
    
} > "$OUTPUT_FILE"

log_success "Markdown manual generated successfully! Saved to: $OUTPUT_FILE"
