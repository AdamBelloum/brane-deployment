# =============================================================
# Cluster_Configurator.py
# Infrastructure inventory management
# =============================================================

import configparser
import io
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List

import streamlit as st

from modules.config import INVENTORY_PATH, INVENTORY_TEMPLATE_PATH as TEMPLATE_PATH


SPECIAL_GROUP_SUFFIXES = (":vars", ":children")
ROLE_LABELS = {
    "central": "Central controller",
    "workers": "Worker domain",
    "proxies": "Proxy node",
}


def load_inventory() -> configparser.ConfigParser:
    """Read the active Ansible inventory while preserving host-variable values."""
    config = configparser.ConfigParser(
        allow_no_value=True,
        delimiters=(" ", "="),
        comment_prefixes=("#", ";"),
        inline_comment_prefixes=("#", ";"),
    )
    config.optionxform = str

    if os.path.exists(INVENTORY_PATH):
        config.read(INVENTORY_PATH)

    return config


def save_inventory(config: configparser.ConfigParser) -> None:
    """Atomically persist the edited inventory."""
    inventory_path = Path(INVENTORY_PATH)
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = inventory_path.with_suffix(".ini.tmp")

    with temporary_path.open("w", encoding="utf-8") as config_file:
        config.write(config_file, space_around_delimiters=True)

    temporary_path.replace(inventory_path)


def _ensure_inventory_exists() -> None:
    """Create the active inventory from its template when required."""
    inventory_path = Path(INVENTORY_PATH)
    template_path = Path(TEMPLATE_PATH)

    if inventory_path.exists():
        return

    inventory_path.parent.mkdir(parents=True, exist_ok=True)

    if template_path.exists():
        shutil.copy(template_path, inventory_path)
    else:
        inventory_path.write_text("[central]\n\n[workers]\n", encoding="utf-8")


def _parse_host_variables(value: str | None) -> Dict[str, str]:
    """Extract Ansible host variables from one inventory host entry."""
    if not value:
        return {}

    return dict(re.findall(r"([A-Za-z_][A-Za-z0-9_-]*)=([^ \t]+)", value))


def _editable_groups(config: configparser.ConfigParser) -> List[str]:
    """Return normal host groups, excluding Ansible vars and children groups."""
    return sorted(
        section
        for section in config.sections()
        if not section.endswith(SPECIAL_GROUP_SUFFIXES)
    )


def _topology_rows(config: configparser.ConfigParser) -> List[Dict[str, str]]:
    """Convert inventory host entries into administrator-facing topology rows."""
    rows: List[Dict[str, str]] = []

    for group in _editable_groups(config):
        for hostname, value in config.items(group):
            variables = _parse_host_variables(value)
            rows.append(
                {
                    "Role": ROLE_LABELS.get(group, group.replace("_", " ").title()),
                    "Node name": hostname,
                    "Address": variables.get("ansible_host", "—"),
                    "Brane domain ID": variables.get("location_id", "—"),
                }
            )

    return sorted(rows, key=lambda row: (row["Role"], row["Node name"]))


def _inventory_text(config: configparser.ConfigParser) -> str:
    """Render the current parsed inventory only for advanced diagnostics."""
    buffer = io.StringIO()
    config.write(buffer, space_around_delimiters=True)
    return buffer.getvalue().strip()


def _reset_inventory_state() -> None:
    """Force a clean inventory reload after a successful change."""
    st.session_state.pop("inventory", None)


def _render_topology_summary(rows: List[Dict[str, str]]) -> None:
    """Render compact deployment metrics and the node topology table."""
    controllers = sum(row["Role"] == "Central controller" for row in rows)
    worker_domains = sum(row["Role"] == "Worker domain" for row in rows)

    controller_col, worker_col, node_col = st.columns(3)
    with controller_col:
        st.metric("Controllers", controllers)
    with worker_col:
        st.metric("Worker domains", worker_domains)
    with node_col:
        st.metric("Configured nodes", len(rows))

    st.markdown("### Deployment topology")

    if not rows:
        st.info(
            "No deployment nodes are configured yet. Add a central controller "
            "or worker domain below."
        )
        return

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Role": st.column_config.TextColumn("Role", width="medium"),
            "Node name": st.column_config.TextColumn("Node name", width="medium"),
            "Address": st.column_config.TextColumn("Address", width="medium"),
            "Brane domain ID": st.column_config.TextColumn(
                "Brane domain ID",
                width="medium",
            ),
        },
    )


