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
import streamlit as st
from typing import Optional, List

from modules import task_manager
from modules.task_ui import render_task_monitor

from modules.config import (
    PACKAGES_DIR,
    CERTS_DIR,
    DATASETS_DIR,
    list_packages,
    list_certs,
    list_datasets,
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


def _get_workflows() -> List[str]:
    """
    Get list of available workflow files (.bs).
    
    Returns:
        List of workflow file paths relative to PACKAGES_DIR
    """
    workflows = []
    try:
        for root, dirs, files in os.walk(PACKAGES_DIR):
            for file in files:
                if file.endswith('.bs'):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, PACKAGES_DIR)
                    workflows.append(rel_path)
    except Exception:
        pass
    return sorted(workflows)


# =============================================================
# UI SECTIONS
# =============================================================

def _render_environment_status() -> None:
    """Render environment status overview."""
    st.subheader("📊 Environment Status")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        packages = list_packages()
        st.metric("📦 Packages", len(packages))
        if packages:
            with st.expander("View packages"):
                for pkg in packages:
                    st.caption(f"• {pkg}")
    
    with col2:
        certs = list_certs()
        st.metric("🔐 Certificates", len(certs))
        if certs:
            with st.expander("View certificates"):
                for cert in certs:
                    st.caption(f"• {cert}")
    
    with col3:
        datasets = list_datasets()
        st.metric("📂 Datasets", len(datasets))
        if datasets:
            with st.expander("View datasets"):
                for ds in datasets:
                    st.caption(f"• {ds}")


