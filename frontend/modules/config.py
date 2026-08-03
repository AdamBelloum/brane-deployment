"""
config.py – Central path and runtime configuration for the Brane frontend.

All modules import from here instead of computing paths independently.
No values are hard-coded; everything is derived from the repo layout or
overridable via environment variables.

Usage in any module:
    from config import ANSIBLE_DIR, INVENTORY_PATH, PLAYBOOK, get_brane_executable
"""

import os
import shutil
from pathlib import Path

# ── Repo layout ────────────────────────────────────────────────────────────────

# frontend/modules/config.py  →  go up two levels to reach repo root
_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIR = os.path.dirname(_MODULES_DIR)
REPO_ROOT = os.path.dirname(_FRONTEND_DIR)

# ── Ansible / docker-deployment paths ──────────────────────────────────────────

ANSIBLE_DIR = os.environ.get(
    "BRANE_ANSIBLE_DIR",
    os.path.join(REPO_ROOT, "docker-deployment"),
)

INVENTORY_PATH = os.environ.get(
    "BRANE_INVENTORY",
    os.path.join(ANSIBLE_DIR, "inventories", "production", "hosts.ini"),
)

INVENTORY_TEMPLATE_PATH = os.path.join(
    ANSIBLE_DIR, "inventories", "production", "hosts.ini.template"
)

PLAYBOOK = os.environ.get(
    "BRANE_PLAYBOOK",
    os.path.join(ANSIBLE_DIR, "site.yml"),
)

# ── Brane CLI binary resolution ────────────────────────────────────────────────

def get_brane_executable() -> str:
    """
    Locate the 'brane' CLI binary on the host machine.

    Search order:
      1. BRANE_CLI environment variable (explicit override)
      2. ~/.local/bin/brane  (default per-user install location)
      3. /usr/local/bin/brane
      4. PATH (via shutil.which)
      5. Fall back to bare "brane" string (lets the OS raise a clear error)
    """
    # 1. Explicit override
    env_override = os.environ.get("BRANE_CLI")
    if env_override:
        return env_override

    # 2. Per-user install
    user_bin = Path.home() / ".local" / "bin" / "brane"
    if user_bin.exists() and os.access(user_bin, os.X_OK):
        return str(user_bin)

    # 3. System-wide install
    system_bin = Path("/usr/local/bin/brane")
    if system_bin.exists() and os.access(system_bin, os.X_OK):
        return str(system_bin)

    # 4. PATH lookup
    path_bin = shutil.which("brane")
    if path_bin:
        return path_bin

    # 5. Bare fallback — subprocess will raise FileNotFoundError with a clear message
    return "brane"

