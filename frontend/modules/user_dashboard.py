# =============================================================
# user_dashboard.py
# Version: 1.0.0
# Date: 2026-08-17
# Author: Brane Deployment Team
#
# Description:
#   Streamlit module for the User role dashboard.
#   Provides workflow authoring, package management, and
#   workflow execution capabilities for end users.
#
#   Mirrors the functionality of brane_helper_user.sh:
#   - Check environment and connectivity
#   - Manage instances and certificates
#   - Build and list packages
#   - Run workflows locally and remotely
#
# Key Responsibilities:
#   1. Display user environment status
#   2. Manage Brane instances
#   3. Add and manage certificates
#   4. Build packages from container.yml
#   5. List available packages
#   6. Run workflows locally
#   7. Run workflows on remote domains
#   8. Display workflow execution results
#
# Design Pattern:
#   Streamlit View Module - Implements render_user_dashboard()
#   function that displays the user workflow interface.
#
# Key Features:
#   - Environment status overview
#   - Instance management interface
#   - Certificate management
#   - Package building and listing
#   - Workflow selection and execution
#   - Real-time execution monitoring
#   - Error handling and guidance
#
# Dependencies:
#   - streamlit: Web UI framework
#   - modules.config: Repository configuration
#   - Standard library: subprocess, os
#
# =============================================================

import os
import subprocess
from pathlib import Path

import streamlit as st
from typing import List

from modules import task_manager
from modules.task_ui import render_task_monitor

from modules.config import (
    PACKAGES_DIR,
    CERTS_DIR,
    DATASETS_DIR,
    list_packages,
    list_certs,
    list_datasets,
    get_brane_executable,
)


# =============================================================
# HELPER FUNCTIONS
# =============================================================

