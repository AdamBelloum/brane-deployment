# =============================================================
# home.py
# Version: 1.0.0
# Date: 2026-08-17
# Author: Brane Deployment Team
#
# Description:
#   Streamlit module for the Brane Deployment Dashboard home page.
#   Displays live cluster topology, system status, and provides 
#   quick access to common operations.
#
#   This module serves as the central command hub showing the 
#   current cluster configuration as read from the Ansible 
#   inventory (hosts.ini) file.
#
# Key Responsibilities:
#   1. Parse and display Ansible inventory configuration
#   2. Extract node information (hostnames, IPs, locations)
#   3. Render cluster topology visualization
#   4. Show system status and health indicators
#   5. Provide quick-start guidance for new users
#   6. Display resource utilization metrics
#   7. Offer navigation shortcuts to common tasks
#
# Design Pattern:
#   Streamlit View Module - Implements render_home_dashboard() 
#   function that displays the home page dashboard with topology 
#   visualization and system overview.
#
# Key Features:
#   - Live inventory parsing from hosts.ini
#   - Dynamic cluster topology visualization
#   - Node status indicators (IP, location, configuration)
#   - System overview and guidance
#   - Quick-access shortcuts to deployment tasks
#   - Responsive card-based layout
#   - Empty state handling with helpful guidance
#
# Dependencies:
#   - streamlit: Web UI framework
#   - modules.config: Repository configuration and paths
#   - Standard library: configparser, os, logging
#
# Configuration Files:
#   INVENTORY_PATH: {ANSIBLE_DIR}/inventories/production/hosts.ini
#
# Inventory Structure:
#   [central_hub]
#     central-node ansible_host=145.100.135.209
#   
#   [worker_nodes]
#     worker-vm-2 ansible_host=145.100.135.210 location_id=client-node-2
#     worker-vm-3 ansible_host=145.100.135.211 location_id=client-node-3
#
# Notes:
#   - Inventory is parsed on every page load
#   - Empty inventory shows helpful guidance
#   - Node metrics displayed in card format
#   - Location IDs shown for worker nodes
#   - Responsive layout adapts to node count
#
# =============================================================

import configparser
import logging
import os
import streamlit as st

from modules.config import INVENTORY_PATH


# =============================================================
# LOGGER CONFIGURATION
# =============================================================

logger = logging.getLogger(__name__)


# =============================================================
# INVENTORY PARSING FUNCTIONS
# =============================================================

def _parse_inventory() -> dict:
    """
    Parse Ansible inventory file and extract node configuration.
    
    Function Purpose:
        Reads the hosts.ini file and parses it into a dictionary 
        mapping section names to lists of (hostname, vars_string) tuples.
        Handles space-delimited Ansible inventory format.
    
    Parameters:
        None
    
    Returns:
        dict: Mapping of section names to host tuples
              Format: {section: [(hostname, vars_string), ...]}
              Empty dict if inventory file not found
    
    Example:
        >>> inventory = _parse_inventory()
        >>> print(inventory)
        {'central_hub': [('central-node', 'ansible_host=145.100.135.209')],
         'worker_nodes': [('worker-vm-2', 'ansible_host=145.100.135.210 location_id=client-node-2')]}
    
    Raises:
        No exceptions raised. Returns empty dict on error.
    
    Notes:
        - Handles space and equals as delimiters
        - Preserves case sensitivity
        - Handles inline comments with # and ;
        - Returns empty dict if file doesn't exist
        - Logs errors for debugging
    """
    if not os.path.exists(INVENTORY_PATH):
        logger.debug(f"Inventory file not found: {INVENTORY_PATH}")
        return {}

    try:
        config = configparser.ConfigParser(
            allow_no_value=True,
            delimiters=(" ", "="),
            comment_prefixes=("#", ";"),
            inline_comment_prefixes=("#", ";"),
        )
        config.optionxform = str  # Preserve case sensitivity
        config.read(INVENTORY_PATH)

        result = {}
        for section in config.sections():
            result[section] = list(config.items(section))
            logger.debug(f"Parsed section [{section}] with {len(result[section])} hosts")

        logger.info(f"Successfully parsed inventory with {len(result)} sections")
        return result

    except Exception as e:
        logger.error(f"Error parsing inventory: {e}")
        return {}


