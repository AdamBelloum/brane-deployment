import os
import platform
import subprocess
import streamlit as st

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
            **Prerequisites:** Execution privileges to write binary assets into system path frameworks (`/usr/local/bin`).
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
            log_area = st.empty()
            full_log = "=== Launching Client Binary Provision Loop ===\n"
            log_area.code(full_log)
            try:
                if detected_os in ["Linux", "Darwin"]:
                    target_path = "/usr/local/bin/brane"
                    full_log += f"Streaming payload via curl...\n"
                    log_area.code(full_log)
                    subprocess.run(["curl", "-L", "-o", "./brane_temp", download_url], check=True)
                    subprocess.run(["mv", "./brane_temp", target_path], check=True)
                    subprocess.run(["chmod", "+x", target_path], check=True)
                    full_log += f"✓ Binary deployed to {target_path}\n"
                elif detected_os == "Windows":
                    target_path = os.path.expanduser("~\\AppData\\Local\\Microsoft\\WindowsApps\\brane.exe")
                    subprocess.run(["curl", "-L", "-o", target_path, download_url], check=True)
                    full_log += f"✓ Binary deployed to {target_path}\n"
                    
                full_log += "\n=== Testing Installation Integrity ===\n"
                log_area.code(full_log)
                v_proc = subprocess.Popen(["brane", "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in iter(v_proc.stdout.readline, ''):
                    full_log += line
                    log_area.code(full_log)
                v_proc.stdout.close()
                v_proc.wait()
                st.success("🎉 Brane CLI successfully installed!")
            except Exception as e:
                st.error(f"Installation interrupted: {str(e)}")

    # ==========================================
    # TAB 2: USER CLI COMMAND PANEL (`brane`)
    # ==========================================
    with tab_user_cli:
        st.subheader("🧑‍🔬 Developer & Data Scientist Command Reference")
        st.write("Manage packages, run workflows, and inspect active instances.")
        
        # Live Interactive Query Tool Helper
        st.markdown("### ⚡ Quick Diagnostic Queries")
        col_u1, col_u2, col_u3 = st.columns(3)
        
        # Simple Helper function to wrap running basic check commands live
        def run_check_cmd(cmd_list):
            st.info(f"Running: `{' '.join(cmd_list)}`")
            p = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            out, _ = p.communicate()
            st.code(out if out.strip() else "Command completed with empty stdout.", language="bash")

        with col_u1:
            if st.button("📋 List Local Packages (`brane package list`)", key="cli_pkg_list_btn"):
                run_check_cmd(["brane", "package", "list"])
        with col_u2:
            if st.button("🌐 Show Current Connected Instance", key="cli_instance_btn"):
                run_check_cmd(["brane", "instance"])
        with col_u3:
            if st.button("📊 List Remote Datasets (`brane data list`)", key="cli_data_list_btn"):
                run_check_cmd(["brane", "data", "list"])

        st.divider()
        
        # Dynamic Markdown reference tables directly from documentation
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.markdown("""
            #### 📦 Package Commands
            | Command | Description |
            | :--- | :--- |
            | `brane package build <PATH>` | Build package from a `container.yml` |
            | `brane package list` | List local packages |
            | `brane package test <NAME>` | Test a package function locally |
            | `brane package push <NAME>` | Push a package to a remote instance |
            | `brane package search` | List packages on the remote instance |
            | `brane package remove <NAME>` | Remove a local package |
            """)
        with col_t2:
            st.markdown("""
            #### 📜 Workflow & Instance Commands
            | Command | Description |
            | :--- | :--- |
            | `brane workflow repl [--remote URL]` | Start interactive BraneScript REPL |
            | `brane workflow run <FILE> [--remote URL]` | Execute a workflow from a `.bs` file |
            | `brane login <URL> --username <NAME>` | Set the active instance |
            | `brane data download <NAME>` | Download a dataset locally |
            """)

    # ==========================================
    # TAB 3: ADMIN CLI COMMAND PANEL (`branectl`)
    # ==========================================
    with tab_admin_cli:
        st.subheader("🛠️ Node Infrastructure & Administrative Management Panel")
        st.write("Download node infrastructure service packages, generate certificates, secrets, and manage cluster statuses.")
        
        # Start / Stop Container Cluster Services Directly on the Host Engine
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
