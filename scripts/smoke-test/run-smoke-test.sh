#!/usr/bin/env bash
set -euo pipefail

# Resolve paths relative to this deployed smoke-test directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$SCRIPT_DIR/smoke-test-package"

# The Ansible smoke task supplies these from the checksum-locked release manifest.
BRANE_RELEASE_TAG="${BRANE_RELEASE_TAG:?Missing BRANE_RELEASE_TAG}"
BRANELET_URL="${BRANELET_URL:?Missing BRANELET_URL}"
BRANELET_SHA256="${BRANELET_SHA256:?Missing BRANELET_SHA256}"
BRANELET_PATH="${BRANELET_PATH:-/tmp/branelet-x86_64-${BRANE_RELEASE_TAG}}"

# `INSTANCE_NAME` can override the currently selected local Brane instance.
INSTANCE_NAME="${INSTANCE_NAME:-}"

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

verify_branelet_sha256() {
  local actual
  actual="$(sha256sum "$1" | awk '{print $1}')"
  if [ "$actual" != "$BRANELET_SHA256" ]; then
    echo "Checksum mismatch for $1" >&2
    echo "Expected: $BRANELET_SHA256" >&2
    echo "Actual:   $actual" >&2
    return 1
  fi
}

download_branelet() {
  # Verify cached content too: a previous release or a corrupt binary must not
  # silently be reused merely because it is executable.
  if [ -x "$BRANELET_PATH" ]; then
    if verify_branelet_sha256 "$BRANELET_PATH"; then
      return 0
    fi
    echo "Removing stale or invalid cached branelet: $BRANELET_PATH" >&2
    rm -f "$BRANELET_PATH"
  fi

  local temporary_path="${BRANELET_PATH}.tmp.$$"
  rm -f "$temporary_path"
  curl -fsSL "$BRANELET_URL" -o "$temporary_path"

  if ! verify_branelet_sha256 "$temporary_path"; then
    rm -f "$temporary_path"
    exit 1
  fi

  chmod +x "$temporary_path"
  mv "$temporary_path" "$BRANELET_PATH"
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
need_cmd sha256sum

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
