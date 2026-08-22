#!/usr/bin/env bash
# brane_gen_cert.sh
# Issue one Brane user client-certificate bundle from an active remote domain CA.
# The CA private key stays on the selected Brane node at all times.

set -euo pipefail

# ── Resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CONFIG_FILE="${BRANE_HELPER_CONFIG:-${SCRIPT_DIR}/.brane_helper.env}"
if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "[ERROR] Config file not found: ${CONFIG_FILE}" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "${CONFIG_FILE}"

BRANE_DEPLOY_HOME="${BRANE_DEPLOY_HOME:-${REPO_ROOT}/docker-deployment}"
ANSIBLE_INVENTORY="${BRANE_DEPLOY_HOME}/inventories/production/hosts.ini"
INSTANCE_NAME="${INSTANCE_NAME:-my-brane}"
LOCAL_CERTS_ROOT="${REPO_ROOT}/certs/users"
REMOTE_BRANECTL_BIN="${REMOTE_BRANECTL_BIN:-\$HOME/.local/bin/branectl}"

# ── Options ──────────────────────────────────────────────────────────────────
SELECTED_NODE=""
RECIPIENT_NAME=""
RECIPIENT_EMAIL=""
CLIENT_ID=""
OUTPUT_NAME=""
FORCE=0

usage() {
    cat <<'EOF'
Usage:
  bash scripts/brane_gen_cert.sh [OPTIONS]

Issue one Brane user client-certificate bundle for a selected domain.

The interactive form asks the administrator for the target domain, recipient
name, and recipient email address. It derives a safe internal client identity
from the email address. The recipient never provides CA material.

Options:
  -i, --inventory PATH        Ansible inventory to use.
  -n, --node NAME             Select this inventory node without prompting.
      --recipient-name NAME   Recipient's administrative/display name.
      --recipient-email EMAIL Recipient's email address.
      --client-id ID          Explicit internal identity (admin override).
  -o, --output-dir PATH       Local root for issued bundles.
                              Default: <repository-root>/certs/users
      --output-name NAME      Bundle directory name below the output root.
                              Default: <client-id>-<selected-host>
  -f, --force                 Permit replacement of an existing local bundle.
  -h, --help                  Show this help message.

Output bundle:
  <output-root>/<bundle-name>/ca.pem
  <output-root>/<bundle-name>/client-id.pem

client-id.pem contains the recipient's private key and must be shared only
through an approved secure delivery mechanism. This script does not email it.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --inventory|-i)
            [[ $# -ge 2 ]] || { echo "[ERROR] Missing value for $1" >&2; exit 2; }
            ANSIBLE_INVENTORY="$2"; shift 2 ;;
        --node|-n)
            [[ $# -ge 2 ]] || { echo "[ERROR] Missing value for $1" >&2; exit 2; }
            SELECTED_NODE="$2"; shift 2 ;;
        --recipient-name)
            [[ $# -ge 2 ]] || { echo "[ERROR] Missing value for $1" >&2; exit 2; }
            RECIPIENT_NAME="$2"; shift 2 ;;
        --recipient-email)
            [[ $# -ge 2 ]] || { echo "[ERROR] Missing value for $1" >&2; exit 2; }
            RECIPIENT_EMAIL="$2"; shift 2 ;;
        --client-id)
            [[ $# -ge 2 ]] || { echo "[ERROR] Missing value for $1" >&2; exit 2; }
            CLIENT_ID="$2"; shift 2 ;;
        --output-dir|-o)
            [[ $# -ge 2 ]] || { echo "[ERROR] Missing value for $1" >&2; exit 2; }
            LOCAL_CERTS_ROOT="$2"; shift 2 ;;
        --output-name)
            [[ $# -ge 2 ]] || { echo "[ERROR] Missing value for $1" >&2; exit 2; }
            OUTPUT_NAME="$2"; shift 2 ;;
        --force|-f)
            FORCE=1; shift ;;
        --help|-h)
            usage; exit 0 ;;
        *)
            echo "[ERROR] Unknown argument: $1" >&2
            usage >&2
            exit 2 ;;
    esac
done

# ── Logging ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; BLUE='\033[0;34m'
YELLOW='\033[1;33m'; NC='\033[0m'
log_info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Helpers ──────────────────────────────────────────────────────────────────
require_value_without_newline() {
    local label="$1" value="$2"
    [[ -n "${value}" && "${value}" != *$'\n'* && "${value}" != *$'\r'* && "${value}" != *$'\t'* ]] || {
        log_error "${label} must not be empty or contain tabs/newlines."
        exit 2
    }
}

normalise_client_id() {
    # Derive a conservative hostname-safe identity from the local part of email.
    # Examples: A.Smith+project@uva.nl -> a-smith-project
    local email="$1" local_part id
    local_part="${email%@*}"
    id="$(printf '%s' "${local_part}" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g')"
    [[ -n "${id}" ]] || return 1
    printf '%.63s' "${id}"
}

validate_client_id() {
    local id="$1"
    [[ "${id}" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$|^[a-z0-9]$ ]] || {
        log_error "Invalid client identity '${id}'. Use 1-63 lowercase letters, digits, and hyphens; it must begin and end with a letter or digit."
        exit 2
    }
}

REMOTE_TMP_DIR=""
REMOTE_CLEANUP_HOST=""
REMOTE_CLEANUP_USER=""
cleanup() {
    local status=$?
    if [[ -n "${REMOTE_TMP_DIR}" && -n "${REMOTE_CLEANUP_HOST}" && -n "${REMOTE_CLEANUP_USER}" ]]; then
        ssh -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR -o ConnectTimeout=10 \
            "${REMOTE_CLEANUP_USER}@${REMOTE_CLEANUP_HOST}" \
            "rm -rf -- '${REMOTE_TMP_DIR}'" >/dev/null 2>&1 || true
    fi
    exit "${status}"
}
trap cleanup EXIT INT TERM

# ── Preflight ────────────────────────────────────────────────────────────────
command -v ansible >/dev/null 2>&1 || { log_error "ansible not found. Activate the deployment virtual environment."; exit 1; }
command -v ssh >/dev/null 2>&1 || { log_error "ssh not found."; exit 1; }
command -v scp >/dev/null 2>&1 || { log_error "scp not found."; exit 1; }

[[ -f "${ANSIBLE_INVENTORY}" ]] || { log_error "Inventory not found: ${ANSIBLE_INVENTORY}"; exit 1; }

ansible_var() {
    local group="$1" variable="$2"
    ansible "${group}" -i "${ANSIBLE_INVENTORY}" \
        --playbook-dir "${BRANE_DEPLOY_HOME}" \
        -m debug -a "msg={{ ${variable} }}" --one-line 2>/dev/null \
        | sed -n 's/.*"msg": "\([^"]*\)".*/\1/p' | head -1
}

log_info "Reading inventory: ${ANSIBLE_INVENTORY}"
ANSIBLE_USER="$(ansible_var all ansible_user)"
CENTRAL_HOST="$(ansible_var central ansible_host)"
CENTRAL_DIR="$(ansible_var central brane_central_install_dir)"
WORKER_DIR="$(ansible_var workers brane_worker_install_dir)"

[[ -n "${ANSIBLE_USER}" && -n "${CENTRAL_HOST}" && -n "${CENTRAL_DIR}" && -n "${WORKER_DIR}" ]] || {
    log_error "Could not resolve required connection or installation variables from the inventory."
    exit 1
}

#mapfile -t WORKER_NAMES < <(ansible workers -i "${ANSIBLE_INVENTORY}" --playbook-dir "${BRANE_DEPLOY_HOME}" -m debug -a 'msg={{ inventory_hostname }}' --one-line 2>/dev/null | sed -n 's/.*"msg": "\([^"]*\)".*/\1/p')
#mapfile -t WORKER_HOSTS < <(ansible workers -i "${ANSIBLE_INVENTORY}" --playbook-dir "${BRANE_DEPLOY_HOME}" -m debug -a 'msg={{ ansible_host }}' --one-line 2>/dev/null | sed -n 's/.*"msg": "\([^"]*\)".*/\1/p')

WORKER_NAMES=()
while IFS= read -r line; do
    [[ -n "${line}" ]] && WORKER_NAMES+=("${line}")
done < <(
    ansible workers -i "${ANSIBLE_INVENTORY}" \
        --playbook-dir "${BRANE_DEPLOY_HOME}" \
        -m debug -a 'msg={{ inventory_hostname }}' --one-line 2>/dev/null \
        | sed -n 's/.*"msg": "\([^"]*\)".*/\1/p'
)

WORKER_HOSTS=()
while IFS= read -r line; do
    [[ -n "${line}" ]] && WORKER_HOSTS+=("${line}")
done < <(
    ansible workers -i "${ANSIBLE_INVENTORY}" \
        --playbook-dir "${BRANE_DEPLOY_HOME}" \
        -m debug -a 'msg={{ ansible_host }}' --one-line 2>/dev/null \
        | sed -n 's/.*"msg": "\([^"]*\)".*/\1/p'
)

NODE_NAMES=("central" "${WORKER_NAMES[@]}")
NODE_HOSTS=("${CENTRAL_HOST}" "${WORKER_HOSTS[@]}")

# ── Target-domain selection ──────────────────────────────────────────────────
echo
printf '  Available domains:\n'
for idx in "${!NODE_NAMES[@]}"; do
    printf '    [%d] %-20s (%s)\n' "$((idx + 1))" "${NODE_NAMES[$idx]}" "${NODE_HOSTS[$idx]}"
done
echo

if [[ -n "${SELECTED_NODE}" ]]; then
    CHOICE=""
    for idx in "${!NODE_NAMES[@]}"; do
        if [[ "${NODE_NAMES[$idx]}" == "${SELECTED_NODE}" ]]; then
            CHOICE="$((idx + 1))"
            break
        fi
    done
    [[ -n "${CHOICE}" ]] || { log_error "Unknown node/domain '${SELECTED_NODE}'."; exit 2; }
    log_info "Selected domain from command line: ${SELECTED_NODE}"
else
    while true; do
        read -r -p "  Select target domain [1-${#NODE_NAMES[@]}]: " CHOICE
        [[ "${CHOICE}" =~ ^[0-9]+$ ]] && (( CHOICE >= 1 && CHOICE <= ${#NODE_NAMES[@]} )) && break
        log_error "Invalid choice."
    done
fi

SEL_NODE="${NODE_NAMES[$((CHOICE - 1))]}"
SEL_HOST="${NODE_HOSTS[$((CHOICE - 1))]}"
if [[ "${SEL_NODE}" == "central" ]]; then
    REMOTE_CERT_DIR="${CENTRAL_DIR}/config/certs"
else
    REMOTE_CERT_DIR="${WORKER_DIR}/config/certs"
fi

# ── Recipient details and identity ───────────────────────────────────────────
if [[ -z "${RECIPIENT_NAME}" ]]; then
    read -r -p "  Recipient name: " RECIPIENT_NAME
fi
if [[ -z "${RECIPIENT_EMAIL}" ]]; then
    read -r -p "  Recipient email address: " RECIPIENT_EMAIL
fi
require_value_without_newline "Recipient name" "${RECIPIENT_NAME}"
require_value_without_newline "Recipient email address" "${RECIPIENT_EMAIL}"
[[ "${RECIPIENT_EMAIL}" =~ ^[^[:space:]@]+@[^[:space:]@]+$ ]] || { log_error "Recipient email address is not valid."; exit 2; }

if [[ -z "${CLIENT_ID}" ]]; then
    CLIENT_ID="$(normalise_client_id "${RECIPIENT_EMAIL}")" || {
        log_error "Could not derive a client identity from '${RECIPIENT_EMAIL}'. Supply --client-id explicitly."
        exit 2
    }
fi
validate_client_id "${CLIENT_ID}"

BUNDLE_NAME="${OUTPUT_NAME:-${CLIENT_ID}-${SEL_HOST}}"
[[ "${BUNDLE_NAME}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || { log_error "Invalid output bundle name: ${BUNDLE_NAME}"; exit 2; }
LOCAL_DIR="${LOCAL_CERTS_ROOT}/${BUNDLE_NAME}"
REGISTER_FILE="${LOCAL_CERTS_ROOT}/issuance-register.tsv"

if [[ -e "${LOCAL_DIR}" && "${FORCE}" -ne 1 ]]; then
    log_error "Local bundle already exists: ${LOCAL_DIR}"
    log_error "Refusing to overwrite it. Use --force only after confirming that replacement is intended."
    exit 1
fi

printf '\n'
printf '  Target domain:       %s (%s)\n' "${SEL_NODE}" "${SEL_HOST}"
printf '  Recipient:           %s <%s>\n' "${RECIPIENT_NAME}" "${RECIPIENT_EMAIL}"
printf '  Client identity:     %s\n' "${CLIENT_ID}"
printf '  Local bundle path:   %s\n\n' "${LOCAL_DIR}"
read -r -p "  Issue this certificate bundle? [y/N]: " CONFIRM
[[ "${CONFIRM}" =~ ^[Yy]([Ee][Ss])?$ ]] || { log_info "Certificate issuance cancelled."; exit 0; }

# ── Verify active remote CA and Brane generator ──────────────────────────────
log_info "Checking active CA and Brane generator on ${SEL_NODE}..."
ssh -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR -o ConnectTimeout=10 \
    "${ANSIBLE_USER}@${SEL_HOST}" bash -s -- "${REMOTE_CERT_DIR}" "${REMOTE_BRANECTL_BIN}" <<'REMOTE_CHECK'
set -euo pipefail
cert_dir="$1"
branectl_bin="$2"
[ -r "${cert_dir}/ca.pem" ]
[ -r "${cert_dir}/ca-key.pem" ]
[ -x "${branectl_bin}" ]
REMOTE_CHECK

# ── Generate remotely in an isolated temporary directory ─────────────────────
log_info "Generating a client certificate on ${SEL_NODE}; the active deployment certificates will not be modified."
REMOTE_TMP_DIR="$(ssh -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR -o ConnectTimeout=20 \
    "${ANSIBLE_USER}@${SEL_HOST}" bash -s -- "${REMOTE_CERT_DIR}" "${REMOTE_BRANECTL_BIN}" "${CLIENT_ID}" <<'REMOTE_GENERATE'
set -euo pipefail
cert_dir="$1"
branectl_bin="$2"
client_id="$3"
tmp_dir="$(mktemp -d "${HOME}/.brane-user-cert.XXXXXX")"
chmod 700 "${tmp_dir}"
"${branectl_bin}" generate certs client \
    --fix-dirs \
    --path "${tmp_dir}" \
    --ca-cert "${cert_dir}/ca.pem" \
    --ca-key "${cert_dir}/ca-key.pem" \
    "${client_id}" \
    --hostname "${client_id}" >&2
[ -s "${tmp_dir}/ca.pem" ]
[ -s "${tmp_dir}/client-id.pem" ]
printf '%s\n' "${tmp_dir}"
REMOTE_GENERATE
)"
REMOTE_CLEANUP_HOST="${SEL_HOST}"
REMOTE_CLEANUP_USER="${ANSIBLE_USER}"

#[[ "${REMOTE_TMP_DIR}" == "${HOME}"/.brane-user-cert.* ]] || {
[[ "${REMOTE_TMP_DIR}" == /*/.brane-user-cert.* ]] || {
    log_error "Unexpected remote temporary-directory response; refusing to copy files."
    exit 1
}

# ── Download bundle to the administrator control host ─────────────────────────
if [[ -e "${LOCAL_DIR}" ]]; then
    rm -rf -- "${LOCAL_DIR}"
fi
install -d -m 700 "${LOCAL_DIR}"

log_info "Downloading the bundle to the administrator control host..."
scp -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR \
    "${ANSIBLE_USER}@${SEL_HOST}:${REMOTE_TMP_DIR}/ca.pem" \
    "${ANSIBLE_USER}@${SEL_HOST}:${REMOTE_TMP_DIR}/client-id.pem" \
    "${LOCAL_DIR}/"

[[ -s "${LOCAL_DIR}/ca.pem" && -s "${LOCAL_DIR}/client-id.pem" ]] || {
    log_error "Downloaded bundle is incomplete."
    exit 1
}
chmod 644 "${LOCAL_DIR}/ca.pem"
chmod 600 "${LOCAL_DIR}/client-id.pem"

# Record public metadata only. The key itself is never printed or logged.
CERT_METADATA="$(awk '/-----BEGIN CERTIFICATE-----/{copy=1} copy{print} /-----END CERTIFICATE-----/{exit}' "${LOCAL_DIR}/client-id.pem" | openssl x509 -noout -subject -issuer -serial -dates 2>/dev/null || true)"
[[ -n "${CERT_METADATA}" ]] || { log_error "The downloaded client identity does not contain a readable certificate."; exit 1; }

# ── Record administrative issuance mapping ───────────────────────────────────
install -d -m 700 "${LOCAL_CERTS_ROOT}"
if [[ ! -f "${REGISTER_FILE}" ]]; then
    printf 'issued_at_utc\trecipient_name\trecipient_email\tclient_identity\tdomain_node\tdomain_host\tbundle_path\n' > "${REGISTER_FILE}"
    chmod 600 "${REGISTER_FILE}"
fi
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${RECIPIENT_NAME}" "${RECIPIENT_EMAIL}" \
    "${CLIENT_ID}" "${SEL_NODE}" "${SEL_HOST}" "${LOCAL_DIR}" >> "${REGISTER_FILE}"
chmod 600 "${REGISTER_FILE}"

log_success "Certificate bundle issued and saved locally: ${LOCAL_DIR}/"
printf '\n%s\n' "${CERT_METADATA}"
echo
echo -e "  ${YELLOW}Delivery reminder:${NC} client-id.pem contains the recipient's private key."
echo "  Send ca.pem and client-id.pem only through an approved secure delivery channel."
echo "  Issuance register: ${REGISTER_FILE}"
echo
echo -e "  ${YELLOW}Recipient import command:${NC}"
echo "  brane certs add ${LOCAL_DIR}/ca.pem ${LOCAL_DIR}/client-id.pem \\"
echo "    --instance ${INSTANCE_NAME} --domain ${SEL_HOST}"
echo

