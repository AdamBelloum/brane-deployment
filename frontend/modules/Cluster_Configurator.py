import os
import configparser
import shutil
import streamlit as st

# ===================================================================
# BULLETPROOF RE-ROUTING FOR THE MODULAR LAYOUT
# ===================================================================
#CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
#ANSIBLE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../docker-deployment"))
#INVENTORY_PATH = os.path.join(ANSIBLE_DIR, "inventories/production/hosts.ini")
#TEMPLATE_PATH = os.path.join(ANSIBLE_DIR, "inventories/production/hosts.ini.template")
from modules.config import INVENTORY_PATH, INVENTORY_TEMPLATE_PATH as TEMPLATE_PATH

def load_inventory():
    """Reads current host mappings safely from the filesystem."""
    config = configparser.ConfigParser(
        allow_no_value=True, 
        delimiters=(' ', '='),
        comment_prefixes=('#', ';'),  # <-- ADD THIS LINE HERE!
        inline_comment_prefixes=('#', ';')
    )
    config.optionxform = str
    if os.path.exists(INVENTORY_PATH):
        config.read(INVENTORY_PATH)
    return config


def save_inventory(config):
    """Saves inventory configuration changes back to hosts.ini."""
    with open(INVENTORY_PATH, 'w') as configfile:
        config.write(configfile, space_around_delimiters=True)


def render_cluster_config():
    """Isolated view module for the Cluster Topology management workspace."""
    st.title("Brane Cluster Topology Configurator")

    with st.expander(" Topology Management Guidelines", expanded=True):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("""
            **What it does:** Dynamically modifies your private Ansible infrastructure blueprint (`hosts.ini`). Allows adding, removing, or re-IPing active nodes on the fly.
            """)
        with col_b:
            st.markdown("""
            **Who is this for:** System Administrators and DevOps Engineers.
            **Prerequisites:** Modifying these targets requires running the infrastructure deployment playbooks afterward to apply configurations to the physical hosts.
            """)

    st.divider()

    # Automatically generate a private hosts.ini from template if missing
    if not os.path.exists(INVENTORY_PATH):
        if os.path.exists(TEMPLATE_PATH):
            shutil.copy(TEMPLATE_PATH, INVENTORY_PATH)
        else:
            # Emergency fallback if both files are missing
            with open(INVENTORY_PATH, 'w') as f:
                f.write("[central_hub]\n\n[worker_nodes]\n")

    # Initialize inventory session state tracking
    if 'inventory' not in st.session_state:
        st.session_state['inventory'] = load_inventory()

    config = st.session_state['inventory']
    sections = config.sections()

    # -------------------------------------------------------------------
    # VIEW CURRENT TOPOLOGY
    # -------------------------------------------------------------------
    st.subheader(" Current Active Inventory Map")
    if not sections:
        st.info("The hosts.ini inventory file is currently empty or unparsed.")
    else:
        for section in sections:
            st.markdown(f"#### **[{section}]**")
            items = config.items(section)
            if items:
                for host, value in items:
                    st.text(f"  └── {host} {value if value else ''}")
            else:
                st.caption("  *(No nodes assigned to this group)*")

    st.divider()
    
    # -------------------------------------------------------------------
    # MODIFY TOPOLOGY MANAGEMENT
    # -------------------------------------------------------------------
    st.subheader(" Topology Modifications Workspace")

    action_mode = st.radio(
        "Select Layout Operation:", 
        ["Add / Update Node", "Remove Node"], 
        horizontal=True,
        key="topology_action_mode"
    )

    if action_mode == "Add / Update Node":
        col_add1, col_add2, col_add3 = st.columns(3)
         
        with col_add1:
            fallback_groups = ["central_hub", "worker_nodes"]
            target_group = st.selectbox(
                "Target Node Group (Section):", 
                list(sections) + ["+ Create New Group"] if sections else fallback_groups,
                key="cfg_target_group"
            )
            if target_group == "+ Create New Group":
                target_group = st.text_input(
                    "Enter New Group Name:", 
                    value=st.session_state.get("cfg_custom_group", "new_group"),
                    key="cfg_custom_group"
                )
                 
        with col_add2:
            node_name = st.text_input(
                "Node Hostname Alias:", 
                value=st.session_state.get("cfg_node_name", "worker-vm-4"), 
                placeholder="e.g. worker-vm-x",
                key="cfg_node_name"
            )
             
        with col_add3:
            node_ip = st.text_input(
                "Target Node IP Address:", 
                value=st.session_state.get("cfg_node_ip", ""), 
                placeholder="e.g. 145.100.135.200",
                key="cfg_node_ip"
            )

        location_id = ""
        if target_group == "worker_nodes":
            location_id = st.text_input(
                "Assign Worker Location ID:", 
                value=st.session_state.get("cfg_location_id", "client-node-3"),
                key="cfg_location_id"
            )

        if st.button("Apply Node Rule Mapping", type="primary"):
            if not node_name or not node_ip:
                st.error("Hostname alias and target IP configurations cannot be empty parameters.")
            else:
                if not config.has_section(target_group):
                    config.add_section(target_group)
                  
                val_str = f"ansible_host={node_ip}"
                if location_id:
                    val_str += f" location_id={location_id}"
                      
                config.set(target_group, node_name, val_str)
                save_inventory(config)
                
                # Clear inventory from state so it reloads fresh on next render pass
                del st.session_state['inventory']
                st.success(f"✓ Configured `{node_name}` under group `[{target_group}]` safely inside `hosts.ini`!")
                st.rerun()

    elif action_mode == "Remove Node":
        col_rm1, col_rm2 = st.columns(2)
         
        with col_rm1:
            rm_group = st.selectbox(
                "Select Target Group:", 
                sections if sections else ["None"],
                key="cfg_rm_group"
            )
        with col_rm2:
            if rm_group != "None":
                hosts_in_group = [h for h, _ in config.items(rm_group)]
                rm_host = st.selectbox(
                    "Select Node Hostname to Purge:", 
                    hosts_in_group if hosts_in_group else ["None"],
                    key="cfg_rm_host"
                )
            else:
                rm_host = "None"
                  
        if st.button("Purge Selected Node Configuration", type="primary"):
            if rm_group != "None" and rm_host != "None":
                config.remove_option(rm_group, rm_host)
                  
                if not config.items(rm_group):
                    config.remove_section(rm_group)
                      
                save_inventory(config)
                
                # Clear state to force sync reload
                del st.session_state['inventory']
                st.success(f"Successfully removed `{rm_host}` from `hosts.ini` configuration limits.")
                st.rerun()
            else:
                st.error("Invalid node layout drop targets selected.")