def _render_instance_management() -> None:
    """Render instance management section."""
    st.subheader("🖥️ Instance Management")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### List Instances")
        if st.button("📋 Show Instances", key="btn_list_instances"):
            try:
                result = subprocess.run(
                    ["brane", "instance", "list"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    st.code(result.stdout, language="text")
                else:
                    st.error("Failed to list instances")
            except Exception as e:
                st.error(f"Error: {e}")
    
    with col2:
        st.markdown("#### Add Instance")
        with st.form("add_instance_form"):
            host = st.text_input("Central node IP/hostname")
            instance_name = st.text_input("Instance name")
            submitted = st.form_submit_button("Add Instance")
            
            if submitted:
                if host and instance_name:
                    try:
                        result = subprocess.run(
                            ["brane", "instance", "add", host, 
                             "--name", instance_name, "--use", "--unchecked", "--force"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if result.returncode == 0:
                            st.success(f"Instance '{instance_name}' added successfully!")
                        else:
                            st.error(f"Failed to add instance: {result.stderr}")
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.error("Both fields are required")


def _render_package_management() -> None:
    """Render package management section."""
    st.subheader("📦 Package Management")
    
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
            if st.button("🔨 Build Package", key="btn_build_pkg"):
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
        if st.button("📋 Show Built Packages", key="btn_list_built_pkg"):
            try:
                result = subprocess.run(
                    ["brane", "package", "list"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    st.code(result.stdout, language="text")
                else:
                    st.info("No packages built yet")
            except Exception as e:
                st.error(f"Error: {e}")

    package_build_task_id = st.session_state.get("user_package_build_task_id")
    if package_build_task_id:
        render_task_monitor(package_build_task_id, title="Package build progress")


def _render_workflow_execution() -> None:
    """Render workflow execution section."""
    st.subheader("⚙️ Workflow Execution")
    
    col1, col2 = st.columns(2)
    
    workflows = _get_workflows()
    
    if not workflows:
        st.warning("No .bs workflow files found in packages/")
        return
    
    with col1:
        st.markdown("#### Run Locally")
        selected_wf = st.selectbox(
            "Select workflow",
            workflows,
            key="wf_select_local"
        )
        username = st.text_input(
            "Username",
            value="test",
            key="wf_username_local"
        )
        if st.button("▶️ Run Locally", key="btn_run_local_wf"):
            wf_path = os.path.join(PACKAGES_DIR, selected_wf)
            if not os.path.exists(wf_path):
                st.error(f"Workflow not found: {wf_path}")
            else:
                task, error = task_manager.start_task(
                    role="user",
                    operation="workflow_run_local",
                    label=f"Local workflow: {selected_wf}",
                    command=["brane", "workflow", "run", username, wf_path],
                    cwd=os.path.dirname(PACKAGES_DIR),
                    metadata={
                        "mode": "local",
                        "username": username,
                        "workflow": selected_wf,
                    },
                    lock_name="workflow-execution",
                )
                if error:
                    st.error(error)
                else:
                    st.session_state.user_local_workflow_task_id = task["id"]
                    st.success("Local workflow started in the background.")
                    st.rerun()

    with col2:
        st.markdown("#### Run Remotely")
        instances = _get_instances()
        if instances:
            selected_instance = st.selectbox(
                "Select instance",
                instances,
                key="wf_select_instance"
            )
            selected_wf_remote = st.selectbox(
                "Select workflow",
                workflows,
                key="wf_select_remote"
            )
            username_remote = st.text_input(
                "Username",
                value="test",
                key="wf_username_remote"
            )
            if st.button("▶️ Run Remotely", key="btn_run_remote_wf"):
                wf_path = os.path.join(PACKAGES_DIR, selected_wf_remote)
                if not os.path.exists(wf_path):
                    st.error(f"Workflow not found: {wf_path}")
                else:
                    runner_path = os.path.join(
                        os.path.dirname(PACKAGES_DIR),
                        "scripts",
                        "run_remote_workflow.py",
                    )
                    task, error = task_manager.start_task(
                        role="user",
                        operation="workflow_run_remote",
                        label=f"Remote workflow: {selected_wf_remote}",
                        command=[
                            "python3",
                            runner_path,
                            "--instance",
                            selected_instance,
                            "--username",
                            username_remote,
                            "--workflow",
                            wf_path,
                        ],
                        cwd=os.path.dirname(PACKAGES_DIR),
                        metadata={
                            "mode": "remote",
                            "instance": selected_instance,
                            "username": username_remote,
                            "workflow": selected_wf_remote,
                        },
                        lock_name="workflow-execution",
                    )
                    if error:
                        st.error(error)
                    else:
                        st.session_state.user_remote_workflow_task_id = task["id"]
                        st.success("Remote workflow submission started in the background.")
                        st.rerun()
        else:
            st.warning("No instances configured. Use Instance Management to add one.")


    local_task_id = st.session_state.get("user_local_workflow_task_id")
    if local_task_id:
        render_task_monitor(local_task_id, title="Local workflow progress")

    remote_task_id = st.session_state.get("user_remote_workflow_task_id")
    if remote_task_id:
        render_task_monitor(remote_task_id, title="Remote workflow progress")


def _render_certificate_management() -> None:
    """Render certificate management section."""
    st.subheader("🔐 Certificate Management")
    
    st.info(
        """
        Certificates are stored in: `certs/<node>/`
        
        Each node directory should contain:
        - `ca.pem` - Certificate Authority
        - `client.pem` or `client-id.pem` - Client certificate
        - `client-key.pem` - Client private key
        """
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### View Certificates")
        certs = list_certs()
        if certs:
            for cert in certs:
                st.caption(f"✓ {cert}")
        else:
            st.info("No certificates found")
    
    with col2:
        st.markdown("#### Add Certificate")
        st.markdown("Manually place certificate files in:")
        st.code(f"{CERTS_DIR}/<node>/")
        st.markdown("Then use the Brane CLI:")
        st.code("brane certs add <ca.pem> <client.pem> <client-key.pem> --domain <node>")


# =============================================================
# MAIN DASHBOARD FUNCTION
# =============================================================

def render_user_dashboard() -> None:
    """
    Render the complete user dashboard.
    
    Function Purpose:
        Displays the user workflow interface including environment 
        status, instance management, package building, and workflow 
        execution capabilities.
    
    Parameters:
        None
    
    Returns:
        None
    """
    st.title("👤 User Dashboard")
    st.markdown("Manage packages, instances, and run workflows")
    st.divider()
    
    # Tabs for different sections
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Status",
        "🖥️ Instances",
        "📦 Packages",
        "⚙️ Workflows",
        "🔐 Certificates",
    ])
    
    with tab1:
        _render_environment_status()
    
    with tab2:
        _render_instance_management()
    
    with tab3:
        _render_package_management()
    
    with tab4:
        _render_workflow_execution()
    
    with tab5:
        _render_certificate_management()
    
    st.divider()
    
    # Footer with guidance
    with st.expander("📖 User Guide"):
        st.markdown("""
        ### Typical User Workflow
        
        1. **Setup Instance** (tab: Instances)
           - Get central node IP from your admin
           - Add instance with your instance name
        
        2. **Add Certificates** (tab: Certificates)
           - Place certificate files in `certs/<node>/`
           - Use Brane CLI to register them
        
        3. **Build Package** (tab: Packages)
           - Select a package from `packages/`
           - Click "Build Package"
        
        4. **Run Workflow** (tab: Workflows)
           - Select a `.bs` workflow file
           - Run locally or on remote domain
           - Monitor execution results
        
        ### Common Issues
        
        - **Execution Denied?** - Policy manager needs to activate a policy
        - **Connection Failed?** - Check instance IP and network connectivity
        - **Certificate Error?** - Ensure certificate has digitalSignature and clientAuth extensions
        """)


# =============================================================
# END OF FILE
# =============================================================
