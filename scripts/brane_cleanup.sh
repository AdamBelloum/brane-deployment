#!/usr/bin/env bash
# brane_cleanup.sh — wipe all Brane state from a node (central or worker)
# Run directly on each node: bash brane_cleanup.sh
# Or via Ansible: ansible all -i hosts.ini -m script -a brane_cleanup.sh

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[CLEANUP]${NC} $1"; }
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${RED}[WARN]${NC} $1"; }

# ── 1. Stop and remove Brane containers ───────────────────────────────────────

log "Stopping Brane docker-compose stacks..."
for dir in ~/brane-central ~/brane-worker; do
  if [ -f "$dir/docker-compose.yml" ]; then
    log "  docker-compose down in $dir"
    docker-compose -f "$dir/docker-compose.yml" down --remove-orphans 2>/dev/null || true
  fi
done

log "Removing any leftover Brane containers..."
CONTAINERS=$(docker ps -a --format '{{.Names}}' | grep -E '^brane-' || true)
if [ -n "$CONTAINERS" ]; then
  echo "$CONTAINERS" | xargs docker rm -f
  ok "Containers removed."
else
  ok "No Brane containers found."
fi

# ── 2. Remove Brane Docker images ─────────────────────────────────────────────

log "Removing Brane Docker images..."
IMAGES=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^brane-|^aux-' || true)
if [ -n "$IMAGES" ]; then
  echo "$IMAGES" | xargs docker rmi -f
  ok "Images removed."
else
  ok "No Brane images found."
fi

# ── 3. Remove Brane Docker volumes ────────────────────────────────────────────

log "Removing Brane Docker volumes..."
VOLUMES=$(docker volume ls --format '{{.Name}}' | grep -E 'brane' || true)
if [ -n "$VOLUMES" ]; then
  echo "$VOLUMES" | xargs docker volume rm -f
  ok "Volumes removed."
else
  ok "No Brane volumes found."
fi

# ── 4. Remove install directories ─────────────────────────────────────────────

log "Removing Brane install directories..."
for dir in ~/brane-central ~/brane-worker /opt/brane; do
  if [ -d "$dir" ]; then
    rm -rf "$dir"
    ok "Removed $dir"
  fi
done

# ── 5. Remove release tarballs from /tmp ──────────────────────────────────────

log "Removing release tarballs from /tmp..."
rm -f /tmp/instance-x86_64.tar.gz /tmp/worker-instance-x86_64.tar.gz /tmp/brane*.tar.gz
ok "Tarballs removed."

# ── 6. Remove central SSH key (if on central) ─────────────────────────────────

if [ -f ~/.ssh/id_ed25519 ]; then
  log "Removing central SSH keypair..."
  rm -f ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub
  ok "SSH keypair removed."
fi

# ── 7. Remove central's key from authorized_keys (if on worker) ───────────────

if [ -f ~/.ssh/authorized_keys ]; then
  log "Cleaning central key from authorized_keys..."
  sed -i '/ab-01\|brane-central\|145\.100\.135\.209/d' ~/.ssh/authorized_keys
  ok "authorized_keys cleaned."
fi

echo ""
ok "Node is clean. Ready for a fresh deployment."

