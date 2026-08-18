import os
import platform
import subprocess
import sys
import streamlit as st
from pathlib import Path

from modules import task_manager
from modules.task_ui import render_task_monitor
from modules.config import REPO_ROOT

def render_cli_panel():
    st.title("💻 Brane CLI Environment Manager & Command Reference")
    st.write("Install system binaries, review command matrices, and trigger administrative hooks from a single terminal workspace.")

    with st.expander("📖 Workstation Setup Guidelines", expanded=True):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("""
            **What it does:** Detects host client architectures to automate local setups of the `brane` development tooling and acts as a comprehensive runtime interactive cheat sheet.
            """)
        with col_b:
            st.markdown("""
            **Who is this for:** All platform participants (Scientists, Developers, and Administrators).
            **Prerequisites:** Local user workspace access. **No root/sudo required.**
            """)

    # Natively handle tabs to separate Installation from the Interactive CLI References
    tab_install, tab_user_cli, tab_admin_cli = st.tabs([
        "📥 Download & Install CLI", 
        "🧑‍🔬 User CLI Reference (`brane`)", 
        "🛠️ Admin CLI Reference (`branectl`)"
    ])

    # ==========================================
    # TAB 1: DOWNLOAD & AUTOMATED INSTALLER
    # ==========================================
    with tab_install:
        detected_os = platform.system()
        detected_arch = platform.machine()
        st.subheader("🤖 Host System Specifications")
        st.info(f"**Detected OS:** {detected_os} | **Hardware Architecture:** {detected_arch}")
        
        binary_options = {
            "Linux (x86_64)": "brane-linux-x86_64",
            "Linux (ARM64/aarch64)": "brane-linux-aarch64",
            "macOS (Apple Silicon / M-Series)": "brane-macos-aarch64",
            "macOS (Intel Core)": "brane-macos-x86_64",
            "Windows (x86_64)": "brane-windows-x86_64.exe"
        }
        
        default_index = 0
        if detected_os == "Darwin":
            default_index = 2 if "arm" in detected_arch.lower() or "aarch" in detected_arch.lower() else 3
        elif detected_os == "Linux":
            default_index = 0 if "x86" in detected_arch else 1
        elif detected_os == "Windows":
            default_index = 4

        selected_platform = st.selectbox("Select target binary artifact variant:", list(binary_options.keys()), index=default_index, key="cli_platform_select")
        binary_name = binary_options[selected_platform]
        download_url = f"https://github.com/BraneFramework/brane/releases/download/nightly/{binary_name}"
        
        st.markdown(f"**Nightly Release Endpoint URL:** `{download_url}`")
        
        if st.button("Download & Register Local Binary", type="primary", key="cli_download_btn"):
            task, error = task_manager.start_task(
                role="user",
                operation="cli_install",
                label=f"Install Brane CLI: {selected_platform}",
                command=[
                    sys.executable,
                    str(Path(__file__).with_name("cli_install_task.py")),
                    "--download-url",
                    download_url,
                ],
                cwd=REPO_ROOT,
                metadata={
                    "platform_variant": selected_platform,
                    "download_url": download_url,
                },
                lock_name="cli-install",
            )
            if error:
                st.error(error)
            else:
                st.session_state.cli_install_task_id = task["id"]
                st.success("Brane CLI installation started in the background.")
                st.rerun()

        cli_install_task_id = st.session_state.get("cli_install_task_id")
        if cli_install_task_id:
            render_task_monitor(
                cli_install_task_id,
                title="Brane CLI installation progress",
            )

        st.markdown("### 🔌 Core Service Direct Switches")
        col_adm1, col_adm2, col_adm3 = st.columns(3)
        target_node_type = st.selectbox("Select Target Cluster Service Type Profile:", ["central", "worker", "proxy", "auxillary"], key="cli_node_type_select")
        
        with col_adm1:
            if st.button("▶️ Start Brane Services", type="primary", key="cli_start_srv_btn"):
                run_check_cmd(["branectl", "start", target_node_type])
        with col_adm2:
            if st.button("🛑 Stop Brane Services", key="cli_stop_srv_btn"):
                run_check_cmd(["branectl", "stop", target_node_type])
                
            st.divider()
        
        st.markdown("### 📑 Administrative Reference Matrix")
        col_ref1, col_ref2 = st.columns(2)
        
        with col_ref1:
            st.markdown(f"""
            #### 📥 Download Commands
            ```bash
            branectl download services {target_node_type} [OPTIONS]
            ```
            * `-f` : Create missing directories automatically
            * `--version <VER>` : Download a specific fixed version string
            
            #### 🔑 Identity & Cert Generation
            ```bash
            # Server Certificates
            branectl generate certs -f -p ./config/certs server <LOCATION_ID> -H <HOSTNAME>
            
            # Client Certificates
            branectl generate certs -f -p ./config/certs client <LOCATION_ID> -H <HOSTNAME>
            ```
            """)
            
        with col_ref2:
            st.markdown("""
            #### 🏗️ Configuration & Schema Generation
            ```bash
            # Infrastructure Configuration (Central Node Only)
            branectl generate infra -f -p ./config/infra.yml <ID:ADDR>...

            # Node Topologies Manifests
            branectl generate node -f central <HOSTNAME>
            branectl generate node -f worker <HOSTNAME> <LOCATION_ID>
            branectl generate node -f proxy <HOSTNAME>

            # Local Computing Backend (Worker Only)
            branectl generate backend -f -p ./config/backend.yml local
            ```
            
            #### 🛡️ Compliance Security Tokens
            ```bash
            branectl generate policy_secret -f -p <PATH>
            branectl generate policy_db -f -p <PATH>
            branectl generate policy_token <INITIATOR> <SYSTEM> <DURATION> -s <SECRET_PATH>
            ```
            """)

