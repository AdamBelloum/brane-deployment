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
import re
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


def _read_token_value(token_path: str) -> str:
    """Read a JWT from either a JSON token file or a raw-token file."""
    raw_value = Path(token_path).read_text(encoding="utf-8").strip()

    if not raw_value:
        raise ValueError("The token file is empty.")

    if not raw_value.startswith("{"):
        return raw_value

    token_data = json.loads(raw_value)
    if not isinstance(token_data, dict):
        raise ValueError("The JSON token file must contain an object.")

    token = token_data.get("token") or token_data.get("access_token")
    if token is None and token_data:
        token = next(iter(token_data.values()))

    if not isinstance(token, str) or not token.strip():
        raise ValueError("The token file does not contain a usable token.")

    return token.strip()


def _check_token_expiry(token_path: str) -> Dict[str, object]:
    """Check expiry of a JSON-wrapped or raw JWT without displaying it."""
    result: Dict[str, object] = {
        "valid": False,
        "remaining_days": 0,
        "remaining_hours": 0,
        "error": None,
    }

    try:
        token = _read_token_value(token_path)
        parts = token.split(".")

        if len(parts) != 3:
            result["error"] = "Invalid JWT format."
            return result

        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload))

        exp = decoded.get("exp")
        if not isinstance(exp, (int, float)):
            result["error"] = "The JWT does not contain a valid expiry claim."
            return result

        remaining = exp - time.time()
        if remaining <= 0:
            result["error"] = "Token expired."
            return result

        result["valid"] = True
        result["remaining_days"] = int(remaining // 86400)
        result["remaining_hours"] = int((remaining % 86400) // 3600)
        return result

    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        result["error"] = str(exc)
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

def _start_policy_task(
    *,
    operation: str,
    label: str,
    command: list[str],
    metadata: Dict[str, object],
    session_key: str,
    lock_name: str,
) -> None:
    """Start one policy task without persisting token material."""
    task, error = start_task(
        role="policy-manager",
        operation=operation,
        label=label,
        command=command,
        cwd=REPO_ROOT,
        metadata=metadata,
        lock_name=lock_name,
    )

    if error:
        st.error(error)
        return

    st.session_state[session_key] = task["id"]
    st.rerun()


def _render_policy_context() -> Dict[str, object]:
    """Render the complete domain-local context for policy operations."""
    st.subheader("Policy context")
    st.caption(
        "Policies are domain-local. Select a token, worker host, SSH user, "
        "Brane domain ID, and the worker node configuration. The token is "
        "never displayed, stored in task metadata, or passed as a command-line "
        "argument."
    )

    tokens = list_policy_tokens()
    workers = _get_worker_hosts()

    token_column, target_column, connection_column = st.columns([2, 2, 2])

    with token_column:
        if tokens:
            selected_token = st.selectbox(
                "Policy-manager token",
                tokens,
                key="policy_context_token",
            )
            token_path = os.path.join(POLICY_TOKENS_DIR, selected_token)
            token_status = _check_token_expiry(token_path)

            if token_status["valid"]:
                st.success(
                    "Token valid — "
                    f"{token_status['remaining_days']}d "
                    f"{token_status['remaining_hours']}h remaining"
                )
            else:
                st.error(
                    "Selected token is not usable: "
                    f"{token_status['error'] or 'unknown error'}"
                )
        else:
            selected_token = None
            token_path = None
            token_status = {"valid": False}
            st.error("No policy-manager tokens were found in `policy_tokens/`.")

    with target_column:
        if workers:
            worker_host = st.selectbox(
                "Worker host",
                workers,
                key="policy_context_worker",
            )
        else:
            worker_host = st.text_input(
                "Worker host",
                key="policy_context_worker_manual",
                placeholder="Worker hostname or IP address",
            )
            st.caption(
                "No worker was found in the inventory; enter the target manually."
            )

        ssh_user = st.text_input(
            "SSH user",
            key="policy_context_ssh_user",
            placeholder="The deployed worker login user",
        )
        domain_id = st.text_input(
            "Brane domain ID",
            key="policy_context_domain_id",
            placeholder="e.g. client-node-2",
            help=(
                "This is the Brane location identifier, not necessarily the "
                "worker hostname."
            ),
        )

    with connection_column:
        node_config = st.text_input(
            "Worker node.yml",
            key="policy_context_node_config",
            placeholder="/home/<ssh-user>/brane-worker/node.yml",
            help="The node configuration path on the selected worker.",
        )
        brane_port = st.text_input(
            "Checker policy port",
            value="50054",
            key="policy_context_brane_port",
            help="The checker endpoint is reached as 127.0.0.1:<port> "
            "inside the checker network namespace.",
        )

        if st.button("Check SSH", key="policy_context_check_ssh"):
            if not worker_host.strip() or not ssh_user.strip():
                st.error("A worker host and SSH user are required.")
            else:
                _start_policy_task(
                    operation="policy_ssh_connectivity_check",
                    label=(
                        "Check SSH connectivity: "
                        f"{ssh_user.strip()}@{worker_host.strip()}"
                    ),
                    command=[
                        "ssh",
                        "-o", "BatchMode=yes",
                        "-o", "ConnectTimeout=5",
                        "-o", "StrictHostKeyChecking=accept-new",
                        "-q",
                        f"{ssh_user.strip()}@{worker_host.strip()}",
                        "exit",
                    ],
                    metadata={
                        "worker_host": worker_host.strip(),
                        "ssh_user": ssh_user.strip(),
                        "read_only": True,
                    },
                    session_key="policy_ssh_check_task_id",
                    lock_name="policy-ssh-connectivity-check",
                )

    ssh_task_id = st.session_state.get("policy_ssh_check_task_id")
    if ssh_task_id:
        render_task_monitor(ssh_task_id, title="Worker SSH connectivity check")

    valid_domain_id = bool(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", domain_id.strip())
    )

    return {
        "ready": bool(
            token_path
            and token_status["valid"]
            and worker_host.strip()
            and ssh_user.strip()
            and valid_domain_id
            and node_config.strip()
            and brane_port.strip()
        ),
        "token_name": selected_token,
        "token_path": token_path,
        "worker_host": worker_host.strip(),
        "ssh_user": ssh_user.strip(),
        "domain_id": domain_id.strip(),
        "node_config": node_config.strip(),
        "brane_port": brane_port.strip(),
    }


def _render_policy_status(context: Dict[str, object]) -> None:
    """Render local policy resources and fetch the remote active-policy status."""
    st.subheader("Policy status")

    policies = _get_policy_files()
    tokens = list_policy_tokens()
    workers = _get_worker_hosts()

    metric_one, metric_two, metric_three = st.columns(3)
    metric_one.metric("Local policy files", len(policies))
    metric_two.metric("Available tokens", len(tokens))
    metric_three.metric("Inventory workers", len(workers))

    st.caption(
        "The deployment starts deny-all by default. A workflow remains denied "
        "until an appropriate uploaded policy version is activated."
    )

    if st.button(
        "Inspect policy state",
        key="policy_inspect_state",
        disabled=not context["ready"],
    ):
        _start_policy_task(
            operation="policy_list",
            label=f"Inspect policy state: {context['worker_host']}",
            command=[
                sys.executable,
                str(Path(__file__).with_name("policy_lifecycle_task.py")),
                "list",
                "--token-path", str(context["token_path"]),
                "--worker-host", str(context["worker_host"]),
                "--ssh-user", str(context["ssh_user"]),
                "--domain-id", str(context["domain_id"]),
                "--node-config", str(context["node_config"]),
                "--brane-port", str(context["brane_port"]),
            ],
            metadata={
                "worker_host": context["worker_host"],
                "ssh_user": context["ssh_user"],
                "brane_port": context["brane_port"],
                "read_only": True,
            },
            session_key="policy_inspect_task_id",
            lock_name="policy-lifecycle",
        )

    if not context["ready"]:
        st.info("Select a valid token and complete the worker context to inspect policy state.")

    task_id = st.session_state.get("policy_inspect_task_id")
    if task_id:
        render_task_monitor(task_id, title="Policy versions and active state")


def _render_policy_upload(context: Dict[str, object]) -> None:
    """Render policy selection and upload through the existing secure helper."""
    st.subheader("Upload policy version")
    st.caption(
        "Uploading adds a version to the target worker. It does not activate "
        "that version or change the policy currently enforced."
    )

    policies = _get_policy_files()
    if not policies:
        st.warning("No `.eflint` policy files were found in `policies/`.")
        return

    selected_policy = st.selectbox(
        "Local eFLINT policy",
        policies,
        key="policy_upload_file",
    )
    policy_path = os.path.join(POLICIES_DIR, selected_policy)

    if st.button(
        "Upload and add policy version",
        key="policy_upload_add",
        type="primary",
        disabled=not context["ready"],
    ):
        _start_policy_task(
            operation="policy_upload_add",
            label=f"Upload policy: {selected_policy}",
            command=[
                sys.executable,
                str(Path(__file__).with_name("policy_upload_task.py")),
                "--policy-path", policy_path,
                "--token-path", str(context["token_path"]),
                "--worker-host", str(context["worker_host"]),
                "--ssh-user", str(context["ssh_user"]),
                "--domain-id", str(context["domain_id"]),
                "--node-config", str(context["node_config"]),
                "--brane-port", str(context["brane_port"]),
            ],
            metadata={
                "policy_file": selected_policy,
                "worker_host": context["worker_host"],
                "ssh_user": context["ssh_user"],
                "brane_port": context["brane_port"],
            },
            session_key="policy_upload_task_id",
            lock_name="policy-upload-add",
        )

    task_id = st.session_state.get("policy_upload_task_id")
    if task_id:
        render_task_monitor(task_id, title="Policy upload progress")


def _render_policy_activation(context: Dict[str, object]) -> None:
    """Render version inspection and activation using the existing API helper."""
    st.subheader("Activate policy version")
    st.warning(
        "Activating a version changes the policy enforced on the selected worker."
    )

    list_column, activate_column = st.columns(2)

    with list_column:
        st.markdown("#### 1. Inspect available versions")
        st.caption(
            "List versions after an upload and copy the version ID returned by "
            "the worker."
        )

        if st.button(
            "List policy versions",
            key="policy_list_versions",
            disabled=not context["ready"],
        ):
            _start_policy_task(
                operation="policy_list",
                label=f"List policy versions: {context['worker_host']}",
                command=[
                    sys.executable,
                    str(Path(__file__).with_name("policy_lifecycle_task.py")),
                    "list",
                    "--token-path", str(context["token_path"]),
                    "--worker-host", str(context["worker_host"]),
                    "--ssh-user", str(context["ssh_user"]),
                    "--domain-id", str(context["domain_id"]),
                    "--node-config", str(context["node_config"]),
                    "--brane-port", str(context["brane_port"]),
                ],
                metadata={
                    "worker_host": context["worker_host"],
                    "ssh_user": context["ssh_user"],
                    "brane_port": context["brane_port"],
                    "read_only": True,
                },
                session_key="policy_list_task_id",
                lock_name="policy-lifecycle",
            )

        list_task_id = st.session_state.get("policy_list_task_id")
        if list_task_id:
            render_task_monitor(list_task_id, title="Available policy versions")

    with activate_column:
        st.markdown("#### 2. Activate a selected version")
        version_id = st.text_input(
            "Policy version ID",
            key="policy_activate_version_id",
        )
        confirm_activation = st.checkbox(
            "I understand that this changes the policy enforced on the worker.",
            key="policy_confirm_activation",
        )

        if st.button(
            "Activate selected version",
            key="policy_activate_version",
            type="primary",
            disabled=not (
                context["ready"] and version_id.strip() and confirm_activation
            ),
        ):
            _start_policy_task(
                operation="policy_activate",
                label=(
                    f"Activate policy {version_id.strip()}: "
                    f"{context['worker_host']}"
                ),
                command=[
                    sys.executable,
                    str(Path(__file__).with_name("policy_lifecycle_task.py")),
                    "activate",
                    "--token-path", str(context["token_path"]),
                    "--worker-host", str(context["worker_host"]),
                    "--ssh-user", str(context["ssh_user"]),
                    "--domain-id", str(context["domain_id"]),
                    "--node-config", str(context["node_config"]),
                    "--brane-port", str(context["brane_port"]),
                    "--version-id", version_id.strip(),
                ],
                metadata={
                    "worker_host": context["worker_host"],
                    "ssh_user": context["ssh_user"],
                    "brane_port": context["brane_port"],
                    "version_id": version_id.strip(),
                },
                session_key="policy_activate_task_id",
                lock_name="policy-lifecycle",
            )

        activate_task_id = st.session_state.get("policy_activate_task_id")
        if activate_task_id:
            render_task_monitor(
                activate_task_id,
                title="Policy activation and verification",
            )


def _render_token_management() -> None:
    """Display locally available policy-manager tokens and expiry state."""
    st.subheader("Policy-manager tokens")
    st.caption(
        "Tokens are supplied by an administrator and must be stored locally in "
        "`policy_tokens/`. Their values are not displayed."
    )

    tokens = list_policy_tokens()
    if not tokens:
        st.warning("No policy-manager tokens were found in `policy_tokens/`.")
        return

    for token_file in tokens:
        token_path = os.path.join(POLICY_TOKENS_DIR, token_file)
        token_status = _check_token_expiry(token_path)

        name_column, status_column = st.columns([2, 3])
        with name_column:
            st.code(token_file, language=None)
        with status_column:
            if token_status["valid"]:
                st.success(
                    f"Valid — expires in {token_status['remaining_days']}d "
                    f"{token_status['remaining_hours']}h"
                )
            else:
                st.error(token_status["error"] or "Invalid token")


# =============================================================
# MAIN DASHBOARD FUNCTION
# =============================================================

def render_policy_manager_dashboard() -> None:
    """Render the policy lifecycle workspace for one target worker."""
    st.title("Policy Manager Workspace")
    st.markdown(
        "Manage eFLINT policy versions for a worker domain: inspect policy "
        "state, upload a version, and explicitly activate it."
    )

    context = _render_policy_context()

    st.divider()
    status_tab, upload_tab, activate_tab, tokens_tab = st.tabs(
        [
            "Policy status",
            "Upload version",
            "Activate version",
            "Tokens",
        ]
    )

    with status_tab:
        _render_policy_status(context)

    with upload_tab:
        _render_policy_upload(context)

    with activate_tab:
        _render_policy_activation(context)

    with tokens_tab:
        _render_token_management()

    st.divider()
    with st.expander("Policy lifecycle guide"):
        st.markdown(
            """1. Select a valid **policy-manager token** and target worker.
2. Use **Check active policy** to establish the currently enforced state.
3. Upload a local `.eflint` file to add a policy version. Uploading does not activate it.
4. List policy versions and copy the intended version ID.
5. Confirm and activate that version. The task verifies the active policy afterwards.

A failed or missing policy activation normally leaves workflows denied because
the deployment uses a deny-all default. Ask an administrator for a replacement
token if the selected token is expired or lacks the necessary authority."""
        )


# =============================================================
# END OF FILE
# =============================================================
