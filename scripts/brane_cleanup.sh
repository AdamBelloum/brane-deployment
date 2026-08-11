#!/usr/bin/env bash
# =============================================================================
# brane_cleanup.sh — DESTRUCTIVE CLEANUP SCRIPT
# =============================================================================
#
# PURPOSE:
#   Performs a full teardown of a Brane deployment across all nodes defined
#   in the Ansible inventory. Run this script when you want to start a
#   completely fresh deployment from scratch.
#
# WHAT THIS SCRIPT DESTROYS (on EVERY node in the inventory):
#
#   On the CENTRAL node (group: central):
#     - All running and stopped Brane Docker containers
#     - All Brane Docker images
#     - All Brane Docker volumes
#     - All Brane buildx builder instances
#     - The ~/brane-central deployment directory and ALL its contents
#       (configuration files, certificates, infra.yml, node.yml, etc.)
#     - Brane release tarballs in /tmp
#
#   On each WORKER node (group: workers):
#     - All running and stopped Brane Docker containers
#     - All Brane Docker images
#     - All Brane Docker volumes
#     - The ~/brane-worker deployment directory and ALL its contents
#     - Brane release tarballs in /tmp
#
# WHAT THIS SCRIPT DOES NOT TOUCH:
#   - SSH keys and authorized_keys on any node
#     (pre-shared keys must remain intact for the next deployment)
#   - Non-Brane Docker containers, images, or volumes
#   - System packages or Docker installation itself
#   - Any files outside ~/brane-central and ~/brane-worker
#
# CONSEQUENCE:
#   After running this script, the Brane deployment is completely gone.
#   A full re-deployment via the Ansible playbooks is required before
#   Brane can be used again. This includes re-running:
#     1. The infrastructure setup playbook
#     2. The central node deployment playbook
#     3. The worker node deployment playbook(s)
#
# PREREQUISITES:
#   - Run from the brane-deployment repository root on the CONTROL machine
#   - Python venv must be activated (source venv/bin/activate)
#   - SSH access to all nodes must be working
#   - Ansible must be available (pip install ansible)
#
# Usage:
#   ./scripts/brane_cleanup.sh
#   ./scripts/brane_cleanup.sh --inventory inventories/production/hosts.ini
#
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${BLUE}[CLEANUP]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── Parse arguments ───────────────────────────────────────────────────────────

INVENTORY="inventories/production/hosts.ini"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --inventory|-i) INVENTORY="$2"; shift 2 ;;
    *) warn "Unknown argument: $1"; shift ;;
  esac
done

if [ ! -f "$INVENTORY" ]; then
  error "Inventory file not found: $INVENTORY"
  error "Usage: $0 [--inventory path/to/hosts.ini]"
  exit 1
fi

if ! command -v ansible &>/dev/null; then
  error "ansible not found. Activate your venv or run: pip install ansible"
  exit 1
fi

# ── Confirmation prompt ───────────────────────────────────────────────────────

echo ""
echo -e "${RED}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${RED}║              ⚠  DESTRUCTIVE OPERATION WARNING  ⚠            ║${NC}"
echo -e "${RED}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${RED}║                                                              ║${NC}"
echo -e "${RED}║  This will PERMANENTLY DELETE on ALL nodes:                 ║${NC}"
echo -e "${RED}║    • All Brane Docker containers (running and stopped)       ║${NC}"
echo -e "${RED}║    • All Brane Docker images and volumes                     ║${NC}"
echo -e "${RED}║    • ~/brane-central  (central node)                        ║${NC}"
echo -e "${RED}║    • ~/brane-worker   (each worker node)                    ║${NC}"
echo -e "${RED}║                                                              ║${NC}"
echo -e "${RED}║  A full re-deployment will be required afterwards.          ║${NC}"
echo -e "${RED}║  SSH keys are NOT affected.                                 ║${NC}"
echo -e "${RED}║                                                              ║${NC}"
echo -e "${RED}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
read -r -p "Type YES to confirm and proceed: " CONFIRM
if [ "$CONFIRM" != "YES" ]; then
  echo "Aborted."
  exit 0
fi
echo ""

log "Using inventory: $INVENTORY"

# ── Resolve the ansible_user from the inventory ───────────────────────────────

ANSIBLE_REMOTE_USER=$(ansible central \
  -i "$INVENTORY" \
  -m debug \
  -a "msg={{ ansible_user }}" \
  --one-line 2>/dev/null \
  | grep -oP '(?<="msg": ")[^"]+' || echo "adam")

log "Remote deploy user: $ANSIBLE_REMOTE_USER"

# ── Write remote scripts to temp files ───────────────────────────────────────

CENTRAL_SCRIPT=$(mktemp /tmp/brane_cleanup_central.XXXXXX.sh)
WORKER_SCRIPT=$(mktemp /tmp/brane_cleanup_worker.XXXXXX.sh)
trap 'rm -f "$CENTRAL_SCRIPT" "$WORKER_SCRIPT"' EXIT

# ── Central node cleanup script ───────────────────────────────────────────────

cat > "$CENTRAL_SCRIPT" << ENDOFSCRIPT
#!/usr/bin/env bash
set -euo pipefail

DEPLOY_USER="${ANSIBLE_REMOTE_USER}"
USER_HOME=\$(getent passwd "\$DEPLOY_USER" | cut -d: -f6)
CENTRAL_DIR="\$USER_HOME/brane-central"

