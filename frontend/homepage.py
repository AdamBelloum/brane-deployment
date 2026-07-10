import streamlit as st

# ===================================================================
# 🌐 INITIALIZATION & SETUP
# ===================================================================
st.set_page_config(page_title="Brane Hub Console", page_icon="🌐", layout="wide")

# Persistent Global Variables for Async Deployments across all pages
if "global_pkg_status" not in st.session_state:
    st.session_state.global_pkg_status = "idle"
if "global_pkg_logs" not in st.session_state:
    st.session_state.global_pkg_logs = []
    
if "global_infra_status" not in st.session_state:
    st.session_state.global_infra_status = "idle"
if "global_infra_logs" not in st.session_state:
    st.session_state.global_infra_logs = []

# ===================================================================
# 📦 LAZY LAUNCH MODULE IMPORTS
# ===================================================================
from modules.home import render_home_dashboard
from modules.Deploy_Infrastructure import render_infra_deploy
from modules.Deploy_Packages import render_packages_deploy
from modules.Cluster_Configurator import render_cluster_config
from modules.Editor_Brane_Scripts import render_brane_scripts
from modules.Editor_Data_Policy import render_data_policy
from modules.Deploy_cli import render_cli_panel
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
# 📑 UNIVERSAL SIDEBAR FOOTER RESOURCE LINKS
# ===================================================================
with st.sidebar:
    st.markdown("### 🌐 Official Brane Resources")
    st.link_button("🏠 Official Website", "https://brane.software/")
    st.link_button("📚 Documentation", "https://docs.brane.software/")
    st.link_button("💻 GitHub Repository", "https://github.com/BraneFramework/brane")
    st.caption("Brane Distributed Framework System Dashboard v1.0.0")
