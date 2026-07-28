#!/usr/bin/env bash
set -euo pipefail



https://github.com/BraneFramework/brane/releases/download/test/branelet-linux-x86_64

# Resolve paths relative to the repo root so the script can be run from anywhere.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR="$ROOT_DIR/scripts/smoke-test/moke-test-package"

# By default we test against the currently selected local Brane instance.
# `INSTANCE_NAME` can override that when we want to target a specific cluster.
INSTANCE_NAME="${INSTANCE_NAME:-}"
BRANE_VERSION="${BRANE_VERSION:-3.0.0}"

# `brane build` needs a local branelet binary that matches the target arch.
BRANELET_PATH="${BRANELET_PATH:-/tmp/branelet-x86_64-v${BRANE_VERSION}}"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

ensure_builder() {
  # Brane package builds need a builder that supports the `type=docker`
  # exporter. OrbStack's default `docker` driver does not, so switch to a
  # dedicated `docker-container` builder when necessary.
  local current_driver
  current_driver="$(docker buildx inspect 2>/dev/null | sed -n 's/^Driver:[[:space:]]*//p' | head -n 1)"

  if [ "$current_driver" = "docker-container" ]; then
    docker buildx inspect --bootstrap >/dev/null
    return 0
  fi

  if docker buildx inspect branebuilder >/dev/null 2>&1; then
    docker buildx use branebuilder >/dev/null
  else
    docker buildx create --name branebuilder --driver docker-container --use >/dev/null
  fi
  docker buildx inspect --bootstrap >/dev/null
}

download_branelet() {
  # Cache the helper binary locally so repeated smoke tests do not need to
  # download it again.
  if [ -x "$BRANELET_PATH" ]; then
    return 0
  fi
  #TODO: this is the version used in the orginal test, I have modified to becayse I use the Test version branectl brane cli
  #curl -fsSL "https://github.com/BraneFramework/brane/releases/download/v${BRANE_VERSION}/branelet-x86_64" -o "$BRANELET_PATH"
  curl -fsSL "https://github.com/BraneFramework/brane/releases/download/test/branelet-linux-x86_64" -o "$BRANELET_PATH"
  chmod +x "$BRANELET_PATH"
}

run_workflow() {
  local workflow="$1"
  printf 'Running %s\n' "$(basename "$workflow")"
  brane run -r "$workflow"
}

need_cmd brane
need_cmd curl
need_cmd docker
need_cmd sed

# Prepare the local build toolchain used for the test package.
ensure_builder
download_branelet

if [ -n "$INSTANCE_NAME" ]; then
  brane instance select "$INSTANCE_NAME" >/dev/null
fi

# Build and publish the tiny smoke-test package, then run one workflow on each
# worker so we verify that scheduling and remote execution both work.
brane build -a x86_64 -i "$BRANELET_PATH" "$PACKAGE_DIR/container.yml"
brane push brane_smoke_test >/dev/null

run_workflow "$PACKAGE_DIR/worker-a.bs"
run_workflow "$PACKAGE_DIR/worker-b.bs"
