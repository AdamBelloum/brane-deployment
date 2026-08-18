"""
config.py – Central path and runtime configuration for the Brane frontend.

All modules import from here instead of computing paths independently.
No values are hard-coded; everything is derived from the repo layout or
overridable via environment variables.

Usage in any module:
    from modules.config import (
        ANSIBLE_DIR, INVENTORY_PATH, PLAYBOOK,
        get_brane_executable, get_central_ip,
    )
"""

import configparser
import os
import shutil
from pathlib import Path
from typing import Optional

# ── Repo layout ───────────────────────────────────────────────────────────────
# frontend/modules/config.py → go up two levels to reach repo root
_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIR = os.path.dirname(_MODULES_DIR)
REPO_ROOT = os.path.dirname(_FRONTEND_DIR)

# Local, Git-ignored Streamlit task state and logs.
FRONTEND_RUNTIME_DIR = Path(_FRONTEND_DIR) / "runtime"

# Repository-root resources, shared by the role workspaces.
PACKAGES_DIR = Path(REPO_ROOT) / "packages"
CERTS_DIR = Path(REPO_ROOT) / "certs"
DATASETS_DIR = Path(REPO_ROOT) / "datasets"
POLICIES_DIR = Path(REPO_ROOT) / "policies"
POLICY_TOKENS_DIR = Path(REPO_ROOT) / "policy_tokens"

# ── Ansible / docker-deployment paths ────────────────────────────────────────
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

# ── Inventory helpers ─────────────────────────────────────────────────────────

def get_central_ip() -> Optional[str]:
    """
    Return the ansible_host IP of the first host in the [central] section
    of hosts.ini. Returns None if the file does not exist or no IP is found.
    """
    if not os.path.exists(INVENTORY_PATH):
        return None

    config = configparser.ConfigParser(
        allow_no_value=True,
        delimiters=(" ", "="),
        comment_prefixes=("#", ";"),
        inline_comment_prefixes=("#", ";"),
    )
    config.optionxform = str
    config.read(INVENTORY_PATH)

    for section in config.sections():
        if "central" in section.lower():
            for _host, vars_str in config.items(section):
                if not vars_str:
                    continue
                for part in vars_str.split():
                    if part.startswith("ansible_host="):
                        return part.split("=", 1)[1]
    return None


# ── Brane CLI binary resolution ───────────────────────────────────────────────

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



# ── Repository resource discovery ────────────────────────────────────────────

def list_packages() -> list[str]:
    """Return package-directory names directly below the repository packages/ directory."""
    if not PACKAGES_DIR.is_dir():
        return []
    return sorted(
        entry.name
        for entry in PACKAGES_DIR.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )


def _list_resource_files(directory: Path) -> list[str]:
    """Return non-hidden files below a repository resource directory."""
    if not directory.is_dir():
        return []

    return sorted(
        str(path.relative_to(directory))
        for path in directory.rglob("*")
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(directory).parts)
    )


def list_certs() -> list[str]:
    """Return certificate-file paths relative to certs/."""
    return _list_resource_files(CERTS_DIR)


def list_datasets() -> list[str]:
    """Return dataset-file paths relative to datasets/."""
    return _list_resource_files(DATASETS_DIR)


def list_policies() -> list[str]:
    """Return non-hidden eFLINT policy-file paths relative to policies/."""
    return [
        relative_path
        for relative_path in _list_resource_files(POLICIES_DIR)
        if relative_path.endswith(".eflint")
    ]


def list_policy_tokens() -> list[str]:
    """Return non-hidden policy-token file paths relative to policy_tokens/."""
    return _list_resource_files(POLICY_TOKENS_DIR)