def _get_instances() -> List[str]:
    """Return configured Brane instance names."""
    try:
        result = subprocess.run(
            ["brane", "instance", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    if result.returncode != 0:
        return []

    instances = []
    for line in result.stdout.splitlines():
        stripped = line.replace("\x00", "").strip()
        if not stripped:
            continue

        parts = stripped.split()
        if not parts or parts[0].upper() == "NAME":
            continue

        instances.append(parts[0])

    return instances


# =============================================================
# UI SECTIONS
# =============================================================

def _render_environment_status() -> None:
    """Render environment status overview."""
    st.subheader(" Environment Status")

    col1, col2, col3 = st.columns(3)

    with col1:
        packages = list_packages()
        st.metric(" Packages", len(packages))
        if packages:
            with st.expander("View packages"):
                for pkg in packages:
                    st.caption(f"• {pkg}")

    with col2:
        certs = list_certs()
        st.metric(" Certificates", len(certs))
        if certs:
            with st.expander("View certificates"):
                for cert in certs:
                    st.caption(f"• {cert}")

    with col3:
        datasets = list_datasets()
        st.metric(" Datasets", len(datasets))
        if datasets:
            with st.expander("View datasets"):
                for ds in datasets:
                    st.caption(f"• {ds}")


def _render_instance_management() -> None:
    """Render normal and advanced configured-instance management."""
    st.subheader("Configured instances")
    st.markdown(
        "Add the Central Brane endpoint that you will select in Workflow Studio "
        "for remote workflow execution."
    )

    left_column, right_column = st.columns(2)

    with left_column:
        st.markdown("#### Inspect instances")

        if st.button("Refresh configured instances", key="btn_list_instances"):
            task, error = task_manager.start_task(
                role="user",
                operation="instance_list",
                label="List configured instances",
                command=[get_brane_executable(), "instance", "list"],
                cwd=os.path.dirname(PACKAGES_DIR),
                metadata={"read_only": True},
                lock_name="instance-list",
            )

            if error:
                st.error(error)
            else:
                st.session_state.user_instance_list_task_id = task["id"]
                st.rerun()

        instance_list_task_id = st.session_state.get("user_instance_list_task_id")
        if instance_list_task_id:
            render_task_monitor(
                instance_list_task_id,
                title="Configured instances",
            )

    with right_column:
        st.markdown("#### Add instance")

        with st.form("add_instance_form"):
            host = st.text_input(
                "Central node address",
                placeholder="e.g. central.example.org or 145.100.135.209",
            )
            instance_name = st.text_input(
                "Instance name",
                placeholder="e.g. uva-central",
            )

            with st.expander("Advanced connection options"):
                st.caption(
                    "Use these only when instructed by the deployment "
                    "administrator. They reduce normal connection safeguards."
                )
                skip_validation = st.checkbox(
                    "Skip endpoint validation",
                    key="instance_skip_validation",
                )
                replace_existing = st.checkbox(
                    "Force replacement of an existing configuration",
                    key="instance_replace_existing",
                )

            submitted = st.form_submit_button("Add instance", type="primary")

        if submitted:
            if not host.strip() or not instance_name.strip():
                st.error("Central node address and instance name are required.")
            else:
                command = [
                    get_brane_executable(),
                    "instance",
                    "add",
                    host.strip(),
                    "--name",
                    instance_name.strip(),
                    "--use",
                ]

                if skip_validation:
                    command.append("--unchecked")
                if replace_existing:
                    command.append("--force")

                task, error = task_manager.start_task(
                    role="user",
                    operation="instance_add",
                    label=f"Add instance: {instance_name.strip()}",
                    command=command,
                    cwd=os.path.dirname(PACKAGES_DIR),
                    metadata={
                        "host": host.strip(),
                        "instance_name": instance_name.strip(),
                        "unchecked": skip_validation,
                        "force": replace_existing,
                        "select_after_add": True,
                    },
                    lock_name="instance-management",
                )

                if error:
                    st.error(error)
                else:
                    st.session_state.user_instance_add_task_id = task["id"]
                    st.success("Instance configuration started in the background.")
                    st.rerun()

    instance_add_task_id = st.session_state.get("user_instance_add_task_id")
    if instance_add_task_id:
        render_task_monitor(
            instance_add_task_id,
            title="Instance configuration progress",
        )


def _render_package_management() -> None:
    """Render package management section."""
    st.subheader(" Package Management")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Build Package")
        packages = list_packages()
        if packages:
            selected_pkg = st.selectbox(
                "Select package to build",
                packages,
                key="pkg_select_build"
            )
            if st.button(" Build Package", key="btn_build_pkg"):
                container_yml = os.path.join(PACKAGES_DIR, selected_pkg, "container.yml")
                if not os.path.exists(container_yml):
                    st.error(f"container.yml not found in {selected_pkg}")
                else:
                    task, error = task_manager.start_task(
                        role="user",
                        operation="package_build",
                        label=f"Build package: {selected_pkg}",
                        command=[
                            "brane",
                            "package",
                            "build",
                            "--arch",
                            "x86_64",
                            container_yml,
                        ],
                        cwd=os.path.dirname(PACKAGES_DIR),
                        metadata={
                            "architecture": "x86_64",
                            "package": selected_pkg,
                            "container_yml": container_yml,
                        },
                        lock_name="package-build",
                    )
                    if error:
                        st.error(error)
                    else:
                        st.session_state.user_package_build_task_id = task["id"]
                        st.success("Package build started in the background.")
                        st.rerun()
        else:
            st.info("No packages found in packages/ directory")

    with col2:
        st.markdown("#### List Built Packages")
        if st.button(" Show Built Packages", key="btn_list_built_pkg"):
            task, error = task_manager.start_task(
                role="user",
                operation="package_list",
                label="List built packages",
                command=["brane", "package", "list"],
                cwd=os.path.dirname(PACKAGES_DIR),
                metadata={"read_only": True},
                lock_name="package-list",
            )
            if error:
                st.error(error)
            else:
                st.session_state.user_package_list_task_id = task["id"]
                st.success("Package listing started in the background.")
                st.rerun()

        package_list_task_id = st.session_state.get("user_package_list_task_id")
        if package_list_task_id:
            render_task_monitor(
                package_list_task_id,
                title="Built packages",
            )

    package_build_task_id = st.session_state.get("user_package_build_task_id")
    if package_build_task_id:
        render_task_monitor(package_build_task_id, title="Package build progress")


def _certificate_bundle_paths(certificate_name: str) -> tuple[Path, Path, Path]:
    """Return expected certificate paths without reading private-key contents."""
    bundle_directory = Path(CERTS_DIR) / certificate_name
    ca_path = bundle_directory / "ca.pem"
    client_path = bundle_directory / "client.pem"

    if not client_path.is_file():
        client_path = bundle_directory / "client-id.pem"

    key_path = bundle_directory / "client-key.pem"
    return ca_path, client_path, key_path


def _render_certificate_management() -> None:
    """Render certificate-bundle inspection and task-backed registration."""
    st.subheader("Certificate bundles")
    st.markdown(
        "Select a local certificate bundle for a Brane domain. Certificate "
        "contents and private keys are never displayed in this interface."
    )

    certificate_names = list_certs()

    if not certificate_names:
        st.info(
            "No certificate bundles were found. Store a bundle in "
            "`certs/<domain>/` containing `ca.pem`, `client.pem` or "
            "`client-id.pem`, and `client-key.pem`."
        )
        return

    bundle_rows = []
    for certificate_name in certificate_names:
        ca_path, client_path, key_path = _certificate_bundle_paths(certificate_name)
        missing_files = [
            label
            for label, file_path in {
                "CA certificate": ca_path,
                "Client certificate": client_path,
                "Client private key": key_path,
            }.items()
            if not file_path.is_file()
        ]

        bundle_rows.append(
            {
                "Domain directory": certificate_name,
                "Status": (
                    "Ready to register"
                    if not missing_files
                    else f"Missing: {', '.join(missing_files)}"
                ),
            }
        )

    st.dataframe(bundle_rows, use_container_width=True, hide_index=True)

    ready_certificates = [
        certificate_name
        for certificate_name in certificate_names
        if all(
            file_path.is_file()
            for file_path in _certificate_bundle_paths(certificate_name)
        )
    ]

    if not ready_certificates:
        st.warning(
            "No complete certificate bundle is available for registration. "
            "Complete one bundle before continuing."
        )
        return

    st.markdown("#### Register certificate bundle")

    with st.form("register_certificate_form"):
        selected_certificate = st.selectbox(
            "Certificate bundle",
            ready_certificates,
            help="The directory name normally matches the Brane domain ID.",
        )
        domain_name = st.text_input(
            "Brane domain ID",
            value=selected_certificate,
            help="Confirm the domain ID used by the selected certificate bundle.",
        )
        submitted = st.form_submit_button(
            "Register certificate",
            type="primary",
        )

    if submitted:
        if not domain_name.strip():
            st.error("A Brane domain ID is required.")
            return

        ca_path, client_path, key_path = _certificate_bundle_paths(
            selected_certificate
        )

        task, error = task_manager.start_task(
            role="user",
            operation="certificate_register",
            label=f"Register certificate: {domain_name.strip()}",
            command=[
                get_brane_executable(),
                "certs",
                "add",
                str(ca_path),
                str(client_path),
                str(key_path),
                "--domain",
                domain_name.strip(),
            ],
            cwd=os.path.dirname(PACKAGES_DIR),
            metadata={
                "certificate_bundle": selected_certificate,
                "domain": domain_name.strip(),
            },
            lock_name="certificate-registration",
        )

        if error:
            st.error(error)
        else:
            st.session_state.user_certificate_register_task_id = task["id"]
            st.success("Certificate registration started in the background.")
            st.rerun()

    task_id = st.session_state.get("user_certificate_register_task_id")
    if task_id:
        render_task_monitor(
            task_id,
            title="Certificate registration progress",
        )


# =============================================================
# MAIN DASHBOARD FUNCTION
# =============================================================

def render_user_dashboard() -> None:
    """Render the user workspace readiness and resource-management dashboard."""
    st.title("User Workspace")
    st.markdown(
        "Prepare your local Brane environment, manage reusable resources, "
        "and then create and run workflows in **Workflow Studio**."
    )

    if st.button(
        "Open Workflow Studio",
        key="open_workflow_studio",
        type="primary",
    ):
        st.session_state.requested_page = "user_workflows"
        st.rerun()

    st.divider()

    readiness_tab, instances_tab, packages_tab, certificates_tab = st.tabs(
        [
            "Workspace readiness",
            "Instances",
            "Packages",
            "Certificates",
        ]
    )

    with readiness_tab:
        _render_environment_status()
        st.info(
            "Typical sequence: configure an instance, register the applicable "
            "certificate, build a package, then open Workflow Studio."
        )

    with instances_tab:
        _render_instance_management()

    with packages_tab:
        _render_package_management()

    with certificates_tab:
        _render_certificate_management()

    st.divider()

    with st.expander("User guide"):
        st.markdown(
            """### Typical workflow

1. **Configure an instance** in the Instances tab.
2. **Confirm the required certificate bundle** in the Certificates tab.
3. **Build a package** for the deployment architecture in the Packages tab.
4. Open **Workflow Studio** to author, submit, and monitor a workflow.

### Common issues

- **Execution denied:** a Policy Manager must activate the applicable policy.
- **Connection failed:** confirm the configured instance address and network access.
- **Certificate error:** confirm that the selected certificate supports
  `digitalSignature` and `clientAuth`.
"""
        )


# =============================================================
# END OF FILE
# =============================================================
