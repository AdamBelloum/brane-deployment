#!/usr/bin/env bash
# brane_gen_cert.sh
# Generate a signed client certificate from a remote Brane node
# and save it locally under ./certs/<node>/
#
# Usage:
#   bash scripts/brane_gen_cert.sh
#   bash scripts/brane_gen_cert.sh --inventory path/to/hosts.ini

set -o nounset
set -o pipefail

# ── Resolve paths ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CONFIG_FILE="${BRANE_HELPER_CONFIG:-${SCRIPT_DIR}/.brane_helper.env}"
if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "[ERROR] Config file not found: ${CONFIG_FILE}"
    exit 1
fi
# shellcheck source=/dev/null
source "${CONFIG_FILE}"

BRANE_DEPLOY_HOME="${BRANE_DEPLOY_HOME:-${REPO_ROOT}/docker-deployment}"
ANSIBLE_INVENTORY="${BRANE_DEPLOY_HOME}/inventories/production/hosts.ini"
INSTANCE_NAME="${INSTANCE_NAME:-my-brane}"

# ── Parse arguments ───────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --inventory|-i) ANSIBLE_INVENTORY="$2"; shift 2 ;;
        *) echo "[WARN] Unknown argument: $1"; shift ;;
    esac
done

# ── Colors ────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'
BLUE='\033[0;34m';  YELLOW='\033[1;33m'; NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

# ── Preflight ─────────────────────────────────────────────
if ! command -v ansible &>/dev/null; then
    log_error "ansible not found. Activate your venv."
    exit 1
fi
if [[ ! -f "${ANSIBLE_INVENTORY}" ]]; then
    log_error "Inventory not found: ${ANSIBLE_INVENTORY}"
    exit 1
fi

# ── Read inventory vars ───────────────────────────────────
log_info "Reading inventory: ${ANSIBLE_INVENTORY}"

ANSIBLE_USER=$(ansible all -i "${ANSIBLE_INVENTORY}" \
    -m debug -a "msg={{ ansible_user }}" --one-line 2>/dev/null \
    | sed -n 's/.*"msg": "\([^"]*\)".*/\1/p' | head -1)

CENTRAL_HOST=$(ansible central -i "${ANSIBLE_INVENTORY}" \
    -m debug -a "msg={{ ansible_host }}" --one-line 2>/dev/null \
    | sed -n 's/.*"msg": "\([^"]*\)".*/\1/p' | head -1)

CENTRAL_DIR=$(ansible central -i "${ANSIBLE_INVENTORY}" \
    -m debug -a "msg={{ brane_central_install_dir }}" --one-line 2>/dev/null \
    | sed -n 's/.*"msg": "\([^"]*\)".*/\1/p' | head -1)

W_DIR=$(ansible workers -i "${ANSIBLE_INVENTORY}" \
    -m debug -a "msg={{ brane_worker_install_dir }}" --one-line 2>/dev/null \
    | sed -n 's/.*"msg": "\([^"]*\)".*/\1/p' | head -1)

W_IPS=$(ansible workers -i "${ANSIBLE_INVENTORY}" \
    -m debug -a "msg={{ ansible_host }}" --one-line 2>/dev/null \
    | sed -n 's/.*"msg": "\([^"]*\)".*/\1/p')

W_NAMES=$(ansible workers -i "${ANSIBLE_INVENTORY}" \
    -m debug -a "msg={{ inventory_hostname }}" --one-line 2>/dev/null \
    | sed -n 's/.*"msg": "\([^"]*\)".*/\1/p')

# ── Build node list ───────────────────────────────────────
NODE_NAMES=("central")
NODE_HOSTS=("$CENTRAL_HOST")

while IFS= read -r line; do
    [ -n "$line" ] && NODE_HOSTS+=("$line")
done <<< "$W_IPS"

while IFS= read -r line; do
    [ -n "$line" ] && NODE_NAMES+=("$line")
done <<< "$W_NAMES"

