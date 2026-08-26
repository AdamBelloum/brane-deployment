#!/usr/bin/env bash
# =============================================================================
# brane_healthcheck.sh — Brane deployment health check
# =============================================================================
# Read-only Tier 1 deployment gate. It checks active Docker/Compose topology,
# not Brane CLI profiles, packages, policies, or workflow execution.
# Compatible with Bash 3.2+ (macOS) and Bash 4/5 (Linux).
# =============================================================================

set -o pipefail

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

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
INVENTORY="$SCRIPT_DIR/../docker-deployment/inventories/production/hosts.ini"
REPORT=false
NODE_FILTER=""

usage() {
  cat <<USAGE
Usage: $0 [--inventory PATH] [--node INVENTORY_HOSTNAME] [--report]

Options:
  --inventory, -i  Ansible inventory path
  --node, -n       Check only one inventory hostname
  --report, -r     Print every individual result
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --inventory|-i)
      [ $# -ge 2 ] || { err "Missing value for $1"; exit 1; }
      INVENTORY=$2; shift 2 ;;
    --node|-n)
      [ $# -ge 2 ] || { err "Missing value for $1"; exit 1; }
      NODE_FILTER=$2; shift 2 ;;
    --report|-r) REPORT=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) err "Unknown argument: $1"; usage; exit 1 ;;
  esac
done

if [ ! -f "$INVENTORY" ]; then
  err "Inventory file not found: $INVENTORY"
  exit 1
fi

if ! command -v ansible >/dev/null 2>&1; then
  err "ansible not found. Activate your venv."
  exit 1
fi

# These lookups intentionally request only inventory-visible topology values.
# Role defaults are not available to ad-hoc Ansible calls and are not used here.
ansible_var() {
  local group=$1 var=$2 tmpfile result
  tmpfile=$(mktemp)
  ansible "$group" -i "$INVENTORY" \
    -m debug -a "msg={{ $var }}" --one-line 2>/dev/null > "$tmpfile" || true
  result=$(sed -n 's/.*"msg": "\([^"]*\)".*/\1/p' "$tmpfile" | head -1)
  rm -f "$tmpfile"
  case "$result" in
    *" "*) echo "" ;;
    *) echo "$result" ;;
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

CENTRAL_HOST=$(ansible_var "central" "ansible_host")
CENTRAL_NODE=$(ansible_var "central" "inventory_hostname")
ANSIBLE_USER=$(ansible_var "central" "ansible_user")
[ -n "$CENTRAL_NODE" ] || CENTRAL_NODE="central"
[ -n "$ANSIBLE_USER" ] || ANSIBLE_USER="adam"
[ -n "$CENTRAL_HOST" ] || CENTRAL_HOST="$CENTRAL_NODE"

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

