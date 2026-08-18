# =============================================================
# policy_manager_dashboard.py
# Version: 1.0.0
# Date: 2026-08-17
# Author: Brane Deployment Team
#
# Description:
#   Streamlit module for the Policy Manager role dashboard.
#   Provides policy management and activation capabilities for
#   domain policy managers.
#
#   Mirrors the functionality of brane_helper_policy.sh:
#   - Check environment and token validity
#   - Add eFLINT policies to worker domains
#   - Activate policy versions
#   - Verify active policies
#
# Key Responsibilities:
#   1. Display policy manager environment status
#   2. Manage policy tokens and verify expiry
#   3. Upload and add eFLINT policies to domains
#   4. Activate policy versions on worker nodes
#   5. Verify active policies
#   6. Monitor SSH connectivity to worker nodes
#   7. Display policy lifecycle status
#
# Design Pattern:
#   Streamlit View Module - Implements render_policy_manager_dashboard() 
#   function that displays the policy management interface.
#
# Key Features:
#   - Environment status overview
#   - Token management and expiry checking
#   - Policy file selection and upload
#   - Worker node connection management
#   - Policy activation interface
#   - Active policy verification
#   - SSH connectivity monitoring
#   - Real-time operation feedback
#
# Dependencies:
#   - streamlit: Web UI framework
#   - modules.config: Repository configuration
#   - Standard library: subprocess, os, json, base64
#
# =============================================================

import os
import sys
from pathlib import Path

import streamlit as st
import json
import base64
import time
from typing import Optional, List, Dict

from modules.config import (
    POLICIES_DIR,
    POLICY_TOKENS_DIR,
    INVENTORY_PATH,
    REPO_ROOT,
    list_policies,
    list_policy_tokens,
)


from modules.task_manager import start_task
from modules.task_ui import render_task_monitor


# =============================================================
# HELPER FUNCTIONS
# =============================================================

