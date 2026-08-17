#!/usr/bin/env bash
# =============================================================
# brane_main.sh
# Version : 2.0.0
# Date    : 2026-08-17
# Desc    : Entry point for the Brane helper suite.
#           Shows a welcome screen with an infrastructure
#           snapshot, then routes to the role-specific helper.
# Usage   : bash scripts/brane_main.sh
# =============================================================

set -o nounset
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${SCRIPT_DIR}/brane_lib.sh"
load_config_soft "${SCRIPT_DIR}"

# Directories to inspect
PACKAGES_DIR="${REPO_ROOT}/packages"
CERTS_DIR="${REPO_ROOT}/certs"
DATASETS_DIR="${REPO_ROOT}/datasets"
TOKEN_DIR="${REPO_ROOT}/policy_token"

# ==========================================
# INVENTORY PARSER (same logic as policy helper)
# ==========================================

_parse_inventory() {
    INV_WORKER_HOSTS=()
    INV_CENTRAL_HOST=""
    INV_SSH_USER="${WORKER_SSH_USER:-${USER}}"

    [[ ! -f "${ANSIBLE_INVENTORY}" ]] && return 1

    local in_workers=0 in_central=0
    while IFS= read -r line; do
        [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
        if [[ "${line}" =~ ^\[workers\] ]];  then in_workers=1; in_central=0; continue
        elif [[ "${line}" =~ ^\[central\] ]]; then in_central=1; in_workers=0; continue
        elif [[ "${line}" =~ ^\[ ]];          then in_workers=0; in_central=0; continue
        fi
        local host=""
        [[ "${line}" =~ ansible_host=([^[:space:]]+) ]] && host="${BASH_REMATCH[1]}" \
            || host=$(printf '%s' "${line}" | awk '{print $1}')
        [[ "${line}" =~ ansible_user=([^[:space:]]+) ]] && INV_SSH_USER="${BASH_REMATCH[1]}"
        [[ -z "${host}" ]] && continue
        [[ "${in_workers}" -eq 1 ]] && INV_WORKER_HOSTS+=("${host}")
        [[ "${in_central}" -eq 1 && -z "${INV_CENTRAL_HOST}" ]] && INV_CENTRAL_HOST="${host}"
    done < "${ANSIBLE_INVENTORY}"
    return 0
}

# ==========================================
# SNAPSHOT — collect state once per launch
# ==========================================

_build_snapshot() {
    # Inventory
    SNAP_INV_OK=false
    SNAP_CENTRAL=""
    SNAP_WORKERS=()
    INV_WORKER_HOSTS=()
    INV_CENTRAL_HOST=""
    INV_SSH_USER="${USER}"
    if _parse_inventory 2>/dev/null; then
        SNAP_INV_OK=true
        SNAP_CENTRAL="${INV_CENTRAL_HOST}"
        SNAP_WORKERS=("${INV_WORKER_HOSTS[@]+"${INV_WORKER_HOSTS[@]}"}")
    fi

    # Directories
    SNAP_PACKAGES=false;  SNAP_PKG_COUNT=0
    SNAP_CERTS=false;     SNAP_CERT_COUNT=0
    SNAP_DATASETS=false;  SNAP_DS_COUNT=0
    SNAP_TOKENS=false;    SNAP_TOK_COUNT=0

    if [[ -d "${PACKAGES_DIR}" ]]; then
        SNAP_PACKAGES=true
        SNAP_PKG_COUNT=$(find "${PACKAGES_DIR}" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
    fi
    if [[ -d "${CERTS_DIR}" ]]; then
        SNAP_CERTS=true
        SNAP_CERT_COUNT=$(find "${CERTS_DIR}" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
    fi
    if [[ -d "${DATASETS_DIR}" ]]; then
        SNAP_DATASETS=true
        SNAP_DS_COUNT=$(find "${DATASETS_DIR}" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
    fi
    if [[ -d "${TOKEN_DIR}" ]]; then
        SNAP_TOKENS=true
        SNAP_TOK_COUNT=$(find "${TOKEN_DIR}" -maxdepth 1 -name "*.json" -type f 2>/dev/null | wc -l | tr -d ' ')
    fi

    # Brane instance
    SNAP_INSTANCE=""
    if command -v brane &>/dev/null; then
        SNAP_INSTANCE=$(brane instance list 2>/dev/null \
            | awk 'NR>1 && /\*/ {print $1; exit} NR>1 {last=$1} END {print last}' \
            | grep -v '^$' || true)
    fi

    # Determine user type
    # "new"      — no dirs, no inventory
    # "partial"  — some dirs present
    # "ready"    — inventory + packages + certs
    SNAP_USER_TYPE="new"
    if ${SNAP_INV_OK} && ${SNAP_PACKAGES} && ${SNAP_CERTS}; then
        SNAP_USER_TYPE="ready"
    elif ${SNAP_INV_OK} || ${SNAP_PACKAGES} || ${SNAP_CERTS} || ${SNAP_DATASETS}; then
        SNAP_USER_TYPE="partial"
    fi
}

# ==========================================
# WELCOME SCREEN
# ==========================================

_show_welcome() {
    clear
    # ── Banner ────────────────────────────────────────────
    printf '\n'
    printf '%s' "${CYAN}"
    printf '  ╔══════════════════════════════════════════════════════╗\n'
    printf '  ║                                                      ║\n'
    printf '  ║   %s██████╗ ██████╗  █████╗ ███╗   ██╗███████╗%s        ║\n' "${BOLD}" "${CYAN}"
    printf '  ║   %s██╔══██╗██╔══██╗██╔══██╗████╗  ██║██╔════╝%s        ║\n' "${BOLD}" "${CYAN}"
    printf '  ║   %s██████╔╝██████╔╝███████║██╔██╗ ██║█████╗  %s        ║\n' "${BOLD}" "${CYAN}"
    printf '  ║   %s██╔══██╗██╔══██╗██╔══██║██║╚██╗██║██╔══╝  %s        ║\n' "${BOLD}" "${CYAN}"
    printf '  ║   %s██████╔╝██║  ██║██║  ██║██║ ╚████║███████╗%s        ║\n' "${BOLD}" "${CYAN}"
    printf '  ║   %s╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝%s        ║\n' "${BOLD}" "${CYAN}"
    printf '  ║                                                      ║\n'
    printf '  ║   %sResearch Infrastructure Helper  v2.0.0%s             ║\n' "${BOLD}" "${CYAN}"
    printf '  ║   %sUniversity of Amsterdam%s                            ║\n' "${YELLOW}" "${CYAN}"
    printf '  ╚══════════════════════════════════════════════════════╝\n'
    printf '%s\n' "${NC}"

    # ── State-dependent welcome message ───────────────────
    case "${SNAP_USER_TYPE}" in
        new)
            printf '  %sWelcome!%s It looks like this is a fresh environment.\n' "${BOLD}" "${NC}"
            printf '  No packages, certificates or inventory were found.\n'
            printf '\n'
            printf '  %sGetting started:%s\n' "${YELLOW}" "${NC}"
            printf '    1. Select %sUser%s below and run option 1 (environment check)\n' "${BOLD}" "${NC}"
            printf '       to install required tools and create the directory structure.\n'
            printf '    2. Use option 2 to add your Brane instance.\n'
            printf '    3. Use option 3 to add your domain certificate.\n'
            printf '\n'
            ;;
        partial)
            printf '  %sWelcome back!%s Your environment is partially configured.\n' "${BOLD}" "${NC}"
            printf '  See the snapshot below — some items still need attention.\n'
            printf '\n'
            ;;
        ready)
            printf '  %sWelcome back!%s Your environment looks ready.\n' "${BOLD}" "${NC}"
            printf '  Infrastructure and local resources are configured.\n'
            printf '\n'
            ;;
    esac

    # ── Infrastructure snapshot ───────────────────────────
    printf '  %s%s%s\n' "${CYAN}" "$(printf '─%.0s' $(seq 1 56))" "${NC}"
    printf '  %sInfrastructure snapshot%s\n' "${BOLD}" "${NC}"
    printf '  %s%s%s\n\n' "${CYAN}" "$(printf '─%.0s' $(seq 1 56))" "${NC}"

    # Inventory
    if ${SNAP_INV_OK}; then
        printf '  %s✓%s Inventory     : found (%s)\n' "${GREEN}" "${NC}" \
            "$(basename "$(dirname "${ANSIBLE_INVENTORY}")")/$(basename "${ANSIBLE_INVENTORY}")"
        if [[ -n "${SNAP_CENTRAL}" ]]; then
            printf '      Central     : %s\n' "${SNAP_CENTRAL}"
        fi
        if [[ "${#SNAP_WORKERS[@]}" -gt 0 ]]; then
            printf '      Workers     :'
            for w in "${SNAP_WORKERS[@]}"; do printf ' %s' "${w}"; done
            printf '\n'
        fi
    else
        printf '  %s✗%s Inventory     : not found  (%s)\n' "${RED}" "${NC}" "${ANSIBLE_INVENTORY}"
    fi

    # Brane instance
    if [[ -n "${SNAP_INSTANCE}" ]]; then
        printf '  %s✓%s Instance      : %s\n' "${GREEN}" "${NC}" "${SNAP_INSTANCE}"
    else
        printf '  %s✗%s Instance      : none configured\n' "${RED}" "${NC}"
    fi

    printf '\n'

    # Local resources
    if ${SNAP_PACKAGES}; then
        printf '  %s✓%s packages/     : %d package(s)\n' "${GREEN}" "${NC}" "${SNAP_PKG_COUNT}"
        find "${PACKAGES_DIR}" -maxdepth 1 -mindepth 1 -type d 2>/dev/null \
            | sort | while IFS= read -r d; do printf '      • %s\n' "$(basename "${d}")"; done
    else
        printf '  %s✗%s packages/     : not found\n' "${RED}" "${NC}"
    fi

    if ${SNAP_CERTS}; then
        printf '  %s✓%s certs/        : %d domain(s)\n' "${GREEN}" "${NC}" "${SNAP_CERT_COUNT}"
        find "${CERTS_DIR}" -maxdepth 1 -mindepth 1 -type d 2>/dev/null \
            | sort | while IFS= read -r d; do printf '      • %s\n' "$(basename "${d}")"; done
    else
        printf '  %s✗%s certs/        : not found\n' "${RED}" "${NC}"
    fi

    if ${SNAP_DATASETS}; then
        printf '  %s✓%s datasets/     : %d dataset(s)\n' "${GREEN}" "${NC}" "${SNAP_DS_COUNT}"
        find "${DATASETS_DIR}" -maxdepth 1 -mindepth 1 -type d 2>/dev/null \
            | sort | while IFS= read -r d; do printf '      • %s\n' "$(basename "${d}")"; done
    else
        printf '  %s✗%s datasets/     : not found\n' "${RED}" "${NC}"
    fi

    if ${SNAP_TOKENS}; then
        printf '  %s✓%s policy_token/ : %d token(s)\n' "${GREEN}" "${NC}" "${SNAP_TOK_COUNT}"
    else
        printf '  %s✗%s policy_token/ : not found\n' "${RED}" "${NC}"
    fi

    printf '\n'
    printf '  %s%s%s\n\n' "${CYAN}" "$(printf '─%.0s' $(seq 1 56))" "${NC}"
}

# ==========================================
# MAIN MENU
# ==========================================

# Build snapshot once at startup
_build_snapshot

while true; do
    _show_welcome

    printf '  %sSelect your role:%s\n\n' "${BOLD}" "${NC}"

    printf '  %s┌─ Roles %s┐%s\n' "${CYAN}" "$(printf '─%.0s' $(seq 1 44))" "${NC}"
    printf '  %s└%s┘%s\n\n' "${CYAN}" "$(printf '─%.0s' $(seq 1 52))" "${NC}"

    printf '   1)  %sUser%s\n' "${BOLD}" "${NC}"
    printf '       Run workflows, manage packages and certificates\n\n'

    printf '   2)  %sAdmin%s\n' "${BOLD}" "${NC}"
    printf '       Deploy and manage the Brane infrastructure\n\n'

    printf '   3)  %sPolicy Manager%s\n' "${BOLD}" "${NC}"
    printf '       Add and activate domain policies\n\n'

    printf '  %s\n' "$(printf '─%.0s' $(seq 1 54))"
    printf '   q)  Exit\n'
    printf '\n'
    read -r -p "  Choose your role [1-3 or q]: " choice
    printf '\n'

    case "${choice}" in
        1)
            exec bash "${SCRIPT_DIR}/brane_helper_user.sh"
            ;;
        2)
            exec bash "${SCRIPT_DIR}/brane_helper_admin.sh"
            ;;
        3)
            exec bash "${SCRIPT_DIR}/brane_helper_policy.sh"
            ;;
        q|Q)
            printf '  Goodbye!\n\n'
            exit 0
            ;;
        *)
            log_error "Invalid option '${choice}'."
            sleep 1
            # Rebuild snapshot on each loop iteration
            _build_snapshot
            ;;
    esac
done

