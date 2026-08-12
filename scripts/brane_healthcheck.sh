#!/usr/bin/env bash
# =============================================================================
# brane_healthcheck.sh — Brane deployment health check
# =============================================================================
#
# Checks on every node in the Ansible inventory:
#   - Required Docker containers are running
#   - Services are listening on the correct ports
#   - Required volume mounts are present on each container
#
# Usage:
#   ./scripts/brane_healthcheck.sh
#   ./scripts/brane_healthcheck.sh --node central
#   ./scripts/brane_healthcheck.sh --node worker-vm-2
#   ./scripts/brane_healthcheck.sh --report
#
# Exit code:
#   0  — all checks passed
#   1  — one or more checks failed
#
# Compatible with Bash 3.2+ (macOS) and Bash 4/5 (Linux).
# =============================================================================

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

log()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
warn()   { echo -e "${YELLOW}[WARN]${NC}  $1"; }
err()    { echo -e "${RED}[ERROR]${NC} $1"; }
header() { echo -e "\n${BOLD}${BLUE}$1${NC}"; \
           printf "${BLUE}"; printf '%.0s─' {1..70}; printf "${NC}\n"; }

RESULT_LINES=()
SUMMARY_LINES=()
WORKER_IPS=()
WORKER_HOSTNAMES=()
TOTAL_PASS=0
TOTAL_FAIL=0

record() {
  local status=$1 node=$2 category=$3 message=$4
  if [ "$status" = "OK" ]; then
    RESULT_LINES+=("${GREEN}[OK]${NC}   [$node] [$category] $message")
    TOTAL_PASS=$((TOTAL_PASS + 1))
  else
    RESULT_LINES+=("${RED}[FAIL]${NC} [$node] [$category] $message")
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
  fi
}

INVENTORY="inventories/production/hosts.ini"
REPORT=false
NODE_FILTER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --inventory|-i) INVENTORY="$2"; shift 2 ;;
    --report|-r)    REPORT=true; shift ;;
    --node|-n)      NODE_FILTER="$2"; shift 2 ;;
    *) warn "Unknown argument: $1"; shift ;;
  esac
done

if [ ! -f "$INVENTORY" ]; then
  err "Inventory file not found: $INVENTORY"
  exit 1
fi

if ! command -v ansible &>/dev/null; then
  err "ansible not found. Activate your venv."
  exit 1
fi

log "Reading infrastructure from inventory: $INVENTORY"
[ -n "$NODE_FILTER" ] && log "Node filter       : $NODE_FILTER"

ansible_var() {
  local group=$1 var=$2 tmpfile result
  tmpfile=$(mktemp)
  ansible "$group" -i "$INVENTORY" \
    -m debug -a "msg={{ $var }}" --one-line 2>/dev/null > "$tmpfile" || true
  result=$(sed -n 's/.*"msg": "\([^"]*\)".*/\1/p' "$tmpfile" | head -1)
  rm -f "$tmpfile"
  case "$result" in
    *" "*) echo "" ;;
    *)     echo "$result" ;;
  esac
}

ansible_var_all() {
  local group=$1 var=$2 tmpfile
  tmpfile=$(mktemp)
  ansible "$group" -i "$INVENTORY" \
    -m debug -a "msg={{ $var }}" --one-line 2>/dev/null > "$tmpfile" || true
  sed -n 's/.*"msg": "\([^"]*\)".*/\1/p' "$tmpfile" | grep -v ' ' || true
  rm -f "$tmpfile"
}

CENTRAL_HOST=$(ansible_var        "central" "ansible_host")
ANSIBLE_USER=$(ansible_var        "central" "ansible_user")
CENTRAL_INSTALL_DIR=$(ansible_var "central" "brane_central_install_dir")
WORKER_INSTALL_DIR=$(ansible_var  "workers" "brane_worker_install_dir")
BRANE_VERSION=$(ansible_var       "central" "brane_image_tag")

CENTRAL_API_PORT=$(ansible_var "central" "brane_api_port")
CENTRAL_DRV_PORT=$(ansible_var "central" "brane_drv_port")
WORKER_REG_PORT=$(ansible_var  "workers" "brane_reg_port")
WORKER_JOB_PORT=$(ansible_var  "workers" "brane_job_port")

[ -z "$CENTRAL_API_PORT" ] && CENTRAL_API_PORT="50051"
[ -z "$CENTRAL_DRV_PORT" ] && CENTRAL_DRV_PORT="50053"
[ -z "$WORKER_REG_PORT"  ] && WORKER_REG_PORT="50051"
[ -z "$WORKER_JOB_PORT"  ] && WORKER_JOB_PORT="50052"

while IFS= read -r line; do
  [ -n "$line" ] && WORKER_IPS+=("$line")
