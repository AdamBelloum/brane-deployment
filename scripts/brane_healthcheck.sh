#!/usr/bin/env bash
# =============================================================================
# brane_healthcheck.sh — Brane deployment health check
# =============================================================================
#
# Checks on every node in the Ansible inventory:
#   (1) Directory structure — required files and directories exist on host
#   (2) Containers — required containers are running
#
# Usage:
#   ./scripts/brane_healthcheck.sh
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
header() { echo -e "\n${BOLD}${BLUE}$1${NC}"; printf "${BLUE}"; printf '%.0s─' {1..70}; printf "${NC}\n"; }

RESULT_LINES=()
SUMMARY_LINES=()
WORKER_IPS=()
WORKER_HOSTNAMES=()
WORKER_LOCATION_IDS=()
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

while IFS= read -r line; do
  [ -n "$line" ] && WORKER_LOCATION_IDS+=("$line")
done <<EOF
$(ansible_var_all "workers" "location_id")
EOF

if [ -z "$CENTRAL_HOST" ]; then
  err "Could not resolve central host from inventory. Aborting."
  exit 1
fi

log "Central           : $CENTRAL_HOST"
log "Central dir       : $CENTRAL_INSTALL_DIR"
log "Workers           : ${WORKER_IPS[*]}"
log "Worker dir        : $WORKER_INSTALL_DIR"
log "Brane version     : $BRANE_VERSION"
log "Ansible user      : $ANSIBLE_USER"

should_check() {
  [ -z "$NODE_FILTER" ] || [ "$NODE_FILTER" = "$1" ]
}

# =============================================================================
# SSH helpers
# =============================================================================

SSH_OPTS="-o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=5"

check_path() {
  local node=$1 host=$2 path=$3
  local result
  result=$(ssh $SSH_OPTS "${ANSIBLE_USER}@${host}" \
    "test -e \"$path\" && echo 'exists' || echo ''" 2>/dev/null || echo "")
  if [ "$result" = "exists" ]; then
    record "OK"   "$node" "directory" "$path"
  else
    record "FAIL" "$node" "directory" "$path (MISSING)"
  fi
}

check_container() {
  local node=$1 host=$2 name=$3 status
  status=$(ssh $SSH_OPTS "${ANSIBLE_USER}@${host}" \
    "docker inspect --format '{{.State.Status}}' '$name' 2>/dev/null" 2>/dev/null || echo "")
  status=$(echo "$status" | tr -d '[:space:]')
  [ -z "$status" ] && status="missing"
  if [ "$status" = "running" ]; then
    record "OK"   "$node" "container" "$name is running"
  else
    record "FAIL" "$node" "container" "$name is $status (expected: running)"
  fi
}

# =============================================================================
# CENTRAL NODE CHECKS
# =============================================================================

if should_check "central-vm-1"; then
  NODE="central-vm-1"
  HOST="$CENTRAL_HOST"
  CDIR="$CENTRAL_INSTALL_DIR"

  header "Checking central node: $HOST"

  # Directory structure
  check_path "$NODE" "$HOST" "$CDIR"
  check_path "$NODE" "$HOST" "$CDIR/node.yml"
  check_path "$NODE" "$HOST" "$CDIR/config"
  check_path "$NODE" "$HOST" "$CDIR/config/certs"
  check_path "$NODE" "$HOST" "$CDIR/config/infra.yml"
  check_path "$NODE" "$HOST" "$CDIR/config/proxy.yml"
  check_path "$NODE" "$HOST" "$CDIR/packages"

  # Containers
  check_container "$NODE" "$HOST" "brane-api"
  check_container "$NODE" "$HOST" "brane-drv"
  check_container "$NODE" "$HOST" "brane-plr"
  check_container "$NODE" "$HOST" "brane-prx"
fi

# =============================================================================
# WORKER NODE CHECKS
# =============================================================================

i=0
while [ $i -lt ${#WORKER_IPS[@]} ]; do
  HOST="${WORKER_IPS[$i]}"
  NODE="${WORKER_HOSTNAMES[$i]}"
  LOCATION_ID="${WORKER_LOCATION_IDS[$i]}"
  WDIR="$WORKER_INSTALL_DIR"

  if should_check "$NODE"; then
    header "Checking worker node: $NODE ($HOST) [location_id: $LOCATION_ID]"

    # Directory structure
    check_path "$NODE" "$HOST" "$WDIR"
    check_path "$NODE" "$HOST" "$WDIR/node.yml"
    check_path "$NODE" "$HOST" "$WDIR/config"
    check_path "$NODE" "$HOST" "$WDIR/config/certs"
    check_path "$NODE" "$HOST" "$WDIR/config/secrets"
    check_path "$NODE" "$HOST" "$WDIR/policies.db"
    check_path "$NODE" "$HOST" "$WDIR/data"
    check_path "$NODE" "$HOST" "$WDIR/results"
    check_path "$NODE" "$HOST" "$WDIR/packages"

    # Containers — use location_id from inventory
    check_container "$NODE" "$HOST" "brane-prx"
    check_container "$NODE" "$HOST" "brane-reg"
    check_container "$NODE" "$HOST" "brane-job-${LOCATION_ID}"
    check_container "$NODE" "$HOST" "brane-chk-${LOCATION_ID}"
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

ALL_NODES=("central-vm-1")
for h in "${WORKER_HOSTNAMES[@]}"; do ALL_NODES+=("$h"); done

for NODE in "${ALL_NODES[@]}"; do
  should_check "$NODE" || continue
  for CAT in directory container; do
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

