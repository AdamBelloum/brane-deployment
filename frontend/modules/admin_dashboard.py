# =============================================================
# admin_dashboard.py
# Version: 3.6.0
# Date: 2026-08-17
# Author: Brane Deployment Team
#
# Description:
#   Streamlit module for the Admin role dashboard.
#   Reorganized with clear categories:
#   1. Deployment Functions (healthcheck, deploy, test)
#   2. Manage Certificates & Tokens (download certs, create tokens)
#   3. Role Switching (test packages as user, test policies as policy manager)
#
# =============================================================

import os
import subprocess
import streamlit as st
import zipfile
import json
import re
import io
from typing import List, Dict, Tuple

from modules.config import (
    ANSIBLE_DIR,
    INVENTORY_PATH,
    PACKAGES_DIR,
    CERTS_DIR,
    POLICY_TOKENS_DIR,
    REPO_ROOT,
    list_packages,
    list_certs,
    list_policies,
)


# =============================================================
# HELPER FUNCTIONS
# =============================================================

def _run_command(cmd: List[str], timeout: int = 60, cwd: str = None) -> Tuple[bool, str]:
    """Run a command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=timeout,
            cwd=cwd
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def _clean_ansi_codes(text: str) -> str:
    """Remove ANSI color codes from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def _get_deployment_tags() -> Dict[str, str]:
    """Get mapping of deployment tag names to their descriptions."""
    return {
        "🔄 Full Deployment (All Tags)": "",
        "📋 Phase 0: Prerequisites": "prerequisites",
        "🔧 Phase 1: Install Branectl": "branectl",
        "👷 Phase 2: Configure Workers": "workers",
        "🎯 Phase 3: Configure Central": "central",
        "🔐 Phase 4: Exchange Certificates": "certs",
        "▶️ Phase 5: Start Services": "start",
        "✅ Phase 6: Run Smoke Tests": "smoke",
    }


