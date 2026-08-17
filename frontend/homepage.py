# =============================================================
# homepage.py
# Version: 2.1.0
# Date: 2026-08-17
# Author: Brane Deployment Team
#
# Description:
#   Main entry point for the Brane Deployment Frontend 
#   application. Implements role-based navigation and environment 
#   snapshot display, following the brane_main.sh pattern.
#
# =============================================================

import sys
import os
import logging
import streamlit as st
from typing import Dict, List, Tuple

from modules.config import (
    get_central_ip,
    get_worker_ips,
    list_packages,
    list_certs,
    list_datasets,
    list_policies,
    list_policy_tokens,
)


# =============================================================
# LOGGER CONFIGURATION
# =============================================================

logger = logging.getLogger(__name__)


# =============================================================
# ENVIRONMENT SNAPSHOT
# =============================================================

class EnvironmentSnapshot:
    """Captures the current state of the Brane environment."""

    def __init__(self):
        """Initialize and build the environment snapshot."""
        self.inventory_ok = False
        self.central_host = ""
        self.worker_hosts = []
        self.packages = []
        self.certs = []
        self.datasets = []
        self.policies = []
        self.tokens = []
        self.user_type = "new"
        self.message = ""
        
        self._build_snapshot()

    def _build_snapshot(self) -> None:
        """
        Build the complete environment snapshot.
        
        Function Purpose:
            Collects all environment information including inventory,
            packages, certificates, datasets, policies, and tokens.
            Uses config.py helper functions for resource discovery.
        """
        # Inventory - use config.py helper functions
        self.central_host = get_central_ip() or ""
        self.worker_hosts = get_worker_ips()
        self.inventory_ok = bool(self.central_host or self.worker_hosts)
        
        logger.info(f"Inventory: ok={self.inventory_ok}, central={self.central_host}, workers={len(self.worker_hosts)}")

        # Resources - use config.py helper functions
        self.packages = list_packages()
        self.certs = list_certs()
        self.datasets = list_datasets()
        self.policies = list_policies()
        self.tokens = list_policy_tokens()

        logger.info(f"Resources: packages={len(self.packages)}, certs={len(self.certs)}, "
                   f"datasets={len(self.datasets)}, policies={len(self.policies)}, tokens={len(self.tokens)}")

        # Determine user type
        if self.inventory_ok and self.packages and self.certs:
            self.user_type = "ready"
        elif self.inventory_ok or self.packages or self.certs or self.datasets:
            self.user_type = "partial"
        else:
            self.user_type = "new"

        # Generate welcome message
        self._generate_message()

        logger.info(f"Snapshot built: user_type={self.user_type}")

    def _generate_message(self) -> None:
        """Generate state-dependent welcome message."""
        if self.user_type == "new":
            self.message = (
                "🎉 **Welcome!** It looks like this is a fresh environment.\n\n"
                "No packages, certificates, or inventory were found.\n\n"
                "**Getting started:**\n"
                "1. Select **Admin** role and configure your cluster\n"
                "2. Deploy infrastructure\n"
                "3. Verify with health checks"
            )
        elif self.user_type == "partial":
            self.message = (
                "👋 **Welcome back!** Your environment is partially configured.\n\n"
                "See the snapshot below — some items still need attention.\n\n"
                "**Next steps:**\n"
                "- Complete missing configuration items\n"
                "- Run health checks to verify deployment\n"
                "- Deploy test packages to verify functionality"
            )
        else:  # ready
            self.message = (
                "✅ **Welcome back!** Your environment looks ready.\n\n"
                "Infrastructure and local resources are configured.\n\n"
                "**You can now:**\n"
                "- Author and execute workflows\n"
                "- Deploy packages and run tests\n"
                "- Manage policies and access controls"
            )


# =============================================================
# PATH CONFIGURATION
# =============================================================

def _setup_import_paths() -> None:
    """Configure Python import paths for module discovery."""
    frontend_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(frontend_dir)
    
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
        logger.debug(f"Added to sys.path: {parent_dir}")


# =============================================================
# MODULE IMPORTS
# =============================================================

def _import_modules() -> Dict[str, Dict]:
    """Import all role-specific modules."""
    modules = {
        "user": {
            "label": "User",
            "description": "Run workflows, manage packages and certificates",
            "icon": "👤",
            "pages": [],
        },
        "admin": {
            "label": "Admin",
            "description": "Deploy and manage the Brane infrastructure",
            "icon": "⚙️",
            "pages": [],
        },
        "policy_manager": {
            "label": "Policy Manager",
            "description": "Add and activate domain policies",
            "icon": "🔐",
            "pages": [],
        },
    }

    # Import user role modules
    try:
        from frontend.modules.user_dashboard import render_user_dashboard
        modules["user"]["pages"].append(("Dashboard", render_user_dashboard))
        logger.debug("Loaded: user role modules")
    except ImportError as e:
        logger.error(f"Failed to import user modules: {e}")

    # Import admin role modules
    try:
        from frontend.modules.admin_dashboard import render_admin_dashboard
        modules["admin"]["pages"].append(("Dashboard", render_admin_dashboard))
        logger.debug("Loaded: admin role modules")
    except ImportError as e:
        logger.error(f"Failed to import admin modules: {e}")

    # Import policy manager role modules
    try:
        from frontend.modules.policy_manager_dashboard import render_policy_manager_dashboard
        modules["policy_manager"]["pages"].append(("Dashboard", render_policy_manager_dashboard))
        logger.debug("Loaded: policy_manager role modules")
    except ImportError as e:
        logger.error(f"Failed to import policy_manager modules: {e}")

    return modules


# =============================================================
# SESSION STATE INITIALIZATION
# =============================================================