echo "[central] Targeting directory: \$CENTRAL_DIR"

# 1. Stop docker-compose stack
if [ -f "\$CENTRAL_DIR/docker-compose.yml" ]; then
  echo "[central] Stopping docker-compose stack..."
  (cd "\$CENTRAL_DIR" && docker-compose down --remove-orphans 2>/dev/null) || true
fi

# 2. Force-remove any remaining brane containers
CONTAINERS=\$(docker ps -a --format '{{.Names}}' | grep -E '^brane-|^brane_|buildx_buildkit_brane' || true)
if [ -n "\$CONTAINERS" ]; then
  echo "[central] Removing containers..."
  echo "\$CONTAINERS" | xargs docker rm -f
fi

# 3. Remove buildx builder instances
BUILDERS=\$(docker buildx ls --format '{{.Name}}' 2>/dev/null | grep -E 'brane' || true)
if [ -n "\$BUILDERS" ]; then
  echo "[central] Removing buildx builders..."
  echo "\$BUILDERS" | xargs -r docker buildx rm --force 2>/dev/null || true
fi

# 4. Remove brane images
IMAGES=\$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^brane-|^brane_|^aux-' || true)
if [ -n "\$IMAGES" ]; then
  echo "[central] Removing images..."
  echo "\$IMAGES" | xargs docker rmi -f
fi

# 5. Remove brane volumes
VOLUMES=\$(docker volume ls --format '{{.Name}}' | grep -E 'brane' || true)
if [ -n "\$VOLUMES" ]; then
  echo "[central] Removing volumes..."
  for VOL in \$VOLUMES; do
    docker volume rm -f "\$VOL" 2>/dev/null || echo "[central] Could not remove volume: \$VOL (skipping)"
  done
fi

# 6. Remove brane-central install directory
if [ -d "\$CENTRAL_DIR" ]; then
  echo "[central] Removing \$CENTRAL_DIR..."
  rm -rf "\$CENTRAL_DIR"
  echo "[central] Removed \$CENTRAL_DIR"
else
  echo "[central] \$CENTRAL_DIR not found, skipping."
fi

# 7. Remove release tarballs
rm -f /tmp/instance-x86_64.tar.gz /tmp/brane*.tar.gz

echo "[central] Done."
ENDOFSCRIPT

# ── Worker node cleanup script ────────────────────────────────────────────────

cat > "$WORKER_SCRIPT" << ENDOFSCRIPT
#!/usr/bin/env bash
set -euo pipefail

DEPLOY_USER="${ANSIBLE_REMOTE_USER}"
USER_HOME=\$(getent passwd "\$DEPLOY_USER" | cut -d: -f6)
WORKER_DIR="\$USER_HOME/brane-worker"

echo "[worker] Targeting directory: \$WORKER_DIR"

# 1. Stop docker-compose stack
if [ -f "\$WORKER_DIR/docker-compose.yml" ]; then
  echo "[worker] Stopping docker-compose stack..."
  (cd "\$WORKER_DIR" && docker-compose down --remove-orphans 2>/dev/null) || true
fi

# 2. Force-remove any remaining brane containers
CONTAINERS=\$(docker ps -a --format '{{.Names}}' | grep -E '^brane-|^brane_|buildx_buildkit_brane' || true)
if [ -n "\$CONTAINERS" ]; then
  echo "[worker] Removing containers..."
  echo "\$CONTAINERS" | xargs docker rm -f
fi

# 3. Remove brane images
IMAGES=\$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^brane-|^brane_' || true)
if [ -n "\$IMAGES" ]; then
  echo "[worker] Removing images..."
  echo "\$IMAGES" | xargs docker rmi -f
fi

# 4. Remove brane volumes
VOLUMES=\$(docker volume ls --format '{{.Name}}' | grep -E 'brane' || true)
if [ -n "\$VOLUMES" ]; then
  echo "[worker] Removing volumes..."
  for VOL in \$VOLUMES; do
    docker volume rm -f "\$VOL" 2>/dev/null || echo "[worker] Could not remove volume: \$VOL (skipping)"
  done
fi

# 5. Remove brane-worker install directory
if [ -d "\$WORKER_DIR" ]; then
  echo "[worker] Removing \$WORKER_DIR..."
  rm -rf "\$WORKER_DIR"
  echo "[worker] Removed \$WORKER_DIR"
else
  echo "[worker] \$WORKER_DIR not found, skipping."
fi

# 6. Remove release tarballs
rm -f /tmp/worker-instance-x86_64.tar.gz /tmp/brane*.tar.gz

echo "[worker] Done."
ENDOFSCRIPT

chmod +x "$CENTRAL_SCRIPT" "$WORKER_SCRIPT"

# ── Clean central node ────────────────────────────────────────────────────────

log "Cleaning central node (central)..."
ansible central \
  -i "$INVENTORY" \
  -m ansible.builtin.script \
  -a "$CENTRAL_SCRIPT" \
  && ok "Central node clean." \
  || warn "Central node cleanup had warnings — check output above."

# ── Clean all worker nodes ────────────────────────────────────────────────────

log "Cleaning worker nodes (workers)..."
ansible workers \
  -i "$INVENTORY" \
  -m ansible.builtin.script \
  -a "$WORKER_SCRIPT" \
  && ok "All worker nodes clean." \
  || warn "One or more worker nodes had warnings — check output above."

echo ""
ok "All nodes clean. Ready for a fresh deployment."