def _render_add_or_update(config: configparser.ConfigParser) -> None:
    """Render the normal inventory editing flow."""
    st.markdown("#### Add or update node")
    st.caption(
        "A worker domain needs a unique Brane domain ID, for example "
        "`client-node-2`."
    )

    role_options = {
        "Central controller": "central",
        "Worker domain": "workers",
        "Proxy node": "proxies",
        "Other inventory group": "",
    }

    with st.form("inventory_add_or_update"):
        selected_role = st.selectbox(
            "Deployment role",
            list(role_options.keys()),
            key="inventory_role",
        )

        target_group = role_options[selected_role]
        if selected_role == "Other inventory group":
            target_group = st.text_input(
                "Inventory group name",
                key="inventory_custom_group",
                placeholder="e.g. monitoring",
            ).strip()

        node_col, address_col = st.columns(2)
        with node_col:
            node_name = st.text_input(
                "Node name",
                key="inventory_node_name",
                placeholder="e.g. worker-vm-4",
            ).strip()
        with address_col:
            node_address = st.text_input(
                "Node address",
                key="inventory_node_address",
                placeholder="IP address or resolvable hostname",
            ).strip()

        domain_id = ""
        if target_group == "workers":
            domain_id = st.text_input(
                "Brane domain ID",
                key="inventory_domain_id",
                placeholder="e.g. client-node-4",
            ).strip()

        submitted = st.form_submit_button("Save node", type="primary")

    if not submitted:
        return

    if not target_group:
        st.error("Choose a deployment role or provide an inventory group name.")
        return

    if not node_name or not node_address:
        st.error("Node name and node address are required.")
        return

    if target_group == "workers" and not domain_id:
        st.error("A Brane domain ID is required for a worker domain.")
        return

    if not config.has_section(target_group):
        config.add_section(target_group)

    host_value = f"ansible_host={node_address}"
    if domain_id:
        host_value += f" location_id={domain_id}"

    config.set(target_group, node_name, host_value)
    save_inventory(config)
    _reset_inventory_state()

    st.success(f"Saved `{node_name}` in the `{target_group}` inventory group.")
    st.rerun()


def _render_remove_node(config: configparser.ConfigParser) -> None:
    """Render the deliberately separate destructive inventory operation."""
    st.markdown("#### Remove node")
    st.warning(
        "Removing a node changes the deployment inventory. Run the relevant "
        "deployment phase after making this change."
    )

    groups = _editable_groups(config)
    if not groups:
        st.info("There are no inventory groups to edit.")
        return

    with st.form("inventory_remove_node"):
        selected_group = st.selectbox(
            "Inventory group",
            groups,
            key="inventory_remove_group",
        )

        hosts = [hostname for hostname, _value in config.items(selected_group)]
        selected_host = st.selectbox(
            "Node name",
            hosts if hosts else ["No nodes available"],
            key="inventory_remove_host",
        )

        submitted = st.form_submit_button("Remove node")

    if not submitted:
        return

    if selected_host == "No nodes available":
        st.error("Choose an inventory group containing a node.")
        return

    config.remove_option(selected_group, selected_host)

    if not config.items(selected_group):
        config.remove_section(selected_group)

    save_inventory(config)
    _reset_inventory_state()

    st.success(f"Removed `{selected_host}` from the `{selected_group}` group.")
    st.rerun()


def render_cluster_config() -> None:
    """Render the administrator-facing infrastructure inventory workspace."""
    st.title("Infrastructure inventory")
    st.markdown(
        "Define the controller and worker domains used by the Brane deployment. "
        "Deploy infrastructure after changing this inventory."
    )

    _ensure_inventory_exists()

    if "inventory" not in st.session_state:
        st.session_state.inventory = load_inventory()

    config = st.session_state.inventory
    topology = _topology_rows(config)

    _render_topology_summary(topology)

    st.divider()
    st.markdown("### Update inventory")

    action = st.radio(
        "Choose an inventory operation",
        ["Add or update node", "Remove node"],
        horizontal=True,
        key="inventory_action",
    )

    if action == "Add or update node":
        _render_add_or_update(config)
    else:
        _render_remove_node(config)

    with st.expander("Advanced inventory details"):
        st.caption(
            "The raw inventory representation is shown for diagnostics. "
            "Use Update inventory for normal changes."
        )
        st.code(_inventory_text(config), language="ini")
        st.caption(f"Active inventory: `{INVENTORY_PATH}`")
        st.caption(f"Inventory template: `{TEMPLATE_PATH}`")
