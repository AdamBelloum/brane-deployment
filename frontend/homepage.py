from modules.task_ui import render_activity_sidebar, render_task_history
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
from modules.user_dashboard import render_user_dashboard
from modules.policy_manager_dashboard import render_policy_manager_dashboard
from modules.admin_dashboard import render_admin_dashboard

# ===================================================================
# 🗺️ ROLE-ORIENTED NAVIGATION & ROUTING
# ===================================================================

PAGES = {
    "home": {
        "label": "Home",
        "role": None,
        "render": render_home_dashboard,
    },
    "admin_overview": {
        "label": "Admin overview",
        "role": "admin",
        "render": render_admin_dashboard,
    },
    "admin_infrastructure": {
        "label": "Infrastructure",
        "role": "admin",
        "render": render_infra_deploy,
    },
    "admin_cluster": {
        "label": "Cluster configuration",
        "role": "admin",
        "render": render_cluster_config,
    },
    "admin_packages": {
        "label": "Packages & registry",
        "role": "admin",
        "render": render_packages_deploy,
    },
    "admin_cli": {
        "label": "CLI & local tools",
        "role": "admin",
        "render": render_cli_panel,
    },
    "policy_overview": {
        "label": "Policy overview",
        "role": "policy_manager",
        "render": render_policy_manager_dashboard,
    },
    "user_overview": {
        "label": "User overview",
        "role": "user",
        "render": render_user_dashboard,
    },
    "user_workflows": {
        "label": "Workflow editor",
        "role": "user",
        "render": render_brane_scripts,
    },
    "task_history": {
        "label": "Task history",
        "role": None,
        "render": render_task_history,
    },
}

if "current_page" not in st.session_state:
    st.session_state.current_page = "home"

# Dashboard actions may request a navigation destination before rerunning.
requested_page = st.session_state.pop("requested_page", None)
if requested_page in PAGES:
    st.session_state.current_page = requested_page

if st.session_state.current_page not in PAGES:
    st.session_state.current_page = "home"

current_page = st.session_state.current_page
current_role = PAGES[current_page]["role"]
if current_role:
    st.session_state.current_role = current_role


def render_navigation_button(page_id: str) -> None:
    """Render one sidebar navigation action and preserve the selected page."""
    page = PAGES[page_id]
    selected = page_id == st.session_state.current_page
    label = f"● {page['label']}" if selected else page["label"]

    if st.button(
        label,
        key=f"nav_{page_id}",
        use_container_width=True,
        type="primary" if selected else "secondary",
    ):
        st.session_state.current_page = page_id
        st.rerun()


with st.sidebar:
    st.title("🧬 Brane Control Center")
    st.caption("Choose a workspace based on the task you need to perform.")

    render_navigation_button("home")

    with st.expander(
        "⚙️ Administration",
        expanded=current_page.startswith("admin_"),
    ):
        st.caption("Operate and maintain the Brane deployment.")
        for page_id in (
            "admin_overview",
            "admin_infrastructure",
            "admin_cluster",
            "admin_packages",
            "admin_cli",
        ):
            render_navigation_button(page_id)

    with st.expander(
        "🔐 Policy Management",
        expanded=current_page.startswith("policy_"),
    ):
        st.caption("Manage data-access policies and their lifecycle.")
        render_navigation_button("policy_overview")

    with st.expander(
        "👤 User Workspace",
        expanded=current_page.startswith("user_"),
    ):
        st.caption("Create, submit, and follow Brane workflows.")
        for page_id in ("user_overview", "user_workflows"):
            render_navigation_button(page_id)

    st.divider()
    render_navigation_button("task_history")
    st.divider()

# Active operations remain visible no matter which workspace is open.
render_activity_sidebar()

# Render the selected workspace.
PAGES[st.session_state.current_page]["render"]()


# ===================================================================
#  UNIVERSAL SIDEBAR FOOTER RESOURCE LINKS
# ===================================================================
with st.sidebar:
    st.markdown("### 🌐 Official Brane Resources")
    st.link_button("🏠 Official Website", "https://brane.software/")
    st.link_button("📚 Documentation", "https://docs.brane.software/")
    st.link_button("💻 GitHub Repository", "https://github.com/BraneFramework/brane")
    st.caption("Brane Distributed Framework System Dashboard v1.0.0")