def _get_worker_nodes() -> List[str]:
    """Get list of worker nodes from inventory."""
    try:
        result = subprocess.run(
            ["ansible", "workers", "-i", INVENTORY_PATH, 
             "-m", "debug", "-a", "msg={{ inventory_hostname }}", "--one-line"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        workers = []
        for line in result.stdout.split('\n'):
            if 'msg' in line:
                match = re.search(r'"msg":\s*"([^"]+)"', line)
                if match:
                    workers.append(match.group(1))
        return sorted(set(workers))
    except Exception:
        return []


def _get_instances() -> List[str]:
    """Get list of configured Brane instances."""
    try:
        result = subprocess.run(
            ["brane", "instance", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            instances = []
            for line in result.stdout.split('\n'):
                if line.strip() and not line.startswith('Name'):
                    parts = line.split()
                    if parts:
                        instances.append(parts[0])
            return instances
        return []
    except Exception:
        return []


def _create_certs_zip(domain: str) -> Tuple[bool, bytes, str]:
    """Create a ZIP file with all certificates for a domain."""
    try:
        domain_cert_dir = os.path.join(CERTS_DIR, domain)
        
        if not os.path.isdir(domain_cert_dir):
            return False, b"", f"Certificate directory not found: {domain_cert_dir}"
        
        # Create ZIP in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file in os.listdir(domain_cert_dir):
                file_path = os.path.join(domain_cert_dir, file)
                if os.path.isfile(file_path):
                    zip_file.write(file_path, arcname=file)
        
        zip_buffer.seek(0)
        return True, zip_buffer.getvalue(), f"certs_{domain}.zip"
    
    except Exception as e:
        return False, b"", str(e)


def _generate_policy_token(manager_name: str, domain_id: str, validity: str = "30d") -> Tuple[bool, str]:
    """Generate a policy expert token."""
    try:
        # Generate token using branectl
        cmd = [
            "branectl", "generate", "policy_token",
            manager_name, domain_id, validity
        ]
        success, output = _run_command(cmd, timeout=30)
        
        if success:
            # Try to parse the token from output
            try:
                token_data = json.loads(output)
                return True, json.dumps(token_data, indent=2)
            except:
                return True, output
        else:
            return False, output
    
    except Exception as e:
        return False, str(e)


# =============================================================
# SECTION 1: DEPLOYMENT FUNCTIONS
# =============================================================

def _render_deployment_functions() -> None:
    """Render deployment functions section."""
    st.subheader("🚀 Deployment Functions")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### 1️⃣ Health Check")
        if st.button("🏥 Run Health Check", key="btn_health_check"):
            with st.spinner("Running health check..."):
                try:
                    # Try multiple possible paths for the health check script
                    possible_paths = [
                        os.path.join(REPO_ROOT, "scripts", "brane_healthcheck.sh"),
                        os.path.join(REPO_ROOT, "brane_healthcheck.sh"),
                        "brane_healthcheck.sh",
                    ]
                    
                    script_path = None
                    for path in possible_paths:
                        if os.path.exists(path):
                            script_path = path
                            break
                    
                    if script_path:
                        # Run from ANSIBLE_DIR so relative paths work
                        success, output = _run_command(
                            ["bash", script_path], 
                            timeout=120, 
                            cwd=ANSIBLE_DIR
                        )
                        
                        # Clean ANSI codes for better display
                        clean_output = _clean_ansi_codes(output)
                        
                        if success:
                            st.success("✅ Health check completed")
                        else:
                            st.warning("⚠️ Health check completed with warnings")
                        st.code(clean_output, language="text")
                    else:
                        st.error("❌ Health check script not found")
                        st.info(f"Looked in:\n- {possible_paths[0]}\n- {possible_paths[1]}\n- {possible_paths[2]}")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    with col2:
        st.markdown("#### 2️⃣ Deploy Infrastructure")
        if st.button("🚀 Configure Deployment", key="btn_deploy_config"):
            st.session_state.show_deploy_config = True
    
    with col3:
        st.markdown("#### 3️⃣ Run Tests")
        if st.button("🧪 Run Smoke Tests", key="btn_smoke_tests"):
            with st.spinner("Running smoke tests..."):
                try:
                    # Verify inventory file exists
                    if not os.path.exists(INVENTORY_PATH):
                        st.error(f"❌ Inventory file not found: {INVENTORY_PATH}")
                        return
                    
                    playbook_path = os.path.join(ANSIBLE_DIR, "site.yml")
                    if not os.path.exists(playbook_path):
                        st.error(f"❌ Playbook not found: {playbook_path}")
                        return
                    
                    success, output = _run_command(
                        ["ansible-playbook", "-i", INVENTORY_PATH,
                         playbook_path, "--tags", "smoke"],
                        timeout=300,
                        cwd=ANSIBLE_DIR
                    )
                    
                    # Clean ANSI codes
                    clean_output = _clean_ansi_codes(output)
                    
                    if success:
                        st.success("✅ Smoke tests passed")
                    else:
                        st.error("❌ Smoke tests failed")
                    st.code(clean_output, language="text")
                except Exception as e:
                    st.error(f"Error: {e}")
    
    # Deployment configuration section
    if st.session_state.get("show_deploy_config", False):
        st.divider()
        st.markdown("### 🎯 Deployment Configuration")
        
        # Verify files exist first
        if not os.path.exists(INVENTORY_PATH):
            st.error(f"❌ Inventory file not found: {INVENTORY_PATH}")
            st.info("Please configure your inventory file first.")
            return
        
        playbook_path = os.path.join(ANSIBLE_DIR, "site.yml")
        if not os.path.exists(playbook_path):
            st.error(f"❌ Playbook not found: {playbook_path}")
            return
        
        st.info(f"**Inventory:** `{INVENTORY_PATH}`")
        st.info(f"**Playbook:** `{playbook_path}`")
        
        st.divider()
        
        # Deployment tag selection
        st.markdown("#### Select Deployment Phase(s)")
        
        tags_dict = _get_deployment_tags()
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            selected_phase = st.selectbox(
                "Choose deployment phase",
                list(tags_dict.keys()),
                key="deploy_phase_select"
            )
        
        with col2:
            st.write("")  # Spacer
            deploy_button = st.button("▶️ Start Deployment", key="btn_start_deploy", type="primary")
        
        if deploy_button:
            phase_tag = tags_dict[selected_phase]
            
            with st.spinner(f"Deploying: {selected_phase}..."):
                try:
                    # Build command
                    cmd = [
                        "ansible-playbook", "-i", INVENTORY_PATH,
                        playbook_path
                    ]
                    
                    # Add tags if not full deployment
                    if phase_tag:
                        cmd.extend(["--tags", phase_tag])
                    
                    # Run deployment
                    success, output = _run_command(cmd, timeout=3600, cwd=ANSIBLE_DIR)
                    
                    # Clean ANSI codes
                    clean_output = _clean_ansi_codes(output)
                    
                    if success:
                        st.success(f"✅ {selected_phase} completed successfully!")
                    else:
                        st.error(f"❌ {selected_phase} failed")
                    
                    st.code(clean_output, language="text")
                    
                except Exception as e:
                    st.error(f"Error: {e}")
        
        st.divider()
        
        # Additional options
        st.markdown("#### Advanced Options")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔍 Dry Run (Check Mode)", key="btn_dry_run"):
                with st.spinner("Running dry run..."):
                    try:
                        cmd = [
                            "ansible-playbook", "-i", INVENTORY_PATH,
                            playbook_path, "--check", "--diff"
                        ]
                        success, output = _run_command(cmd, timeout=300, cwd=ANSIBLE_DIR)
                        clean_output = _clean_ansi_codes(output)
                        
                        if success:
                            st.success("✅ Dry run completed")
                        else:
                            st.warning("⚠️ Dry run showed potential issues")
                        st.code(clean_output, language="text")
                    except Exception as e:
                        st.error(f"Error: {e}")
        
        with col2:
            if st.button("✓ Syntax Check", key="btn_syntax_check"):
                with st.spinner("Checking syntax..."):
                    try:
                        cmd = [
                            "ansible-playbook", "-i", INVENTORY_PATH,
                            playbook_path, "--syntax-check"
                        ]
                        success, output = _run_command(cmd, timeout=30, cwd=ANSIBLE_DIR)
                        clean_output = _clean_ansi_codes(output)
                        
                        if success:
                            st.success("✅ Syntax is valid")
                        else:
                            st.error("❌ Syntax error")
                        st.code(clean_output, language="text")
                    except Exception as e:
                        st.error(f"Error: {e}")
        
        with col3:
            if st.button("❌ Close Configuration", key="btn_close_deploy_config"):
                st.session_state.show_deploy_config = False
                st.rerun()


# =============================================================
# SECTION 2: MANAGE CERTIFICATES & TOKENS
# =============================================================

def _render_manage_certs_tokens() -> None:
    """Render certificate and token management section."""
    st.subheader("🔐 Manage Certificates & Tokens")
    
    tab1, tab2 = st.tabs(["📥 Download Certificates", "🔑 Create & Download Tokens"])
    
    with tab1:
        st.markdown("#### Download Domain Certificates")
        
        domains = list_certs()
        
        if not domains:
            st.warning("No certificate domains found in certs/")
            st.info(f"Looking in: `{CERTS_DIR}`")
            return
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            selected_domain = st.selectbox(
                "Select domain to download certificates",
                domains,
                key="domain_select_certs"
            )
        
        with col2:
            st.write("")  # Spacer
            if st.button("📥 Download ZIP", key="btn_download_certs", type="primary"):
                success, zip_data, filename = _create_certs_zip(selected_domain)
                
                if success:
                    st.success(f"✅ Certificates packaged: {filename}")
                    st.download_button(
                        label=f"⬇️ Download {filename}",
                        data=zip_data,
                        file_name=filename,
                        mime="application/zip",
                        key="download_certs_button"
                    )
                else:
                    st.error(f"❌ Error: {filename}")
        
        st.divider()
        
        st.markdown("#### Certificate Details")
        domain_cert_dir = os.path.join(CERTS_DIR, selected_domain)
        if os.path.isdir(domain_cert_dir):
            files = os.listdir(domain_cert_dir)
            st.info(f"**Domain:** {selected_domain}")
            st.info(f"**Files:** {', '.join(files)}")
            
            # Show file sizes
            for file in files:
                file_path = os.path.join(domain_cert_dir, file)
                if os.path.isfile(file_path):
                    size = os.path.getsize(file_path)
                    st.caption(f"  • {file} ({size} bytes)")
    
    with tab2:
        st.markdown("#### Generate Policy Expert Token")
        
        col1, col2 = st.columns(2)
        
        with col1:
            manager_name = st.text_input(
                "Policy manager name (e.g., alice)",
                key="token_manager_name"
            )
            domain_id = st.selectbox(
                "Domain ID (worker node)",
                _get_worker_nodes() or ["worker-1"],
                key="token_domain_id"
            )
        
        with col2:
            validity = st.text_input(
                "Validity period",
                value="30d",
                key="token_validity"
            )
            st.write("")  # Spacer
        
        if st.button("🔑 Generate Token", key="btn_gen_token", type="primary"):
            if manager_name and domain_id:
                with st.spinner("Generating token..."):
                    success, token_output = _generate_policy_token(manager_name, domain_id, validity)
                    
                    if success:
                        st.success(f"✅ Token generated for {manager_name}")
                        st.code(token_output, language="json")
                        
                        # Offer download
                        token_filename = f"policy_token_{manager_name}_{domain_id}.json"
                        st.download_button(
                            label=f"⬇️ Download {token_filename}",
                            data=token_output,
                            file_name=token_filename,
                            mime="application/json",
                            key="download_token_button"
                        )
                    else:
                        st.error(f"❌ Failed to generate token: {token_output}")
            else:
                st.error("Manager name and domain ID are required")


# =============================================================
# SECTION 3: ROLE SWITCHING & TESTING
# =============================================================

def _render_role_switching() -> None:
    """Render role switching section for testing."""
    st.subheader("🔄 Switch Roles for Testing")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### 👤 Test as User")
        st.markdown("""
        Switch to User role to:
        - Build packages
        - Run workflows
        - Test package execution
        """)
        if st.button("👤 Switch to User Dashboard", key="btn_switch_user", type="primary"):
            st.session_state.current_role = "user"
            st.rerun()
    
    with col2:
        st.markdown("#### 🔐 Test as Policy Manager")
        st.markdown("""
        Switch to Policy Manager role to:
        - Add policies to domains
        - Activate policy versions
        - Test policy enforcement
        """)
        if st.button("🔐 Switch to Policy Manager", key="btn_switch_policy", type="primary"):
            st.session_state.current_role = "policy_manager"
            st.rerun()
    
    with col3:
        st.markdown("#### ⚙️ Back to Admin")
        st.markdown("""
        You are currently in:
        **Admin Dashboard**
        
        Manage infrastructure and
        deployment operations
        """)


# =============================================================
# DEBUG SECTION
# =============================================================

def _render_debug_info() -> None:
    """Render debug information."""
    with st.expander("🔧 Debug Information"):
        st.markdown("#### Configuration Paths")
        st.code(f"""
REPO_ROOT:        {REPO_ROOT}
ANSIBLE_DIR:      {ANSIBLE_DIR}
INVENTORY_PATH:   {INVENTORY_PATH}
PACKAGES_DIR:     {PACKAGES_DIR}
CERTS_DIR:        {CERTS_DIR}
POLICIES_DIR:     {POLICY_TOKENS_DIR}

Inventory exists: {os.path.exists(INVENTORY_PATH)}
Ansible dir exists: {os.path.isdir(ANSIBLE_DIR)}
Packages dir exists: {os.path.isdir(PACKAGES_DIR)}
Certs dir exists: {os.path.isdir(CERTS_DIR)}

Health check script paths:
- {os.path.join(REPO_ROOT, 'scripts', 'brane_healthcheck.sh')} exists: {os.path.exists(os.path.join(REPO_ROOT, 'scripts', 'brane_healthcheck.sh'))}
- {os.path.join(REPO_ROOT, 'brane_healthcheck.sh')} exists: {os.path.exists(os.path.join(REPO_ROOT, 'brane_healthcheck.sh'))}
        """, language="text")


# =============================================================
# MAIN DASHBOARD FUNCTION
# =============================================================

def render_admin_dashboard() -> None:
    """
    Render the reorganized admin dashboard with clear categories.
    """
    st.title("⚙️ Admin Dashboard")
    st.markdown("Infrastructure management, deployment, and certificate/token operations")
    st.divider()
    
    # Main sections
    st.markdown("### 1. Deployment Functions")
    _render_deployment_functions()
    
    st.divider()
    
    st.markdown("### 2. Manage Certificates & Tokens")
    _render_manage_certs_tokens()
    
    st.divider()
    
    st.markdown("### 3. Role Switching & Testing")
    _render_role_switching()
    
    st.divider()
    
    # Debug info
    _render_debug_info()
    
    st.divider()
    
    # Quick reference
    with st.expander("📖 Admin Dashboard Guide"):
        st.markdown("""
        ## Admin Dashboard Overview
        
        ### 1. Deployment Functions
        - **Health Check** - Run infrastructure health checks
        - **Configure Deployment** - Select deployment phases and run
        - **Run Tests** - Execute smoke tests
        
        #### Deployment Phases
        - **Full Deployment** - Deploy all phases at once
        - **Phase 0: Prerequisites** - Install system dependencies
        - **Phase 1: Branectl** - Install Brane CLI tools
        - **Phase 2: Workers** - Configure worker nodes
        - **Phase 3: Central** - Configure central hub
        - **Phase 4: Certificates** - Exchange TLS certificates
        - **Phase 5: Start** - Start all services
        - **Phase 6: Smoke Tests** - Run integration tests
        
        ### 2. Manage Certificates & Tokens
        - **Download Certificates** - Select domain and download as ZIP
        - **Create & Download Tokens** - Generate policy expert tokens
        
        ### 3. Role Switching & Testing
        - **Switch to User** - Test packages and workflows
        - **Switch to Policy Manager** - Test policies
        """)


# =============================================================
# END OF FILE
# =============================================================
