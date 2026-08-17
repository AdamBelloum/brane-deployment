# =============================================================
# config.py
# Version: 1.2.2
# Date: 2026-08-17
# Author: Brane Deployment Team
#
# Description:
#   Central path and runtime configuration for the Brane frontend.
#   All modules import from here instead of computing paths independently.
#   No values are hard-coded; everything is derived from repo layout or
#   overridable via environment variables.
#
# =============================================================

import configparser
import os
import shutil
from pathlib import Path
from typing import Optional, List

# =============================================================
# REPO LAYOUT DETECTION
# =============================================================

# frontend/modules/config.py → go up two levels to reach repo root
_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIR = os.path.dirname(_MODULES_DIR)
REPO_ROOT = os.path.dirname(_FRONTEND_DIR)

# =============================================================
# ANSIBLE / DOCKER-DEPLOYMENT PATHS
# =============================================================

ANSIBLE_DIR = os.environ.get(
    "BRANE_ANSIBLE_DIR",
    os.path.join(REPO_ROOT, "docker-deployment"),
)

INVENTORY_PATH = os.environ.get(
    "BRANE_INVENTORY",
    os.path.join(ANSIBLE_DIR, "inventories", "production", "hosts.ini"),
)

# Export as ANSIBLE_INVENTORY for compatibility
ANSIBLE_INVENTORY = INVENTORY_PATH

INVENTORY_TEMPLATE_PATH = os.path.join(
    ANSIBLE_DIR, "inventories", "production", "hosts.ini.template"
)

PLAYBOOK = os.environ.get(
    "BRANE_PLAYBOOK",
    os.path.join(ANSIBLE_DIR, "site.yml"),
)

# =============================================================
# RESOURCE DIRECTORIES
# =============================================================

PACKAGES_DIR = os.path.join(REPO_ROOT, "packages")
CERTS_DIR = os.path.join(REPO_ROOT, "certs")
DATASETS_DIR = os.path.join(REPO_ROOT, "datasets")
POLICIES_DIR = os.path.join(REPO_ROOT, "policies")
POLICY_TOKENS_DIR = os.path.join(REPO_ROOT, "policy_tokens")


# =============================================================
# RESOURCE DISCOVERY FUNCTIONS
# =============================================================

def list_packages() -> List[str]:
    """
    List all available packages in the packages/ directory.
    
    Returns:
        List of package directory names (subdirectories only)
    """
    if not os.path.isdir(PACKAGES_DIR):
        return []
    
    try:
        packages = [
            d for d in os.listdir(PACKAGES_DIR)
            if os.path.isdir(os.path.join(PACKAGES_DIR, d)) and not d.startswith('.')
        ]
        return sorted(packages)
    except Exception:
        return []


def list_certs() -> List[str]:
    """
    List all available certificate domains in the certs/ directory.
    
    Returns:
        List of certificate domain directory names (subdirectories only)
    """
    if not os.path.isdir(CERTS_DIR):
        return []
    
    try:
        certs = [
            d for d in os.listdir(CERTS_DIR)
            if os.path.isdir(os.path.join(CERTS_DIR, d)) and not d.startswith('.')
        ]
        return sorted(certs)
    except Exception:
        return []


def list_datasets() -> List[str]:
    """
    List all available datasets in the datasets/ directory.
    
    Returns:
        List of dataset directory names (subdirectories only)
    """
    if not os.path.isdir(DATASETS_DIR):
        return []
    
    try:
        datasets = [
            d for d in os.listdir(DATASETS_DIR)
            if os.path.isdir(os.path.join(DATASETS_DIR, d)) and not d.startswith('.')
        ]
        return sorted(datasets)
    except Exception:
        return []


def list_policies() -> List[str]:
    """
    List all available eFLINT policy files in the policies/ directory.
    
    Returns:
        List of .eflint file names
    """
    if not os.path.isdir(POLICIES_DIR):
        return []
    
    try:
        policies = [
            f for f in os.listdir(POLICIES_DIR)
            if f.endswith('.eflint') and os.path.isfile(os.path.join(POLICIES_DIR, f))
        ]
        return sorted(policies)
    except Exception:
        return []


def list_policy_tokens() -> List[str]:
    """
    List all available policy token files in the policy_tokens/ directory.
    
    Supports both .json and .jason extensions (for compatibility).
    
    Returns:
        List of token file names (.json or .jason)
    """
    if not os.path.isdir(POLICY_TOKENS_DIR):
        return []
    
    try:
        tokens = [
            f for f in os.listdir(POLICY_TOKENS_DIR)
            if (f.endswith('.json') or f.endswith('.jason')) 
            and os.path.isfile(os.path.join(POLICY_TOKENS_DIR, f))
        ]
        return sorted(tokens)
    except Exception:
        return []


# =============================================================
# INVENTORY HELPER FUNCTIONS
# =============================================================

def get_central_ip() -> Optional[str]:
    """
    Extract central hub IP from inventory file.
    
    Supports both section naming conventions:
    - [central_hub] (new style)
    - [central] (old style)
    
    Returns:
        Central hub IP address or None if not found
    """
    if not os.path.exists(INVENTORY_PATH):
        return None
    
    try:
        config = configparser.ConfigParser(
            allow_no_value=True,
            delimiters=(" ", "="),
            comment_prefixes=("#", ";"),
            inline_comment_prefixes=("#", ";"),
        )
        config.optionxform = str
        config.read(INVENTORY_PATH)
        
        # Try both section naming conventions
        for section_name in ["central_hub", "central"]:
            if config.has_section(section_name):
                for host, vars_str in config.items(section_name):
                    if vars_str and "ansible_host=" in vars_str:
                        ip = vars_str.split("ansible_host=")[1].split()[0]
                        return ip
        
        return None
    except Exception:
        return None


def get_worker_ips() -> List[str]:
    """
    Extract all worker node IPs from inventory file.
    
    Supports both section naming conventions:
    - [worker_nodes] (new style)
    - [workers] (old style)
    
    Returns:
        List of worker node IP addresses
    """
    if not os.path.exists(INVENTORY_PATH):
        return []
    
    try:
        config = configparser.ConfigParser(
            allow_no_value=True,
            delimiters=(" ", "="),
            comment_prefixes=("#", ";"),
            inline_comment_prefixes=("#", ";"),
        )
        config.optionxform = str
        config.read(INVENTORY_PATH)
        
        workers = []
        
        # Try both section naming conventions
        for section_name in ["worker_nodes", "workers"]:
            if config.has_section(section_name):
                for host, vars_str in config.items(section_name):
                    if vars_str and "ansible_host=" in vars_str:
                        ip = vars_str.split("ansible_host=")[1].split()[0]
                        workers.append(ip)
        
        return sorted(workers)
    except Exception:
        return []


# =============================================================
# BRANE CLI HELPER FUNCTIONS
# =============================================================

def get_brane_executable() -> str:
    """
    Get path to Brane CLI executable.
    
    Searches in:
    1. ~/.local/bin/brane (Linux/macOS)
    2. System PATH
    3. Current directory
    
    Returns:
        Path to brane executable or "brane" (for PATH lookup)
    """
    # Check user local bin
    local_bin = os.path.expanduser("~/.local/bin/brane")
    if os.path.exists(local_bin):
        return local_bin
    
    # Check system PATH
    import shutil as sh
    brane_path = sh.which("brane")
    if brane_path:
        return brane_path
    
    # Fallback to "brane" (will search PATH)
    return "brane"


# =============================================================
# END OF FILE
# =============================================================