done <<EOF
$(ansible_var_all "workers" "ansible_host")
EOF

while IFS= read -r line; do
  [ -n "$line" ] && WORKER_HOSTNAMES+=("$line")
done <<EOF
$(ansible_var_all "workers" "inventory_hostname")
EOF

if [ -z "$CENTRAL_HOST" ]; then
  err "Could not resolve central host from inventory. Aborting."
  exit 1
fi

log "Central           : $CENTRAL_HOST"
log "Central dir       : $CENTRAL_INSTALL_DIR"
log "Central ports     : api=$CENTRAL_API_PORT  drv=$CENTRAL_DRV_PORT"
log "Workers           : ${WORKER_IPS[*]}"
log "Worker dir        : $WORKER_INSTALL_DIR"
log "Worker ports      : reg=$WORKER_REG_PORT  job=$WORKER_JOB_PORT"
log "Brane version     : $BRANE_VERSION"
log "Ansible user      : $ANSIBLE_USER"

should_check() {
  [ -z "$NODE_FILTER" ] || [ "$NODE_FILTER" = "$1" ]
}

# ── Remote command execution with proper quoting ────────────────────────────────
# Use printf %q to properly escape arguments for SSH transmission.

remote() {
  local host=$1; shift
  local cmd
  # Build the command with proper escaping for SSH
  cmd=$(printf '%s ' "$@")
  ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=5 \
      "${ANSIBLE_USER}@${host}" "$cmd" 2>/dev/null || true
}

check_container() {
  local node=$1 host=$2 name=$3 status
  status=$(remote "$host" docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || echo "missing")
  status=$(echo "$status" | tr -d '[:space:]')
  if [ "$status" = "running" ]; then
    record "OK"   "$node" "container" "$name is running"
  else
    record "FAIL" "$node" "container" "$name is ${status:-missing} (expected: running)"
  fi
}

check_port() {
  local node=$1 host=$2 port=$3 label=$4 result
  result=$(remote "$host" ss -tlnp | grep ":${port}" || true)
  if [ -n "$result" ]; then
    record "OK"   "$node" "port" "$port ($label) is listening"
  else
    record "FAIL" "$node" "port" "$port ($label) is NOT listening"
  fi
}

check_mount() {
  local node=$1 host=$2 container=$3 path=$4 mounted
  # Pass the docker inspect command with proper quoting
  mounted=$(remote "$host" "docker inspect --format '{{range .Mounts}}{{.Destination}}|{{end}}' $container" 2>/dev/null || echo "")
  if echo "$mounted" | grep -qF "${path}|"; then
    record "OK"   "$node" "mount" "$container → $path"
  else
    record "FAIL" "$node" "mount" "$container → $path (MISSING)"
  fi
}

# =============================================================================
# CENTRAL NODE CHECKS
# =============================================================================

if should_check "central"; then
  NODE="central"
  HOST="$CENTRAL_HOST"
  CDIR="$CENTRAL_INSTALL_DIR"

  check_container "$NODE" "$HOST" "brane-api"
  check_container "$NODE" "$HOST" "brane-drv"
  check_container "$NODE" "$HOST" "brane-plr"
  check_container "$NODE" "$HOST" "brane-prx"

  check_port "$NODE" "$HOST" "$CENTRAL_API_PORT" "brane-api"
  check_port "$NODE" "$HOST" "$CENTRAL_DRV_PORT" "brane-drv"

  # brane-api mounts: /node.yml, packages, config/infra.yml, config/certs
  check_mount "$NODE" "$HOST" "brane-api" "/node.yml"
  check_mount "$NODE" "$HOST" "brane-api" "${CDIR}/packages"
  check_mount "$NODE" "$HOST" "brane-api" "${CDIR}/config/infra.yml"
  check_mount "$NODE" "$HOST" "brane-api" "${CDIR}/config/certs"

  # brane-drv mounts: /node.yml, config/certs, config/infra.yml
  check_mount "$NODE" "$HOST" "brane-drv" "/node.yml"
  check_mount "$NODE" "$HOST" "brane-drv" "${CDIR}/config/certs"
  check_mount "$NODE" "$HOST" "brane-drv" "${CDIR}/config/infra.yml"

  # brane-plr mounts: /node.yml, config/infra.yml
  check_mount "$NODE" "$HOST" "brane-plr" "/node.yml"
  check_mount "$NODE" "$HOST" "brane-plr" "${CDIR}/config/infra.yml"

  # brane-prx mounts: /node.yml, config/proxy.yml, config/certs
  check_mount "$NODE" "$HOST" "brane-prx" "/node.yml"
  check_mount "$NODE" "$HOST" "brane-prx" "${CDIR}/config/proxy.yml"
  check_mount "$NODE" "$HOST" "brane-prx" "${CDIR}/config/certs"