if [ ${#WORKER_IPS[@]} -ne ${#WORKER_HOSTNAMES[@]} ] || \
   [ ${#WORKER_IPS[@]} -ne ${#WORKER_LOCATION_IDS[@]} ]; then
  err "Worker inventory values could not be resolved consistently. Aborting."
  exit 1
fi

log "Reading infrastructure from inventory: $INVENTORY"
[ -n "$NODE_FILTER" ] && log "Node filter       : $NODE_FILTER"
log "Central           : $CENTRAL_NODE ($CENTRAL_HOST)"
log "Workers           : ${WORKER_HOSTNAMES[*]}"
log "Ansible user      : $ANSIBLE_USER"

should_check() {
  [ -z "$NODE_FILTER" ] || [ "$NODE_FILTER" = "$1" ]
}

SSH_OPTS="-o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=5"

ssh_remote() {
  local host=$1 command=$2
  ssh $SSH_OPTS "${ANSIBLE_USER}@${host}" "$command"
}

trim_line() {
  printf '%s' "$1" | tr -d '\r\n'
}

check_path() {
  local node=$1 host=$2 path=$3 result
  if [ -z "$path" ]; then
    record "FAIL" "$node" "path" "expected path is unavailable from active configuration"
    return
  fi
  result=$(ssh_remote "$host" "test -e '$path' && echo exists || true" 2>/dev/null || true)
  if [ "$(trim_line "$result")" = "exists" ]; then
    record "OK" "$node" "path" "$path"
  else
    record "FAIL" "$node" "path" "$path (MISSING)"
  fi
}

check_container() {
  local node=$1 host=$2 name=$3 status
  status=$(ssh_remote "$host" \
    "docker inspect --format '{{.State.Status}}' '$name' 2>/dev/null" 2>/dev/null || true)
  status=$(trim_line "$status")
  [ -n "$status" ] || status="missing"
  if [ "$status" = "running" ]; then
    record "OK" "$node" "container" "$name is running"
  else
    record "FAIL" "$node" "container" "$name is $status (expected: running)"
  fi
}

check_compose_service() {
  local node=$1 host=$2 service=$3 result name state
  result=$(ssh_remote "$host" \
    "docker ps -a --filter 'label=com.docker.compose.service=$service' \
      --format '{{.Names}}|{{.State}}' 2>/dev/null" \
    2>/dev/null | head -n 1 || true)
  result=$(trim_line "$result")

  if [ -z "$result" ]; then
    record "FAIL" "$node" "container" \
      "$service Compose service is missing (expected: running)"
    return
  fi

  name=${result%%|*}
  state=${result#*|}
  if [ "$state" = "running" ]; then
    record "OK" "$node" "container" \
      "$service ($name) is running"
  else
    record "FAIL" "$node" "container" \
      "$service ($name) is $state (expected: running)"
  fi
}

check_image() {
  local node=$1 host=$2 container=$3 repository=$4 tag=$5 actual expected
  expected="${repository}:${tag}"
  if [ -z "$tag" ]; then
    record "FAIL" "$node" "image" "$container expected tag is unavailable from active configuration"
    return
  fi
  actual=$(ssh_remote "$host" \
    "docker inspect --format '{{.Config.Image}}' '$container' 2>/dev/null" 2>/dev/null || true)
  actual=$(trim_line "$actual")
  if [ "$actual" = "$expected" ]; then
    record "OK" "$node" "image" "$container uses $expected"
  else
    [ -n "$actual" ] || actual="missing"
    record "FAIL" "$node" "image" "$container uses $actual (expected: $expected)"
  fi
}

check_port() {
  local node=$1 host=$2 port=$3 result
  if [ -z "$port" ]; then
    record "FAIL" "$node" "port" "expected port is unavailable from active configuration"
    return
  fi
  result=$(ssh_remote "$host" \
    "ss -ltnH 2>/dev/null | awk '{print \$4}' | grep -Eq '[:.]${port}\$' && echo listening || true" \
    2>/dev/null || true)
  if [ "$(trim_line "$result")" = "listening" ]; then
    record "OK" "$node" "port" "$port is listening"
  else
    record "FAIL" "$node" "port" "$port is not listening"
  fi
}

CURRENT_MOUNTS=""
load_mounts() {
  local host=$1 container=$2
  CURRENT_MOUNTS=$(ssh_remote "$host" \
    "docker inspect --format '{{range .Mounts}}{{.Source}}|{{.Destination}}{{printf \"\\n\"}}{{end}}' '$container' 2>/dev/null" \
    2>/dev/null || true)
}

check_mount() {
  local node=$1 container=$2 source=$3 destination=$4
  if [ -z "$source" ] || [ -z "$destination" ]; then
    record "FAIL" "$node" "mount" "$container expected mount is unavailable from active configuration"
    return
  fi
  if printf '%s\n' "$CURRENT_MOUNTS" | grep -Fqx "${source}|${destination}"; then
    record "OK" "$node" "mount" "$container: $destination"
  else
    record "FAIL" "$node" "mount" "$container missing $source -> $destination"
  fi
}

# The only .env access is a strict allow-list. DELIB_TOKEN and all other
# non-listed values are never read into output or printed.
fetch_public_env() {
  local host=$1 directory=$2 allowed_regex=$3 destination=$4
  ssh_remote "$host" \
    "awk -F= '\$1 ~ /${allowed_regex}/ {print}' '$directory/.env' 2>/dev/null" \
    > "$destination" 2>/dev/null || true
}

env_value() {
  local env_file=$1 key=$2
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$env_file"
}

resolve_install_dir() {
  local host=$1 container=$2 node_config
  node_config=$(ssh_remote "$host" \
    "docker inspect --format '{{range .Mounts}}{{if eq .Destination \"/node.yml\"}}{{.Source}}{{end}}{{end}}' '$container' 2>/dev/null" \
    2>/dev/null || true)
  node_config=$(trim_line "$node_config")
  case "$node_config" in
    */node.yml) printf '%s\n' "${node_config%/node.yml}" ;;
    *) echo "" ;;
  esac
}

check_connectivity() {
  local node=$1 target_host=$2 target_port=$3 result
  if [ -z "$target_port" ]; then
    record "FAIL" "$node" "connectivity" "central -> $target_host: expected port is unavailable"
    return
  fi
  result=$(ssh_remote "$CENTRAL_HOST" \
    "timeout 5 bash -c '</dev/tcp/$target_host/$target_port' >/dev/null 2>&1 && echo reachable || true" \
    2>/dev/null || true)
  if [ "$(trim_line "$result")" = "reachable" ]; then
    record "OK" "$node" "connectivity" "central -> $target_host:$target_port"
  else
    record "FAIL" "$node" "connectivity" "central cannot reach $target_host:$target_port"
  fi
}

CENTRAL_ENV=$(mktemp)
WORKER_ENV=$(mktemp)
trap 'rm -f "$CENTRAL_ENV" "$WORKER_ENV"' EXIT

# =============================================================================
# CENTRAL NODE CHECKS
# =============================================================================

if should_check "$CENTRAL_NODE"; then
  NODE="$CENTRAL_NODE"
  HOST="$CENTRAL_HOST"
  CDIR=$(resolve_install_dir "$HOST" "brane-api")

  header "Checking central node: $NODE ($HOST)"

  if [ -z "$CDIR" ]; then
    record "FAIL" "$NODE" "path" "cannot derive active installation root from brane-api /node.yml mount"
  else
    fetch_public_env "$HOST" "$CDIR" \
      '^(DRV_NAME|DRV_PORT|PRX_NAME|API_NAME|API_PORT|PLR_NAME|BRANE_VERSION|NODE_CONFIG_PATH|INFRA|PROXY|CERTS|PACKAGES)$' \
      "$CENTRAL_ENV"

    C_PRX=$(env_value "$CENTRAL_ENV" "PRX_NAME")
    C_API=$(env_value "$CENTRAL_ENV" "API_NAME")
    C_DRV=$(env_value "$CENTRAL_ENV" "DRV_NAME")
    C_PLR=$(env_value "$CENTRAL_ENV" "PLR_NAME")
    C_TAG=$(env_value "$CENTRAL_ENV" "BRANE_VERSION")
    C_API_PORT=$(env_value "$CENTRAL_ENV" "API_PORT")
    C_DRV_PORT=$(env_value "$CENTRAL_ENV" "DRV_PORT")
    C_NODE_CONFIG=$(env_value "$CENTRAL_ENV" "NODE_CONFIG_PATH")
    C_INFRA=$(env_value "$CENTRAL_ENV" "INFRA")
    C_PROXY=$(env_value "$CENTRAL_ENV" "PROXY")
    C_CERTS=$(env_value "$CENTRAL_ENV" "CERTS")
    C_PACKAGES=$(env_value "$CENTRAL_ENV" "PACKAGES")

    [ -n "$C_PRX" ] || C_PRX="brane-prx"
    [ -n "$C_API" ] || C_API="brane-api"
    [ -n "$C_DRV" ] || C_DRV="brane-drv"
    [ -n "$C_PLR" ] || C_PLR="brane-plr"

    log "Central dir       : $CDIR"
    log "Brane version     : ${C_TAG:-unavailable}"

    check_path "$NODE" "$HOST" "$CDIR"
    check_path "$NODE" "$HOST" "$CDIR/docker-compose.yml"
    check_path "$NODE" "$HOST" "$CDIR/.env"
    check_path "$NODE" "$HOST" "$C_NODE_CONFIG"
    check_path "$NODE" "$HOST" "$C_INFRA"
    check_path "$NODE" "$HOST" "$C_PROXY"
    check_path "$NODE" "$HOST" "$C_CERTS"
    check_path "$NODE" "$HOST" "$C_PACKAGES"

    check_compose_service "$NODE" "$HOST" "aux-scylla"
    check_compose_service "$NODE" "$HOST" "aux-kafka"
    check_compose_service "$NODE" "$HOST" "aux-zookeeper"
    check_container "$NODE" "$HOST" "$C_PRX"
    check_container "$NODE" "$HOST" "$C_API"
    check_container "$NODE" "$HOST" "$C_DRV"
    check_container "$NODE" "$HOST" "$C_PLR"

    check_image "$NODE" "$HOST" "$C_PRX" "brane-prx" "$C_TAG"
    check_image "$NODE" "$HOST" "$C_API" "brane-api" "$C_TAG"
    check_image "$NODE" "$HOST" "$C_DRV" "brane-drv" "$C_TAG"
    check_image "$NODE" "$HOST" "$C_PLR" "brane-plr" "$C_TAG"

    check_port "$NODE" "$HOST" "$C_API_PORT"
    check_port "$NODE" "$HOST" "$C_DRV_PORT"

    load_mounts "$HOST" "$C_PRX"
    check_mount "$NODE" "$C_PRX" "$C_NODE_CONFIG" "/node.yml"
    check_mount "$NODE" "$C_PRX" "$C_PROXY" "$C_PROXY"
    check_mount "$NODE" "$C_PRX" "$C_CERTS" "$C_CERTS"

    load_mounts "$HOST" "$C_API"
    check_mount "$NODE" "$C_API" "$C_NODE_CONFIG" "/node.yml"
    check_mount "$NODE" "$C_API" "$C_INFRA" "$C_INFRA"
    check_mount "$NODE" "$C_API" "$C_CERTS" "$C_CERTS"
    check_mount "$NODE" "$C_API" "$C_PACKAGES" "$C_PACKAGES"

    load_mounts "$HOST" "$C_DRV"
    check_mount "$NODE" "$C_DRV" "$C_NODE_CONFIG" "/node.yml"
    check_mount "$NODE" "$C_DRV" "$C_CERTS" "$C_CERTS"
    check_mount "$NODE" "$C_DRV" "$C_INFRA" "$C_INFRA"

    load_mounts "$HOST" "$C_PLR"
    check_mount "$NODE" "$C_PLR" "$C_NODE_CONFIG" "/node.yml"
    check_mount "$NODE" "$C_PLR" "$C_INFRA" "$C_INFRA"
  fi
fi

# =============================================================================
# WORKER NODE CHECKS
# =============================================================================

i=0
while [ "$i" -lt "${#WORKER_IPS[@]}" ]; do
  HOST="${WORKER_IPS[$i]}"
  NODE="${WORKER_HOSTNAMES[$i]}"
  LOCATION_ID="${WORKER_LOCATION_IDS[$i]}"

  if should_check "$NODE"; then
    WDIR=$(resolve_install_dir "$HOST" "brane-reg")
    header "Checking worker node: $NODE ($HOST) [location_id: $LOCATION_ID]"

    if [ -z "$WDIR" ]; then
      record "FAIL" "$NODE" "path" "cannot derive active installation root from brane-reg /node.yml mount"
    else
      : > "$WORKER_ENV"
      fetch_public_env "$HOST" "$WDIR" \
        '^(BRANE_VERSION|NODE_CONFIG_PATH|BACKEND|PROXY|POLICIES|CERTS|SECRETS|PACKAGES|DATA|RESULTS|TEMP_DATA|TEMP_RESULTS|PRX_NAME|REG_NAME|JOB_NAME|CHK_NAME|REG_PORT|JOB_PORT)$' \
        "$WORKER_ENV"

      W_TAG=$(env_value "$WORKER_ENV" "BRANE_VERSION")
      W_NODE_CONFIG=$(env_value "$WORKER_ENV" "NODE_CONFIG_PATH")
      W_BACKEND=$(env_value "$WORKER_ENV" "BACKEND")
      W_PROXY=$(env_value "$WORKER_ENV" "PROXY")
      W_POLICIES=$(env_value "$WORKER_ENV" "POLICIES")
      W_CERTS=$(env_value "$WORKER_ENV" "CERTS")
      W_SECRETS=$(env_value "$WORKER_ENV" "SECRETS")
      W_PACKAGES=$(env_value "$WORKER_ENV" "PACKAGES")
      W_DATA=$(env_value "$WORKER_ENV" "DATA")
      W_RESULTS=$(env_value "$WORKER_ENV" "RESULTS")
      W_TEMP_DATA=$(env_value "$WORKER_ENV" "TEMP_DATA")
      W_TEMP_RESULTS=$(env_value "$WORKER_ENV" "TEMP_RESULTS")
      W_PRX=$(env_value "$WORKER_ENV" "PRX_NAME")
      W_REG=$(env_value "$WORKER_ENV" "REG_NAME")
      W_JOB=$(env_value "$WORKER_ENV" "JOB_NAME")
      W_CHK=$(env_value "$WORKER_ENV" "CHK_NAME")
      W_REG_PORT=$(env_value "$WORKER_ENV" "REG_PORT")
      W_JOB_PORT=$(env_value "$WORKER_ENV" "JOB_PORT")

      [ -n "$W_PRX" ] || W_PRX="brane-prx"
      [ -n "$W_REG" ] || W_REG="brane-reg"
      [ -n "$W_JOB" ] || W_JOB="brane-job-$LOCATION_ID"
      [ -n "$W_CHK" ] || W_CHK="brane-chk-$LOCATION_ID"

      log "Worker dir        : $WDIR"
      log "Brane version     : ${W_TAG:-unavailable}"

      check_path "$NODE" "$HOST" "$WDIR"
      check_path "$NODE" "$HOST" "$WDIR/docker-compose.yml"
      check_path "$NODE" "$HOST" "$WDIR/.env"
      check_path "$NODE" "$HOST" "$W_NODE_CONFIG"
      check_path "$NODE" "$HOST" "$W_BACKEND"
      check_path "$NODE" "$HOST" "$W_PROXY"
      check_path "$NODE" "$HOST" "$W_POLICIES"
      check_path "$NODE" "$HOST" "$W_CERTS"
      check_path "$NODE" "$HOST" "$W_SECRETS"
      check_path "$NODE" "$HOST" "$W_PACKAGES"
      check_path "$NODE" "$HOST" "$W_DATA"
      check_path "$NODE" "$HOST" "$W_RESULTS"
      check_path "$NODE" "$HOST" "$W_TEMP_DATA"
      check_path "$NODE" "$HOST" "$W_TEMP_RESULTS"

      check_container "$NODE" "$HOST" "$W_PRX"
      check_container "$NODE" "$HOST" "$W_REG"
      check_container "$NODE" "$HOST" "$W_CHK"
      check_container "$NODE" "$HOST" "$W_JOB"

      check_image "$NODE" "$HOST" "$W_PRX" "brane-prx" "$W_TAG"
      check_image "$NODE" "$HOST" "$W_REG" "brane-reg" "$W_TAG"
      check_image "$NODE" "$HOST" "$W_CHK" "brane-chk" "$W_TAG"
      check_image "$NODE" "$HOST" "$W_JOB" "brane-job" "$W_TAG"

      check_port "$NODE" "$HOST" "$W_REG_PORT"
      check_port "$NODE" "$HOST" "$W_JOB_PORT"

      load_mounts "$HOST" "$W_PRX"
      check_mount "$NODE" "$W_PRX" "$W_NODE_CONFIG" "/node.yml"
      check_mount "$NODE" "$W_PRX" "$W_PROXY" "$W_PROXY"
      check_mount "$NODE" "$W_PRX" "$W_CERTS" "$W_CERTS"

      load_mounts "$HOST" "$W_REG"
      check_mount "$NODE" "$W_REG" "$W_NODE_CONFIG" "/node.yml"
      check_mount "$NODE" "$W_REG" "$W_BACKEND" "$W_BACKEND"
      check_mount "$NODE" "$W_REG" "$W_POLICIES" "$W_POLICIES"
      check_mount "$NODE" "$W_REG" "$W_CERTS" "$W_CERTS"
      check_mount "$NODE" "$W_REG" "$W_SECRETS" "$W_SECRETS"
      check_mount "$NODE" "$W_REG" "$W_DATA" "$W_DATA"
      check_mount "$NODE" "$W_REG" "$W_RESULTS" "$W_RESULTS"

      load_mounts "$HOST" "$W_CHK"
      check_mount "$NODE" "$W_CHK" "$W_NODE_CONFIG" "/node.yml"
      check_mount "$NODE" "$W_CHK" "$W_POLICIES" "/home/brane/policy/policies.db"
      check_mount "$NODE" "$W_CHK" "$W_CERTS" "$W_CERTS"
      check_mount "$NODE" "$W_CHK" "$W_SECRETS" "$W_SECRETS"

      load_mounts "$HOST" "$W_JOB"
      check_mount "$NODE" "$W_JOB" "$W_NODE_CONFIG" "/node.yml"
      check_mount "$NODE" "$W_JOB" "$W_BACKEND" "$W_BACKEND"
      check_mount "$NODE" "$W_JOB" "$W_POLICIES" "$W_POLICIES"
      check_mount "$NODE" "$W_JOB" "$W_CERTS" "$W_CERTS"
      check_mount "$NODE" "$W_JOB" "$W_PACKAGES" "$W_PACKAGES"
      check_mount "$NODE" "$W_JOB" "$W_DATA" "$W_DATA"
      check_mount "$NODE" "$W_JOB" "$W_RESULTS" "$W_RESULTS"
      check_mount "$NODE" "$W_JOB" "$W_TEMP_DATA" "$W_TEMP_DATA"
      check_mount "$NODE" "$W_JOB" "$W_TEMP_RESULTS" "$W_TEMP_RESULTS"
      check_mount "$NODE" "$W_JOB" "/var/run/docker.sock" "/var/run/docker.sock"

      # The published job port belongs to brane-chk because brane-job shares
      # brane-chk's network namespace.
      check_connectivity "$NODE" "$HOST" "$W_REG_PORT"
      check_connectivity "$NODE" "$HOST" "$W_JOB_PORT"
    fi
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

ALL_NODES=("$CENTRAL_NODE")
for h in "${WORKER_HOSTNAMES[@]}"; do
  ALL_NODES+=("$h")
done

for NODE in "${ALL_NODES[@]}"; do
  should_check "$NODE" || continue
  for CAT in path container image port mount connectivity; do
    CAT_PASS=0
    CAT_FAIL=0
    CAT_TOTAL=0
    for line in "${RESULT_LINES[@]}"; do
      echo "$line" | grep -Fq "[$NODE]" || continue
      echo "$line" | grep -Fq "[$CAT]" || continue
      CAT_TOTAL=$((CAT_TOTAL + 1))
      if echo "$line" | grep -q '\[OK\]'; then
        CAT_PASS=$((CAT_PASS + 1))
      else
        CAT_FAIL=$((CAT_FAIL + 1))
      fi
    done
    [ "$CAT_TOTAL" -gt 0 ] || continue
    if [ "$CAT_FAIL" -gt 0 ]; then
      SUMMARY_LINES+=("${RED}[FAIL]${NC} $NODE | $CAT: $CAT_PASS ok, $CAT_FAIL failed")
    else
      SUMMARY_LINES+=("${GREEN}[OK]${NC}   $NODE | $CAT: $CAT_PASS ok")
    fi
  done
done

for line in "${SUMMARY_LINES[@]}"; do
  echo -e "  $line"
done

echo ""
echo -e "  ${BOLD}Total: ${GREEN}${TOTAL_PASS} passed${NC}  ${BOLD}${RED}${TOTAL_FAIL} failed${NC}"
printf "${BLUE}"; printf '%.0s─' {1..70}; printf "${NC}\n"

if [ "$TOTAL_FAIL" -gt 0 ]; then
  echo -e "${RED}${BOLD}  Deployment is UNHEALTHY. Run with --report for full details.${NC}"
  exit 1
fi

echo -e "${GREEN}${BOLD}  Deployment is HEALTHY.${NC}"
exit 0