# ── Node selection menu ───────────────────────────────────
echo ""
echo "  Available nodes:"
idx=0
while [ $idx -lt ${#NODE_NAMES[@]} ]; do
    printf "    [%d] %-20s (%s)\n" "$((idx+1))" "${NODE_NAMES[$idx]}" "${NODE_HOSTS[$idx]}"
    idx=$((idx + 1))
done
echo ""

while true; do
    read -r -p "  Select node [1-${#NODE_NAMES[@]}]: " CHOICE
    [[ "$CHOICE" =~ ^[0-9]+$ ]] && \
        [ "$CHOICE" -ge 1 ] && [ "$CHOICE" -le "${#NODE_NAMES[@]}" ] && break
    log_error "Invalid choice."
done

SEL_NODE="${NODE_NAMES[$((CHOICE-1))]}"
SEL_HOST="${NODE_HOSTS[$((CHOICE-1))]}"

if [ "$SEL_NODE" = "central" ]; then
    REMOTE_CERT_DIR="${CENTRAL_DIR}/config/certs"
else
    REMOTE_CERT_DIR="${W_DIR}/config/certs"
fi

log_info "Node: $SEL_NODE ($SEL_HOST) — $REMOTE_CERT_DIR"

# ── Verify CA files on remote ─────────────────────────────
CA_CHECK=$(ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=5 \
    "${ANSIBLE_USER}@${SEL_HOST}" \
    "[ -f '${REMOTE_CERT_DIR}/ca.pem' ] && [ -f '${REMOTE_CERT_DIR}/ca-key.pem' ] && echo ok || echo missing")

if [ "$CA_CHECK" != "ok" ]; then
    log_error "ca.pem or ca-key.pem not found in ${REMOTE_CERT_DIR} on ${SEL_HOST}"
    exit 1
fi

# ── Generate client cert on remote (with required extensions) ────
log_info "Generating client certificate on ${SEL_NODE}..."
ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=10 \
    "${ANSIBLE_USER}@${SEL_HOST}" bash <<REMOTE
set -e
cd "${REMOTE_CERT_DIR}"

cat > client_ext.cnf <<EOF
[req]
distinguished_name = req_distinguished_name
req_extensions     = v3_req
prompt             = no

[req_distinguished_name]
CN = ${ANSIBLE_USER}
O  = brane-client

[v3_req]
keyUsage         = critical, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth
EOF

openssl genrsa -out client-key.pem 2048
openssl req -new -key client-key.pem -out client.csr -config client_ext.cnf
openssl x509 -req -in client.csr \
    -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
    -out client.pem -days 365 -sha256 \
    -extfile client_ext.cnf -extensions v3_req
rm -f client.csr client_ext.cnf
REMOTE

if [ $? -ne 0 ]; then
    log_error "Certificate generation failed on ${SEL_NODE}."
    exit 1
fi

# ── Save locally under certs/<node>/ ─────────────────────
LOCAL_DIR="${BRANE_DEPLOY_HOME}/certs/${SEL_NODE}"
[ -d "$LOCAL_DIR" ] || mkdir -p "$LOCAL_DIR"

scp -o StrictHostKeyChecking=no -o LogLevel=ERROR \
    "${ANSIBLE_USER}@${SEL_HOST}:${REMOTE_CERT_DIR}/ca.pem" \
    "${ANSIBLE_USER}@${SEL_HOST}:${REMOTE_CERT_DIR}/client.pem" \
    "${ANSIBLE_USER}@${SEL_HOST}:${REMOTE_CERT_DIR}/client-key.pem" \
    "${LOCAL_DIR}/"

if [ $? -ne 0 ]; then
    log_error "Failed to copy certificates from ${SEL_NODE}."
    exit 1
fi

log_success "Certificates saved to: ${LOCAL_DIR}/"
echo ""
echo -e "  ${YELLOW}Next step:${NC}"
echo "  brane certs add ${LOCAL_DIR}/ca.pem ${LOCAL_DIR}/client.pem ${LOCAL_DIR}/client-key.pem \\"
echo "    --instance ${INSTANCE_NAME} --domain ${SEL_HOST}"
echo ""