def _parse_inventory() -> Dict[str, List[str]]:
    """
    Parse Ansible inventory file for worker nodes.
    
    Returns:
        Dict with 'workers' and 'central' keys containing IPs/hostnames
    """
    result = {"workers": [], "central": ""}
    
    if not os.path.exists(INVENTORY_PATH):
        return result
    
    try:
        in_workers = False
        in_central = False
        
        with open(INVENTORY_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                
                # Skip blank lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Detect group headers
                if line.startswith('[worker'):
                    in_workers = True
                    in_central = False
                    continue
                elif line.startswith('[central'):
                    in_central = True
                    in_workers = False
                    continue
                elif line.startswith('['):
                    in_workers = False
                    in_central = False
                    continue
                
                # Extract ansible_host value
                host = ""
                if "ansible_host=" in line:
                    host = line.split("ansible_host=")[1].split()[0]
                else:
                    host = line.split()[0]
                
                if host:
                    if in_workers:
                        result["workers"].append(host)
                    elif in_central:
                        result["central"] = host
    
    except Exception:
        pass
    
    return result


def _check_token_expiry(token_path: str) -> Dict[str, any]:
    """
    Check JWT token expiry.
    
    Returns:
        Dict with 'valid', 'remaining_days', 'remaining_hours', 'error' keys
    """
    result = {"valid": False, "remaining_days": 0, "remaining_hours": 0, "error": None}
    
    try:
        # Read token from JSON file
        with open(token_path, 'r') as f:
            data = json.load(f)
            token = data.get('token') or data.get('access_token') or list(data.values())[0]
        
        # Parse JWT
        parts = token.split('.')
        if len(parts) != 3:
            result["error"] = "Invalid JWT format"
            return result
        
        # Decode payload
        payload = parts[1]
        # Add padding if needed
        payload += '=' * (4 - len(payload) % 4)
        
        try:
            decoded = json.loads(base64.urlsafe_b64decode(payload))
        except Exception as e:
            result["error"] = f"Failed to decode JWT: {e}"
            return result
        
        exp = decoded.get('exp', 0)
        remaining = exp - time.time()
        
        if remaining <= 0:
            result["error"] = "Token EXPIRED"
            result["valid"] = False
        else:
            result["valid"] = True
            result["remaining_days"] = int(remaining // 86400)
            result["remaining_hours"] = int((remaining % 86400) // 3600)
        
        return result
    
    except Exception as e:
        result["error"] = str(e)
        return result


def _get_worker_hosts() -> List[str]:
    """Get list of worker hosts from inventory."""
    inventory = _parse_inventory()
    return inventory.get("workers", [])


def _get_policy_files() -> List[str]:
    """Get list of .eflint policy files."""
    policies = []
    try:
        for root, dirs, files in os.walk(POLICIES_DIR):
            for file in files:
                if file.endswith('.eflint'):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, POLICIES_DIR)
                    policies.append(rel_path)
    except Exception:
        pass
    return sorted(policies)


# =============================================================
# UI SECTIONS
# =============================================================

def _render_environment_status() -> None:
    """Render environment status overview."""
    st.subheader("📊 Environment Status")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        tokens = list_policy_tokens()
        st.metric("🔑 Tokens", len(tokens))
        if tokens:
            with st.expander("View tokens"):
                for token in tokens:
                    st.caption(f"• {token}")
    
    with col2:
        policies = list_policies()
        st.metric("📋 Policies", len(policies))
        if policies:
            with st.expander("View policies"):
                for policy in policies:
                    st.caption(f"• {policy}")
    
    with col3:
        inventory = _parse_inventory()
        workers = inventory.get("workers", [])
        st.metric("🖥️ Workers", len(workers))
        if workers:
            with st.expander("View workers"):
                for worker in workers:
                    st.caption(f"• {worker}")
    
    with col4:
        if os.path.exists(INVENTORY_PATH):
            st.metric("📂 Inventory", "✓ Found")
        else:
            st.metric("📂 Inventory", "✗ Missing")


def _render_token_management() -> None:
    """Render token management section."""
    st.subheader("🔑 Token Management")
    
    tokens = list_policy_tokens()
    
    if not tokens:
        st.warning("No policy tokens found in policy_tokens/")
        st.info("Place your policy_token.json file in the policy_tokens/ directory")
        return
    
    st.markdown("#### Token Validity Check")
    
    # Check all tokens
    for token_file in tokens:
        token_path = os.path.join(POLICY_TOKENS_DIR, token_file)
        
        col1, col2 = st.columns([2, 3])
        
        with col1:
            st.markdown(f"**{token_file}**")
        
        with col2:
            result = _check_token_expiry(token_path)
            
            if result["error"]:
                if "EXPIRED" in result["error"]:
                    st.error(f"❌ {result['error']}")
                else:
                    st.warning(f"⚠️ {result['error']}")
            elif result["valid"]:
                days = result["remaining_days"]
                hours = result["remaining_hours"]
                st.success(f"✅ Valid — expires in {days}d {hours}h")
            else:
                st.error("❌ Invalid token")


def _render_policy_upload() -> None:
    """Render policy upload section."""
    st.subheader("📤 Add Policy to Domain")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("#### Select Token")
        tokens = list_policy_tokens()
        if not tokens:
            st.error("No tokens found in policy_tokens/")
            return
        
        selected_token = st.selectbox("Policy token", tokens, key="token_select")
        token_path = os.path.join(POLICY_TOKENS_DIR, selected_token)
        
        # Check token validity
        token_status = _check_token_expiry(token_path)
        if token_status["error"]:
            st.error(f"Token error: {token_status['error']}")
            return
        
        if not token_status["valid"]:
            st.error("Token is not valid")
            return
        
        st.success(f"✅ Token valid for {token_status['remaining_days']}d {token_status['remaining_hours']}h")
    
    with col2:
        st.markdown("#### Select Policy")
        policies = _get_policy_files()
        if not policies:
            st.error("No .eflint policy files found in policies/")
            return
        
        selected_policy = st.selectbox("Policy file", policies, key="policy_select")
        policy_path = os.path.join(POLICIES_DIR, selected_policy)
        
        if os.path.exists(policy_path):
            st.success(f"✅ Policy file found")
        else:
            st.error(f"Policy file not found: {policy_path}")
            return
    
    st.divider()
    
    st.markdown("#### Worker Node Connection")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        workers = _get_worker_hosts()
        if workers:
            worker_host = st.selectbox("Worker host", workers, key="worker_select")
        else:
            worker_host = st.text_input("Worker IP/hostname", key="worker_input")
    
    with col2:
        ssh_user = st.text_input("SSH user", value="ubuntu", key="ssh_user_input")
    
    with col3:
        brane_port = st.text_input("brane-chk port", value="50051", key="port_input")
    
    # Test connection
    if st.button("🔗 Test Connection", key="btn_test_conn"):
        if not worker_host or not ssh_user:
            st.error("Worker host and SSH user are required.")
        else:
            task, error = start_task(
                role="policy-manager",
                operation="policy_ssh_connectivity_check",
                label=f"Check SSH connectivity: {ssh_user}@{worker_host}",
                command=[
                    "ssh",
                    "-o", "BatchMode=yes",
                    "-o", "ConnectTimeout=5",
                    "-o", "StrictHostKeyChecking=accept-new",
                    "-q",
                    f"{ssh_user}@{worker_host}",
                    "exit",
                ],
                cwd=REPO_ROOT,
                metadata={
                    "worker_host": worker_host,
                    "ssh_user": ssh_user,
                    "read_only": True,
                },
                lock_name="policy-ssh-connectivity-check",
            )
            if error:
                st.error(error)
            else:
                st.session_state.policy_ssh_check_task_id = task["id"]
                st.success("SSH connectivity check started in the background.")
                st.rerun()

    policy_ssh_check_task_id = st.session_state.get("policy_ssh_check_task_id")
    if policy_ssh_check_task_id:
        render_task_monitor(
            policy_ssh_check_task_id,
            title="Worker SSH connectivity check",
        )

    st.divider()
    
    # Upload and add policy
    if st.button("📤 Upload & Add Policy", key="btn_add_policy", type="primary"):
        if not worker_host or not ssh_user or not brane_port:
            st.error("Worker host, SSH user, and brane-chk port are required.")
        else:
            task, error = start_task(
                role="policy-manager",
                operation="policy_upload_add",
                label=f"Upload and add policy: {selected_policy}",
                command=[
                    sys.executable,
                    str(Path(__file__).with_name("policy_upload_task.py")),
                    "--policy-path",
                    policy_path,
                    "--token-path",
                    token_path,
                    "--worker-host",
                    worker_host,
                    "--ssh-user",
                    ssh_user,
                    "--brane-port",
                    brane_port,
                ],
                cwd=REPO_ROOT,
                metadata={
                    "policy_file": selected_policy,
                    "worker_host": worker_host,
                    "ssh_user": ssh_user,
                    "brane_port": brane_port,
                },
                lock_name="policy-upload-add",
            )
            if error:
                st.error(error)
            else:
                st.session_state.policy_upload_task_id = task["id"]
                st.success("Policy upload and add started in the background.")
                st.rerun()

    policy_upload_task_id = st.session_state.get("policy_upload_task_id")
    if policy_upload_task_id:
        render_task_monitor(
            policy_upload_task_id,
            title="Policy upload and add progress",
        )


def _render_policy_activation() -> None:
    """Render task-backed policy version listing and activation."""
    st.subheader("✅ Activate Policy Version")

    token_column, connection_column = st.columns([1, 1])

    with token_column:
        st.markdown("#### Select Token")
        tokens = list_policy_tokens()
        if not tokens:
            st.error("No tokens found in policy_tokens/.")
            return

        selected_token = st.selectbox(
            "Policy token",
            tokens,
            key="token_select_activate",
        )
        token_path = os.path.join(POLICY_TOKENS_DIR, selected_token)
        token_status = _check_token_expiry(token_path)

        if token_status["error"] or not token_status["valid"]:
            st.error("Selected token is not valid.")
            return

        st.success("✅ Token valid")

    with connection_column:
        st.markdown("#### Worker Node Connection")
        workers = _get_worker_hosts()
        if workers:
            worker_host = st.selectbox(
                "Worker host",
                workers,
                key="worker_select_activate",
            )
        else:
            worker_host = st.text_input(
                "Worker IP/hostname",
                key="worker_input_activate",
            )

        ssh_user = st.text_input(
            "SSH user",
            value="ubuntu",
            key="ssh_user_activate",
        )
        brane_port = st.text_input(
            "brane-chk port",
            value="50051",
            key="port_activate",
        )

    def start_lifecycle_task(operation: str, version_id: str | None = None) -> None:
        if not worker_host or not ssh_user or not brane_port:
            st.error("Worker host, SSH user, and brane-chk port are required.")
            return

        command = [
            sys.executable,
            str(Path(__file__).with_name("policy_lifecycle_task.py")),
            operation,
            "--token-path",
            token_path,
            "--worker-host",
            worker_host,
            "--ssh-user",
            ssh_user,
            "--brane-port",
            brane_port,
        ]
        if version_id:
            command.extend(["--version-id", version_id])

        label = (
            f"List policies: {worker_host}"
            if operation == "list"
            else f"Activate policy {version_id}: {worker_host}"
        )

        task, error = start_task(
            role="policy-manager",
            operation=f"policy_{operation}",
            label=label,
            command=command,
            cwd=REPO_ROOT,
            metadata={
                "worker_host": worker_host,
                "ssh_user": ssh_user,
                "brane_port": brane_port,
                "version_id": version_id,
            },
            lock_name="policy-lifecycle",
        )

        if error:
            st.error(error)
        else:
            st.session_state.policy_lifecycle_task_id = task["id"]
            st.success("Policy lifecycle task started in the background.")
            st.rerun()

    st.divider()
    st.markdown("#### Available Policy Versions")

    if st.button("📋 List Policy Versions", key="btn_list_versions"):
        start_lifecycle_task("list")

    st.divider()
    st.markdown("#### Activate Version")

    version_id = st.text_input(
        "Policy version ID to activate",
        key="version_id_input",
    )

    if st.button("✅ Activate Policy", key="btn_activate_policy", type="primary"):
        if not version_id:
            st.error("Policy version ID is required.")
        else:
            start_lifecycle_task("activate", version_id)

    task_id = st.session_state.get("policy_lifecycle_task_id")
    if task_id:
        render_task_monitor(
            task_id,
            title="Policy lifecycle task progress",
        )


# =============================================================
# MAIN DASHBOARD FUNCTION
# =============================================================

def render_policy_manager_dashboard() -> None:
    """
    Render the complete policy manager dashboard.
    
    Function Purpose:
        Displays the policy management interface including token 
        management, policy upload, and policy activation capabilities.
    
    Parameters:
        None
    
    Returns:
        None
    """
    st.title("🔐 Policy Manager Dashboard")
    st.markdown("Manage eFLINT policies and domain access control")
    st.divider()
    
    # Tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Status",
        "🔑 Tokens",
        "📤 Add Policy",
        "✅ Activate Policy",
    ])
    
    with tab1:
        _render_environment_status()
    
    with tab2:
        _render_token_management()
    
    with tab3:
        _render_policy_upload()
    
    with tab4:
        _render_policy_activation()
    
    st.divider()
    
    # Footer with guidance
    with st.expander("📖 Policy Manager Guide"):
        st.markdown("""
        ### Policy Lifecycle
        
        1. **Prepare Token** (tab: Tokens)
           - Ensure your policy_token.json is in policy_tokens/
           - Check token validity (must not be expired)
        
        2. **Add Policy** (tab: Add Policy)
           - Select policy token
           - Select .eflint policy file
           - Provide worker node connection details
           - Upload and add policy to domain
           - Note the version ID returned
        
        3. **Activate Policy** (tab: Activate Policy)
           - Select policy token
           - List available policy versions
           - Select version ID to activate
           - Verify active policy is set
        
        ### Key Concepts
        
        - **Policy Token**: JWT token with policy expert permissions
        - **Policy Version**: Unique ID for each uploaded policy
        - **Active Policy**: The policy version currently enforced on the domain
        - **Worker Domain**: The Brane worker node where policy is enforced
        
        ### Troubleshooting
        
        - **Token Expired?** - Request a new one from your Brane admin
        - **SSH Connection Failed?** - Check SSH keys and network connectivity
        - **Policy Activation Denied?** - Verify token has correct permissions
        - **Workflow Still Denied?** - Check policy rules permit the task
        """)


# =============================================================
# END OF FILE
# =============================================================
