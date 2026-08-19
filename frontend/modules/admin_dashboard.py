# =============================================================
# admin_dashboard.py
# Role-focused Administration workspace
# =============================================================

import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import streamlit as st

from modules.config import (
    ANSIBLE_DIR,
    CERTS_DIR,
    INVENTORY_PATH,
    POLICY_TOKENS_DIR,
    REPO_ROOT,
    list_certs,
    list_policy_tokens,
)
from modules.task_manager import start_task
from modules.task_ui import render_task_monitor


def _get_deployment_tags() -> Dict[str, str]:
    """Return deployment phases available in the Ansible playbook."""
    return {
        "Full deployment": "",
        "Phase 0: Prerequisites": "prerequisites",
        "Phase 1: Install Branectl": "branectl",
        "Phase 2: Configure workers": "workers",
        "Phase 3: Configure central": "central",
        "Phase 4: Exchange certificates": "certs",
        "Phase 5: Start services": "start",
        "Phase 6: Run smoke tests": "smoke",
    }


def _get_worker_domains() -> Dict[str, str]:
    """
    Return a mapping of Brane domain IDs to Ansible inventory host names.

    Example:
        {"client-node-2": "worker-vm-2"}
    """
    try:
        result = subprocess.run(
            [
                "ansible-inventory",
                "-i",
                str(INVENTORY_PATH),
                "--playbook-dir",
                str(ANSIBLE_DIR),
                "--list",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

        if result.returncode != 0:
            return {}

        inventory = json.loads(result.stdout)
        worker_hosts = inventory.get("workers", {}).get("hosts", [])
        hostvars = inventory.get("_meta", {}).get("hostvars", {})

        domains: Dict[str, str] = {}
        for hostname in worker_hosts:
            domain_id = hostvars.get(hostname, {}).get("location_id", hostname)
            domains[str(domain_id)] = str(hostname)

        return dict(sorted(domains.items()))
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}


def _create_certs_zip(domain: str) -> Tuple[bool, bytes, str]:
    """Create an in-memory ZIP containing one domain's certificate bundle."""
    try:
        domain_cert_dir = CERTS_DIR / domain
        if not domain_cert_dir.is_dir():
            return False, b"", "Certificate directory no longer exists."

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(domain_cert_dir.iterdir()):
                if file_path.is_file():
                    archive.write(file_path, arcname=file_path.name)

        zip_buffer.seek(0)
        return True, zip_buffer.getvalue(), f"brane-certs-{domain}.zip"
    except OSError as exc:
        return False, b"", f"Could not package certificates: {exc}"


def _start_admin_task(
    *,
    operation: str,
    label: str,
    command: List[str],
    cwd: str | Path,
    metadata: Dict[str, object],
    lock_name: str,
    session_key: str,
) -> None:
    """Start a task and retain its identifier for the Admin task monitor."""
    task, error = start_task(
        role="admin",
        operation=operation,
        label=label,
        command=command,
        cwd=str(cwd),
        metadata=metadata,
        lock_name=lock_name,
    )

    if error:
        st.error(error)
        return

    st.session_state[session_key] = task["id"]
    st.success("Task started in the background.")
    st.rerun()


def _start_health_check() -> None:
    """Start the existing health-check script as a read-only task."""
    candidate_paths = [
        Path(REPO_ROOT) / "scripts" / "brane_healthcheck.sh",
        Path(REPO_ROOT) / "brane_healthcheck.sh",
        Path("brane_healthcheck.sh"),
    ]
    script_path = next((path for path in candidate_paths if path.is_file()), None)

    if script_path is None:
        st.error("The infrastructure health-check script could not be found.")
        st.info("See Advanced diagnostics for the paths checked.")
        return

    _start_admin_task(
        operation="infrastructure_health_check",
        label="Run infrastructure health check",
        command=["bash", str(script_path)],
        cwd=ANSIBLE_DIR,
        metadata={
            "read_only": True,
            "working_directory": str(ANSIBLE_DIR),
        },
        lock_name="admin-infrastructure-operation",
        session_key="admin_infrastructure_task_id",
    )


def _set_admin_panel(panel: str) -> None:
    """Open an Admin action panel below the dashboard actions."""
    st.session_state.admin_active_panel = panel
    st.rerun()


def _go_to_workspace(role: str, page: str) -> None:
    """Switch workspace using the established session-state navigation flow."""
    st.session_state.current_role = role
    st.session_state.requested_page = page
    st.rerun()


def _render_status_summary(worker_domains: Dict[str, str]) -> None:
    """Render compact, truthful Admin workspace status indicators."""
    monitored_tasks = sum(
        bool(st.session_state.get(key))
        for key in (
            "admin_infrastructure_task_id",
            "admin_certificate_task_id",
            "admin_policy_token_task_id",
        )
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Configured domains", len(worker_domains))
    with col2:
        st.metric("Certificate bundles", len(list_certs()))
    with col3:
        st.metric("Task monitors", monitored_tasks)

    if monitored_tasks:
        st.caption(
            "A task launched during this browser session is available below. "
            "Use Task History for the complete task record."
        )
    else:
        st.caption(
            "No Admin task has been launched in this browser session. "
            "Run a health check after infrastructure changes."
        )


def _render_primary_actions() -> None:
    """Render the four agreed primary Admin responsibilities."""
    st.markdown("### Primary actions")

    deploy_col, health_col = st.columns(2)
    with deploy_col:
        st.markdown("#### Deploy infrastructure")
        st.caption(
            "Select and execute an Ansible deployment phase, with "
            "dry-run and syntax-check options."
        )
        if st.button(
            "Open deployment",
            key="admin_open_deployment",
            type="primary",
            use_container_width=True,
        ):
            _set_admin_panel("deployment")

    with health_col:
        st.markdown("#### Check infrastructure health")
        st.caption(
            "Run the existing read-only health check against the central "
            "and worker infrastructure."
        )
        if st.button(
            "Run health check",
            key="admin_run_health_check",
            use_container_width=True,
        ):
            _start_health_check()

    certificate_col, token_col = st.columns(2)
    with certificate_col:
        st.markdown("#### Domain certificates")
        st.caption(
            "Generate or download the current end-user certificate bundle "
            "for a Brane domain."
        )
        if st.button(
            "Manage certificates",
            key="admin_open_certificates",
            use_container_width=True,
        ):
            _set_admin_panel("certificates")

    with token_col:
        st.markdown("#### Policy-manager tokens")
        st.caption(
            "Generate and download a domain-specific token for a policy manager."
        )
        if st.button(
            "Manage policy tokens",
            key="admin_open_policy_tokens",
            use_container_width=True,
        ):
            _set_admin_panel("policy_tokens")


def _render_deployment_panel() -> None:
    """Render the focused infrastructure deployment flow."""
    st.markdown("### Deploy infrastructure")
    st.caption(
        "Deployment is an administrative operation. A second infrastructure "
        "operation cannot start while another one holds the infrastructure lock."
    )

    inventory_path = Path(INVENTORY_PATH)
    playbook_path = Path(ANSIBLE_DIR) / "site.yml"

    if not inventory_path.is_file():
        st.error("The configured Ansible inventory file is unavailable.")
        return

    if not playbook_path.is_file():
        st.error("The configured Ansible playbook is unavailable.")
        return

    tags = _get_deployment_tags()
    selected_phase = st.selectbox(
        "Deployment phase",
        list(tags.keys()),
        key="admin_deployment_phase",
    )

    phase_tag = tags[selected_phase]
    if phase_tag:
        st.info(f"This runs only the `{phase_tag}` Ansible tag.")
    else:
        st.warning("This runs the complete infrastructure deployment playbook.")

    deploy_col, close_col = st.columns([1, 1])
    with deploy_col:
        if st.button(
            "Start deployment",
            key="admin_start_deployment",
            type="primary",
        ):
            command = [
                "ansible-playbook",
                "-i",
                str(inventory_path),
                str(playbook_path),
            ]
            if phase_tag:
                command.extend(["--tags", phase_tag])

            _start_admin_task(
                operation="infrastructure_deploy",
                label=f"Deploy infrastructure: {selected_phase}",
                command=command,
                cwd=ANSIBLE_DIR,
                metadata={
                    "inventory_path": str(inventory_path),
                    "playbook_path": str(playbook_path),
                    "phase": selected_phase,
                    "tags": [phase_tag] if phase_tag else [],
                },
                lock_name="admin-infrastructure-operation",
                session_key="admin_infrastructure_task_id",
            )

    with close_col:
        if st.button("Close deployment", key="admin_close_deployment"):
            st.session_state.admin_active_panel = None
            st.rerun()

    with st.expander("Advanced deployment checks"):
        check_col, syntax_col, smoke_col = st.columns(3)

        with check_col:
            if st.button("Dry run", key="admin_deployment_dry_run"):
                _start_admin_task(
                    operation="infrastructure_dry_run",
                    label="Dry-run infrastructure deployment",
                    command=[
                        "ansible-playbook",
                        "-i",
                        str(inventory_path),
                        str(playbook_path),
                        "--check",
                        "--diff",
                    ],
                    cwd=ANSIBLE_DIR,
                    metadata={"read_only": True},
                    lock_name="admin-infrastructure-operation",
                    session_key="admin_infrastructure_task_id",
                )

        with syntax_col:
            if st.button("Syntax check", key="admin_deployment_syntax_check"):
                _start_admin_task(
                    operation="infrastructure_syntax_check",
                    label="Check infrastructure playbook syntax",
                    command=[
                        "ansible-playbook",
                        "-i",
                        str(inventory_path),
                        str(playbook_path),
                        "--syntax-check",
                    ],
                    cwd=ANSIBLE_DIR,
                    metadata={"read_only": True},
                    lock_name="admin-infrastructure-operation",
                    session_key="admin_infrastructure_task_id",
                )

        with smoke_col:
            if st.button("Run smoke tests", key="admin_deployment_smoke_tests"):
                _start_admin_task(
                    operation="infrastructure_smoke_tests",
                    label="Run infrastructure smoke tests",
                    command=[
                        "ansible-playbook",
                        "-i",
                        str(inventory_path),
                        str(playbook_path),
                        "--tags",
                        "smoke",
                    ],
                    cwd=ANSIBLE_DIR,
                    metadata={"read_only": True, "tags": ["smoke"]},
                    lock_name="admin-infrastructure-operation",
                    session_key="admin_infrastructure_task_id",
                )


def _render_certificates_panel(worker_domains: Dict[str, str]) -> None:
    """Render generation and secure download of one domain certificate bundle."""
    st.markdown("### Domain certificates")
    st.warning(
        "Certificate bundles include a private key. Download and share them "
        "only through an approved secure channel."
    )

    if not worker_domains:
        st.error(
            "No worker domains could be read from the configured Ansible inventory."
        )
        return

    selected_domain = st.selectbox(
        "Brane domain",
        list(worker_domains.keys()),
        key="admin_certificate_domain",
    )
    inventory_host = worker_domains[selected_domain]

    st.caption(
        f"Brane domain `{selected_domain}` is deployed on inventory host "
        f"`{inventory_host}`."
    )

    st.markdown("#### Generate replacement bundle")
    st.warning(
        f"Generating a certificate for `{selected_domain}` replaces its current "
        "client certificate and private key."
    )

    confirm_replacement = st.checkbox(
        "I understand that this replaces the current certificate bundle.",
        key="admin_confirm_certificate_replacement",
    )

    generate_col, close_col = st.columns(2)
    with generate_col:
        if st.button(
            "Generate certificate bundle",
            key="admin_generate_certificate",
            type="primary",
            disabled=not confirm_replacement,
        ):
            script_path = Path(REPO_ROOT) / "scripts" / "brane_gen_cert.sh"
            if not script_path.is_file():
                st.error("The certificate-generation script is unavailable.")
                return

            _start_admin_task(
                operation="domain_certificate_generate",
                label=f"Generate certificate bundle: {selected_domain}",
                command=[
                    "bash",
                    str(script_path),
                    "--inventory",
                    str(INVENTORY_PATH),
                    "--node",
                    inventory_host,
                    "--output-name",
                    selected_domain,
                    "--output-dir",
                    str(CERTS_DIR),
                ],
                cwd=REPO_ROOT,
                metadata={
                    "domain_id": selected_domain,
                    "inventory_host": inventory_host,
                },
                lock_name="certificate-generation",
                session_key="admin_certificate_task_id",
            )

    with close_col:
        if st.button("Close certificates", key="admin_close_certificates"):
            st.session_state.admin_active_panel = None
            st.rerun()

    st.markdown("#### Download existing bundle")
    certificate_domains = list_certs()

    if not certificate_domains:
        st.info("No local certificate bundles are available yet.")
        return

    download_domain = st.selectbox(
        "Certificate bundle to download",
        certificate_domains,
        key="admin_download_certificate_domain",
    )

    if st.button(
        "Prepare certificate download",
        key="admin_prepare_certificate_download",
    ):
        success, zip_data, filename = _create_certs_zip(download_domain)
        if success:
            st.session_state.admin_certificate_download = {
                "domain": download_domain,
                "data": zip_data,
                "filename": filename,
            }
        else:
            st.error(filename)

    prepared_download = st.session_state.get("admin_certificate_download")
    if prepared_download and prepared_download.get("domain") == download_domain:
        st.download_button(
            label=f"Download {prepared_download['filename']}",
            data=prepared_download["data"],
            file_name=prepared_download["filename"],
            mime="application/zip",
            key="admin_download_certificate_bundle",
            type="primary",
        )


def _render_policy_tokens_panel(worker_domains: Dict[str, str]) -> None:
    """Render policy-manager token generation and secure download."""
    st.markdown("### Policy-manager tokens")
    st.warning(
        "A policy-manager token authorises policy operations for its domain. "
        "Share it only with the intended policy manager through a secure channel."
    )

    if not worker_domains:
        st.error(
            "No worker domains could be read from the configured Ansible inventory."
        )
        return

    manager_name = st.text_input(
        "Policy manager name",
        key="admin_policy_manager_name",
        placeholder="e.g. alice",
    )
    domain_id = st.selectbox(
        "Brane domain",
        list(worker_domains.keys()),
        key="admin_policy_token_domain",
    )
    validity = st.text_input(
        "Token validity",
        value="30d",
        key="admin_policy_token_validity",
    )

    generate_col, close_col = st.columns(2)
    with generate_col:
        if st.button(
            "Generate policy-manager token",
            key="admin_generate_policy_token",
            type="primary",
        ):
            if not manager_name.strip():
                st.error("A policy manager name is required.")
                return

            token_task_script = Path(__file__).with_name(
                "policy_token_generate_task.py"
            )
            if not token_task_script.is_file():
                st.error("The policy-token generation task script is unavailable.")
                return

            _start_admin_task(
                operation="policy_token_generate",
                label=f"Generate policy token: {manager_name.strip()} for {domain_id}",
                command=[
                    sys.executable,
                    str(token_task_script),
                    "--manager-name",
                    manager_name.strip(),
                    "--domain-id",
                    domain_id,
                    "--validity",
                    validity.strip(),
                    "--token-dir",
                    str(POLICY_TOKENS_DIR),
                ],
                cwd=REPO_ROOT,
                metadata={
                    "manager_name": manager_name.strip(),
                    "domain_id": domain_id,
                    "validity": validity.strip(),
                },
                lock_name="policy-token-generate",
                session_key="admin_policy_token_task_id",
            )

    with close_col:
        if st.button("Close policy tokens", key="admin_close_policy_tokens"):
            st.session_state.admin_active_panel = None
            st.rerun()

    st.markdown("#### Download generated token")
    token_files = list_policy_tokens()

    if not token_files:
        st.info("No generated policy-token files are available yet.")
        return

    selected_token_file = st.selectbox(
        "Stored token file",
        token_files,
        key="admin_generated_policy_token_file",
    )
    selected_token_path = POLICY_TOKENS_DIR / selected_token_file

    if selected_token_path.is_file():
        st.download_button(
            label=f"Download {selected_token_path.name}",
            data=selected_token_path.read_bytes(),
            file_name=selected_token_path.name,
            mime="application/json",
            key="admin_download_generated_policy_token",
            type="primary",
        )
    else:
        st.error("The selected token file no longer exists.")


def _render_task_monitors() -> None:
    """Render monitors for tasks started through the Admin workspace."""
    task_monitors = [
        (
            "admin_infrastructure_task_id",
            "Infrastructure task progress",
        ),
        (
            "admin_certificate_task_id",
            "Certificate-generation progress",
        ),
        (
            "admin_policy_token_task_id",
            "Policy-token generation progress",
        ),
    ]

    active_monitors = [
        (session_key, title)
        for session_key, title in task_monitors
        if st.session_state.get(session_key)
    ]

    if not active_monitors:
        return

    st.divider()
    st.markdown("### Recent administrative task")

    for session_key, title in active_monitors:
        render_task_monitor(st.session_state[session_key], title=title)


def _render_workspace_navigation() -> None:
    """Render simple navigation to the two non-Admin workspaces."""
    st.divider()
    st.markdown("### Need another workspace?")
    st.caption(
        "Test packages, instances, and workflows in User Workspace. "
        "Manage or test policies in Policy Management."
    )

    user_col, policy_col = st.columns(2)
    with user_col:
        if st.button(
            "Go to User Workspace",
            key="admin_go_to_user_workspace",
            use_container_width=True,
        ):
            _go_to_workspace("user", "user_overview")

    with policy_col:
        if st.button(
            "Go to Policy Management",
            key="admin_go_to_policy_workspace",
            use_container_width=True,
        ):
            _go_to_workspace("policy_manager", "policy_overview")


def _render_advanced_diagnostics() -> None:
    """Keep implementation details out of the normal Admin workflow."""
    health_script_paths = [
        Path(REPO_ROOT) / "scripts" / "brane_healthcheck.sh",
        Path(REPO_ROOT) / "brane_healthcheck.sh",
    ]

    with st.expander("Advanced diagnostics"):
        st.code(
            "\n".join(
                [
                    f"Repository root: {REPO_ROOT}",
                    f"Ansible directory: {ANSIBLE_DIR}",
                    f"Inventory: {INVENTORY_PATH}",
                    f"Certificates: {CERTS_DIR}",
                    f"Policy tokens: {POLICY_TOKENS_DIR}",
                    f"Inventory exists: {Path(INVENTORY_PATH).is_file()}",
                    f"Ansible directory exists: {Path(ANSIBLE_DIR).is_dir()}",
                    f"Certificate directory exists: {CERTS_DIR.is_dir()}",
                    "",
                    "Health-check scripts:",
                    *[
                        f"- {path} exists: {path.is_file()}"
                        for path in health_script_paths
                    ],
                ]
            ),
            language="text",
        )


def render_admin_dashboard() -> None:
    """Render the role-focused Administration workspace."""
    st.title("Administration")
    st.markdown(
        "Deploy and maintain Brane infrastructure, and provision domain "
        "access material."
    )

    worker_domains = _get_worker_domains()
    _render_status_summary(worker_domains)

    st.divider()
    _render_primary_actions()

    active_panel = st.session_state.get("admin_active_panel")
    if active_panel:
        st.divider()

        if active_panel == "deployment":
            _render_deployment_panel()
        elif active_panel == "certificates":
            _render_certificates_panel(worker_domains)
        elif active_panel == "policy_tokens":
            _render_policy_tokens_panel(worker_domains)

    _render_task_monitors()
    _render_workspace_navigation()
    _render_advanced_diagnostics()
