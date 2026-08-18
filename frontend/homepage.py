import streamlit as st

# ===================================================================
# 🔧 INITIALIZE SESSION STATE
# ===================================================================

# Role & Configuration
if "current_role" not in st.session_state:
    st.session_state.current_role = "user"

# Infrastructure Deployment
if "global_infra_status" not in st.session_state:
    st.session_state.global_infra_status = "idle"

if "global_infra_logs" not in st.session_state:
    st.session_state.global_infra_logs = []

if "global_infra_proc" not in st.session_state:
    st.session_state.global_infra_proc = None

# Package Deployment
if "global_pkg_status" not in st.session_state:
    st.session_state.global_pkg_status = "idle"

# Script Execution
if "global_script_status" not in st.session_state:
    st.session_state.global_script_status = "idle"

if "global_script_logs" not in st.session_state:
    st.session_state.global_script_logs = []

if "script_log_queue" not in st.session_state:
    st.session_state.script_log_queue = []

# Policy Management
if "global_policy_status" not in st.session_state:
    st.session_state.global_policy_status = "idle"

if "global_policy_logs" not in st.session_state:
    st.session_state.global_policy_logs = []

if "policy_log_queue" not in st.session_state:
    st.session_state.policy_log_queue = []

# Configuration Editor
if "cfg_script_name" not in st.session_state:
    st.session_state.cfg_script_name = ""

if "cfg_workflow_code" not in st.session_state:
    st.session_state.cfg_workflow_code = ""

if "cfg_policy_filename" not in st.session_state:
    st.session_state.cfg_policy_filename = ""

if "cfg_policy_code" not in st.session_state:
    st.session_state.cfg_policy_code = ""

if "cfg_policy_node" not in st.session_state:
    st.session_state.cfg_policy_node = ""

if "cfg_policy_token" not in st.session_state:
    st.session_state.cfg_policy_token = ""

# UI State
if "show_deploy_config" not in st.session_state:
    st.session_state.show_deploy_config = False

# ===================================================================
# 📦 IMPORTS
# ===================================================================
from modules.home import render_home_dashboard
from modules.Cluster_Configurator import render_cluster_config
from modules.Deploy_Infrastructure import render_infra_deploy
from modules.Deploy_Packages import render_packages_deploy
from modules.Deploy_cli import render_cli_panel
from modules.Editor_Brane_Scripts import render_brane_scripts
from modules.Editor_Data_Policy import render_data_policy

# ===================================================================
# 🗺️ CONTROLLER NAVIGATION & ROUTING
# ===================================================================
st.sidebar.title("🧬 Brane Control Center")

page_selection = st.sidebar.radio(
    "Navigation Menus",
    [
        "Dashboard Home", 
        "Cluster Configurator", 
        "Deploy Infrastructure", 
        "Deploy Packages",
        "Deploy Brane CLI",
        "Editor Brane Scripts",
        "Editor Data Policy"
    ]
)

st.sidebar.divider()

# Render Global Active Indicator Badges in the Sidebar
if st.session_state.global_pkg_status == "running" or st.session_state.global_infra_status == "running":
    st.sidebar.warning("⚡ Background Deployment Active...")

# Route the UI Content based on Sidebar Selection
if page_selection == "Dashboard Home":
    render_home_dashboard()
elif page_selection == "Cluster Configurator":
    render_cluster_config()
elif page_selection == "Deploy Infrastructure":
    render_infra_deploy()
elif page_selection == "Deploy Packages":
    render_packages_deploy()
elif page_selection == "Deploy Brane CLI":
    render_cli_panel()
elif page_selection == "Editor Brane Scripts":
    render_brane_scripts()
elif page_selection == "Editor Data Policy":
    render_data_policy()


# ===================================================================
#  UNIVERSAL SIDEBAR FOOTER RESOURCE LINKS
# ===================================================================
with st.sidebar:
    st.markdown("### 🌐 Official Brane Resources")
    st.link_button("🏠 Official Website", "https://brane.software/")
    st.link_button("📚 Documentation", "https://docs.brane.software/")
    st.link_button("💻 GitHub Repository", "https://github.com/BraneFramework/brane")
    st.caption("Brane Distributed Framework System Dashboard v1.0.0")
