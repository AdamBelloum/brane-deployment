#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Brane Operations"
echo "  1) Deploy / manage Brane"
echo "  2) Cleanup Brane environment"
echo "  3) Show Brane tools help"
echo "  4) troubleshoot brane deployment"
echo "  5) Exit"
read -rp "Enter choice [1-4]: " choice

case "$choice" in
    1) exec "$SCRIPT_DIR/brane_helper.sh" ;;
    2) exec "$SCRIPT_DIR/brane_cleanup.sh" ;;
    3) exec "$SCRIPT_DIR/show_brane_tools_help.sh" ;;
    4) exec "$SCRIPT_DIR/troubleshoot-brane-deployment.sh" ;;
    5) exit 0 ;;
    *) echo "Invalid choice";;
esac