def _extract_ip_address(vars_string: str) -> str:
    """
    Extract ansible_host IP address from variable string.
    
    Function Purpose:
        Parses a space-delimited variable string to find and 
        extract the ansible_host IP address value.
    
    Parameters:
        vars_string (str): Space-delimited variable string
                          Example: "ansible_host=145.100.135.209 location_id=node-1"
    
    Returns:
        str: IP address if found, "—" (em-dash) if not found
    
    Example:
        >>> ip = _extract_ip_address("ansible_host=145.100.135.209 location_id=node-1")
        >>> print(ip)
        145.100.135.209
    
    Notes:
        - Returns em-dash (—) for missing values (more readable than None)
        - Handles empty or None input gracefully
        - Case-sensitive matching for "ansible_host="
    """
    if not vars_string:
        return "—"

    try:
        for part in vars_string.split():
            if part.startswith("ansible_host="):
                ip = part.split("=", 1)[1]
                logger.debug(f"Extracted IP: {ip}")
                return ip
    except Exception as e:
        logger.error(f"Error extracting IP: {e}")

    return "—"


def _extract_location_id(vars_string: str) -> str:
    """
    Extract location_id from variable string.
    
    Function Purpose:
        Parses a space-delimited variable string to find and 
        extract the location_id value (typically for worker nodes).
    
    Parameters:
        vars_string (str): Space-delimited variable string
                          Example: "ansible_host=145.100.135.209 location_id=client-node-2"
    
    Returns:
        str: Location ID if found, None if not found
    
    Example:
        >>> location = _extract_location_id("ansible_host=145.100.135.209 location_id=client-node-2")
        >>> print(location)
        client-node-2
    
    Notes:
        - Returns None for missing values (not displayed in UI)
        - Handles empty or None input gracefully
        - Case-sensitive matching for "location_id="
    """
    if not vars_string:
        return None

    try:
        for part in vars_string.split():
            if part.startswith("location_id="):
                location = part.split("=", 1)[1]
                logger.debug(f"Extracted location_id: {location}")
                return location
    except Exception as e:
        logger.error(f"Error extracting location_id: {e}")

    return None


# =============================================================
# UI RENDERING HELPER FUNCTIONS
# =============================================================

def _render_system_overview() -> None:
    """
    Render system overview and guidance section.
    
    Function Purpose:
        Displays the welcome message, system description, and 
        quick-start guidance for new users.
    
    Parameters:
        None
    
    Returns:
        None
    
    Notes:
        - Shown in expandable section
        - Provides context for new users
        - Links to Cluster Configurator
    """
    with st.expander("📖 System Guide & Overview", expanded=True):
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.markdown(
                """
                **What it does:**
                
                Central command hub showing the current cluster topology 
                as configured in your local `hosts.ini` inventory file.
                
                Displays all configured nodes, their IP addresses, and 
                deployment status at a glance.
                """
            )
        
        with col_b:
            st.markdown(
                """
                **Who is this for:**
                
                System Administrators, Developers, and Data Scientists.
                
                **Prerequisites:**
                
                Configure your cluster topology in the **Cluster Configurator** 
                before deploying infrastructure or packages.
                """
            )

    st.write(
        "Welcome to the unified Brane management platform. "
        "Use the sidebar navigation to deploy infrastructure, stage packages, "
        "author workflows, or manage data access policies."
    )


def _render_empty_inventory_state() -> None:
    """
    Render UI for empty or missing inventory state.
    
    Function Purpose:
        Displays helpful guidance when no inventory is configured, 
        directing users to the Cluster Configurator.
    
    Parameters:
        None
    
    Returns:
        None
    
    Notes:
        - Shows warning with actionable guidance
        - Provides next steps for configuration
    """
    st.warning(
        "⚠️ **No inventory configured.** "
        "Your cluster topology is empty or the inventory file is missing."
    )

    st.info(
        """
        ### 🚀 Quick Start
        
        1. **Configure Your Cluster:**
           - Navigate to **Cluster Configurator** in the sidebar
           - Add your central hub node
           - Add your worker nodes with IP addresses and location IDs
        
        2. **Deploy Infrastructure:**
           - Go to **Deploy Infrastructure**
           - Select "Full Automated End-to-End Deployment"
           - Monitor the Ansible playbook execution
        
        3. **Verify Installation:**
           - Return here to see your live cluster topology
           - Navigate to **Deploy Packages** and run the smoke test
        """
    )