fi

# =============================================================================
# WORKER NODE CHECKS
# =============================================================================

i=0
while [ $i -lt ${#WORKER_IPS[@]} ]; do
  HOST="${WORKER_IPS[$i]}"
  NODE="${WORKER_HOSTNAMES[$i]}"
  WDIR="$WORKER_INSTALL_DIR"
  JOB_NAME="brane-job-${NODE}"
  CHK_NAME="brane-chk-${NODE}"

  if should_check "$NODE"; then
    check_container "$NODE" "$HOST" "brane-prx"
    check_container "$NODE" "$HOST" "brane-reg"
    check_container "$NODE" "$HOST" "$JOB_NAME"
    check_container "$NODE" "$HOST" "$CHK_NAME"

    check_port "$NODE" "$HOST" "$WORKER_REG_PORT" "brane-reg"
    check_port "$NODE" "$HOST" "$WORKER_JOB_PORT" "brane-job"

    check_mount "$NODE" "$HOST" "brane-prx" "/node.yml"
    check_mount "$NODE" "$HOST" "brane-prx" "${WDIR}/config/certs"

    check_mount "$NODE" "$HOST" "brane-reg" "/node.yml"
    check_mount "$NODE" "$HOST" "brane-reg" "${WDIR}/config/certs"
    check_mount "$NODE" "$HOST" "brane-reg" "${WDIR}/config/secrets"
    check_mount "$NODE" "$HOST" "brane-reg" "${WDIR}/policies.db"
    check_mount "$NODE" "$HOST" "brane-reg" "${WDIR}/data"
    check_mount "$NODE" "$HOST" "brane-reg" "${WDIR}/results"

    check_mount "$NODE" "$HOST" "$CHK_NAME" "/node.yml"
    check_mount "$NODE" "$HOST" "$CHK_NAME" "${WDIR}/config/certs"
    check_mount "$NODE" "$HOST" "$CHK_NAME" "${WDIR}/config/secrets"
    check_mount "$NODE" "$HOST" "$CHK_NAME" "${WDIR}/policies.db"

    check_mount "$NODE" "$HOST" "$JOB_NAME" "/node.yml"
    check_mount "$NODE" "$HOST" "$JOB_NAME" "${WDIR}/config/certs"
    check_mount "$NODE" "$HOST" "$JOB_NAME" "${WDIR}/packages"
    check_mount "$NODE" "$HOST" "$JOB_NAME" "${WDIR}/data"
    check_mount "$NODE" "$HOST" "$JOB_NAME" "${WDIR}/results"
    check_mount "$NODE" "$HOST" "$JOB_NAME" "/var/run/docker.sock"
  fi

  i=$((i + 1))
done

# =============================================================================
# OUTPUT
# =============================================================================

if [ "$REPORT" = true ]; then
  header "Full check results"
  for line in "${RESULT_LINES[@]}"; do
    echo -e "  $line"
  done
fi

header "Health report — $(date '+%Y-%m-%d %H:%M:%S')"

ALL_NODES=("central")
for h in "${WORKER_HOSTNAMES[@]}"; do ALL_NODES+=("$h"); done

for NODE in "${ALL_NODES[@]}"; do
  should_check "$NODE" || continue
  for CAT in container port mount; do
    CAT_PASS=0; CAT_FAIL=0
    for line in "${RESULT_LINES[@]}"; do
      echo "$line" | grep -q "\[$NODE\]" || continue
      echo "$line" | grep -q "\[$CAT\]"  || continue
      if echo "$line" | grep -q "\[OK\]"; then
        CAT_PASS=$((CAT_PASS + 1))
      else
        CAT_FAIL=$((CAT_FAIL + 1))
      fi
    done
    if [ "$CAT_FAIL" -gt 0 ]; then
      SUMMARY_LINES+=("${RED}[FAIL]${NC} $NODE | $CAT: $CAT_PASS ok, $CAT_FAIL failed")
    else
      SUMMARY_LINES+=("${GREEN}[OK]${NC}   $NODE | $CAT: $CAT_PASS ok")
    fi
  done
done

for line in "${SUMMARY_LINES[@]}"; do echo -e "  $line"; done

echo ""
echo -e "  ${BOLD}Total: ${GREEN}${TOTAL_PASS} passed${NC}  ${BOLD}${RED}${TOTAL_FAIL} failed${NC}"
printf "${BLUE}"; printf '%.0s─' {1..70}; printf "${NC}\n"

if [ "$TOTAL_FAIL" -gt 0 ]; then
  echo -e "${RED}${BOLD}  Deployment is UNHEALTHY. Run with --report for full details.${NC}"
  exit 1
else
  echo -e "${GREEN}${BOLD}  Deployment is HEALTHY.${NC}"
  exit 0
fi