def _initialize_session_state() -> None:
    """Initialize all global session state variables."""
    if "current_role" not in st.session_state:
        st.session_state.current_role = None
        logger.debug("Initialized: current_role")

    if "snapshot" not in st.session_state:
        st.session_state.snapshot = EnvironmentSnapshot()
        logger.debug("Initialized: snapshot")

    # Background operation states
    for op in ["pkg", "infra", "script", "policy"]:
        if f"global_{op}_status" not in st.session_state:
            st.session_state[f"global_{op}_status"] = "idle"
        if f"global_{op}_logs" not in st.session_state:
            st.session_state[f"global_{op}_logs"] = []


# =============================================================
# UI RENDERING
# =============================================================

def _render_welcome_screen(snapshot: EnvironmentSnapshot) -> None:
    """Render the welcome screen with environment snapshot."""
    st.title("🌐 Brane Distributed Framework Console")
    st.markdown("Research Infrastructure Helper v2.1.0")
    st.divider()

    # Welcome message
    st.info(snapshot.message)

    st.divider()

    # Environment snapshot
    st.subheader("📊 Infrastructure Snapshot")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🖥️ Inventory")
        if snapshot.inventory_ok:
            if snapshot.central_host:
                st.success(f"✅ Central: `{snapshot.central_host}`")
            if snapshot.worker_hosts:
                st.success(f"✅ Workers: {len(snapshot.worker_hosts)} node(s)")
                for w in snapshot.worker_hosts:
                    st.caption(f"  • {w}")
            if not snapshot.central_host and not snapshot.worker_hosts:
                st.warning("⚠️ Inventory file found but no nodes configured")
        else:
            st.error("❌ Inventory not found")

    with col2:
        st.markdown("#### 📦 Local Resources")
        
        # Packages
        if snapshot.packages:
            st.success(f"✅ Packages: {len(snapshot.packages)}")
            for p in snapshot.packages:
                st.caption(f"  • {p}")
        else:
            st.warning("⚠️ No packages found")

        # Certificates
        if snapshot.certs:
            st.success(f"✅ Certificates: {len(snapshot.certs)}")
            for c in snapshot.certs:
                st.caption(f"  • {c}")
        else:
            st.warning("⚠️ No certificates found")

        # Datasets
        if snapshot.datasets:
            st.success(f"✅ Datasets: {len(snapshot.datasets)}")
            for d in snapshot.datasets:
                st.caption(f"  • {d}")
        else:
            st.info("ℹ️ No datasets found")

        # Policies
        if snapshot.policies:
            st.success(f"✅ Policies: {len(snapshot.policies)}")
            for p in snapshot.policies:
                st.caption(f"  • {p}")
        else:
            st.info("ℹ️ No policies found")

        # Tokens
        if snapshot.tokens:
            st.success(f"✅ Tokens: {len(snapshot.tokens)}")
            for t in snapshot.tokens:
                st.caption(f"  • {t}")
        else:
            st.info("ℹ️ No tokens found")


def _render_role_menu(modules: Dict[str, Dict]) -> str:
    """Render role selection menu and return selected role."""
    st.divider()
    st.subheader("👥 Select Your Role")

    cols = st.columns(3)

    selected_role = None

    for idx, (role_key, role_info) in enumerate(modules.items()):
        with cols[idx]:
            if st.button(
                f"{role_info['icon']} {role_info['label']}",
                use_container_width=True,
                key=f"role_{role_key}",
            ):
                selected_role = role_key

            st.caption(role_info["description"])

    return selected_role


def _render_role_dashboard(role: str, modules: Dict[str, Dict]) -> None:
    """Render the selected role's dashboard."""
    role_info = modules[role]
    pages = role_info["pages"]

    st.title(f"{role_info['icon']} {role_info['label']} Dashboard")
    st.divider()

    if not pages:
        st.error(f"No modules available for {role_info['label']} role")
        return

    # Render selected page (only one page per role now)
    for page_name, page_renderer in pages:
        try:
            page_renderer()
        except Exception as e:
            st.error(f"Error rendering page: {str(e)}")
            logger.error(f"Page rendering error: {str(e)}", exc_info=True)
        break

    # Back button
    st.sidebar.divider()
    if st.sidebar.button("← Back to Role Selection"):
        st.session_state.current_role = None
        st.rerun()


# =============================================================
# STREAMLIT PAGE CONFIGURATION
# =============================================================

def _configure_streamlit_page() -> None:
    """Configure Streamlit page settings and appearance."""
    st.set_page_config(
        page_title="Brane Deployment Frontend",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    logger.debug("Streamlit page configuration applied")


# =============================================================
# MAIN APPLICATION CONTROLLER
# =============================================================

def main() -> None:
    """Main application entry point and controller."""
    # Initialization
    _configure_streamlit_page()
    _setup_import_paths()
    _initialize_session_state()

    # Import modules
    modules = _import_modules()

    if not any(m["pages"] for m in modules.values()):
        st.error("❌ Failed to load any modules.")
        logger.error("No modules could be imported")
        return

    # Get snapshot
    snapshot = st.session_state.snapshot

    # Role-based routing
    if st.session_state.current_role is None:
        # Show welcome and role selection
        _render_welcome_screen(snapshot)
        selected_role = _render_role_menu(modules)

        if selected_role:
            st.session_state.current_role = selected_role
            st.rerun()
    else:
        # Show role dashboard
        _render_role_dashboard(st.session_state.current_role, modules)


# =============================================================
# APPLICATION ENTRY POINT
# =============================================================

if __name__ == "__main__":
    main()


# =============================================================
# END OF FILE
# =============================================================