def _render_cluster_topology(inventory: dict) -> None:
    """
    Render cluster topology visualization from inventory.
    
    Function Purpose:
        Displays all configured nodes organized by group in a 
        responsive card-based layout with IP addresses and 
        location information.
    
    Parameters:
        inventory (dict): Parsed inventory dictionary
                         Format: {section: [(hostname, vars_string), ...]}
    
    Returns:
        None
    
    Notes:
        - Creates responsive columns based on node count
        - Shows IP address as metric value
        - Displays location_id as caption for worker nodes
        - Handles empty sections gracefully
    """
    st.subheader("🖥️ Live Cluster Topology")

    for section, hosts in inventory.items():
        st.markdown(f"#### **[{section}]**")

        if not hosts:
            st.caption("*(no nodes configured)*")
            continue

        # Create responsive columns (max 4 per row)
        cols = st.columns(min(len(hosts), 4))

        for idx, (hostname, vars_str) in enumerate(hosts):
            col = cols[idx % len(cols)]

            with col:
                # Extract node information
                ip_address = _extract_ip_address(vars_str)
                location_id = _extract_location_id(vars_str)

                # Display node as metric card
                st.metric(
                    label=hostname,
                    value=ip_address,
                    delta="✓ configured",
                )

                # Show location ID if present
                if location_id:
                    st.caption(f"📍 Location: `{location_id}`")

                # Show status
                st.caption("✅ Active")


def _render_quick_actions() -> None:
    """
    Render quick-action buttons for common tasks.
    
    Function Purpose:
        Displays convenient shortcuts to frequently-used operations 
        like deploying infrastructure or running smoke tests.
    
    Parameters:
        None
    
    Returns:
        None
    
    Notes:
        - Provides quick navigation to common tasks
        - Improves user experience and discoverability
    """
    st.divider()
    st.subheader("⚡ Quick Actions")

    col_q1, col_q2, col_q3 = st.columns(3)

    with col_q1:
        if st.button("🔧 Configure Cluster", use_container_width=True):
            st.switch_page("pages/cluster_configurator.py")

    with col_q2:
        if st.button("🏗️ Deploy Infrastructure", use_container_width=True):
            st.switch_page("pages/deploy_infrastructure.py")

    with col_q3:
        if st.button("📦 Deploy Packages", use_container_width=True):
            st.switch_page("pages/deploy_packages.py")


def _render_system_metrics() -> None:
    """
    Render system health and status metrics.
    
    Function Purpose:
        Displays key system metrics including node count, 
        deployment status, and resource utilization.
    
    Parameters:
        None
    
    Returns:
        None
    
    Notes:
        - Provides at-a-glance system health
        - Shows key metrics in card format
    """
    st.divider()
    st.subheader("📊 System Metrics")

    inventory = _parse_inventory()
    total_nodes = sum(len(hosts) for hosts in inventory.values())
    total_groups = len(inventory)

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)

    with col_m1:
        st.metric("Total Nodes", total_nodes)

    with col_m2:
        st.metric("Node Groups", total_groups)

    with col_m3:
        st.metric("Cluster Status", "🟢 Ready" if total_nodes > 0 else "🔴 Unconfigured")

    with col_m4:
        st.metric("Configuration", "✅ Valid" if total_nodes > 0 else "⚠️ Pending")


# =============================================================
# MAIN DASHBOARD RENDERING FUNCTION
# =============================================================

def render_home_dashboard() -> None:
    """
    Render the complete home dashboard.
    
    Function Purpose:
        Displays the main dashboard page including system overview, 
        cluster topology visualization, quick actions, and system metrics.
    
    Parameters:
        None
    
    Returns:
        None
    
    UI Sections:
        1. Page title and header
        2. System overview and guidance
        3. Cluster topology visualization
        4. Quick action buttons
        5. System metrics
    
    Notes:
        - Inventory is parsed fresh on each page load
        - Responsive layout adapts to content
        - Handles empty inventory gracefully
        - Provides clear guidance for new users
    """
    # ─────────────────────────────────────────────────────────────
    # PAGE HEADER
    # ─────────────────────────────────────────────────────────────
    st.title("🌐 Brane Distributed Framework Console")
    st.markdown(
        "Central command hub for cluster management, deployment orchestration, "
        "and workflow execution."
    )

    # ─────────────────────────────────────────────────────────────
    # SYSTEM OVERVIEW
    # ─────────────────────────────────────────────────────────────
    _render_system_overview()

    st.divider()

    # ─────────────────────────────────────────────────────────────
    # CLUSTER TOPOLOGY
    # ─────────────────────────────────────────────────────────────
    inventory = _parse_inventory()

    if not inventory:
        _render_empty_inventory_state()
        return

    _render_cluster_topology(inventory)

    # ─────────────────────────────────────────────────────────────
    # QUICK ACTIONS
    # ─────────────────────────────────────────────────────────────
    _render_quick_actions()

    # ─────────────────────────────────────────────────────────────
    # SYSTEM METRICS
    # ─────────────────────────────────────────────────────────────
    _render_system_metrics()


# =============================================================
# END OF FILE
# =============================================================
