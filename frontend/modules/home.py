import configparser
import os
import streamlit as st
from modules.config import INVENTORY_PATH


def _parse_inventory() -> dict:
    """
    Parse hosts.ini and return a dict of {section: [(hostname, vars_string)]}.
    Returns an empty dict if the file does not exist yet.
    """
    if not os.path.exists(INVENTORY_PATH):
        return {}

    config = configparser.ConfigParser(
        allow_no_value=True,
        delimiters=(" ", "="),
        comment_prefixes=("#", ";"),
        inline_comment_prefixes=("#", ";"),
    )
    config.optionxform = str
    config.read(INVENTORY_PATH)

    result = {}
    for section in config.sections():
        result[section] = list(config.items(section))
    return result


def _extract_ip(vars_string: str) -> str:
    """Extract ansible_host IP value from a vars string, or return '—'."""
    if not vars_string:
        return "—"
    for part in vars_string.split():
        if part.startswith("ansible_host="):
            return part.split("=", 1)[1]
    return "—"


def render_home_dashboard():
    """Home dashboard — shows live cluster topology read from hosts.ini."""
    st.title("🌐 Brane Distributed Framework Console")

    with st.expander("📖 System Guide & Overview", expanded=True):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("""
            **What it does:**
            Central command hub showing the current cluster topology
            as configured in your local `hosts.ini`.
            """)
        with col_b:
            st.markdown("""
            **Who is this for:** System Administrators, Developers, and Data Scientists.

            **Prerequisites:** Configure your inventory in the
            **Cluster Configurator** before deploying.
            """)

    st.write(
        "Welcome to the unified Brane management platform. "
        "Use the sidebar to deploy infrastructure, stage packages, or write computations."
    )
    st.divider()

    # ── Topology from hosts.ini ──────────────────────────────────────────────
    st.subheader("🖥️ Cluster Topology")

    inventory = _parse_inventory()

    if not inventory:
        st.warning(
            "No inventory found. "
            "Copy `hosts.ini.template` to `hosts.ini` and configure your nodes "
            "in the **Cluster Configurator**, then return here."
        )
        return

    for section, hosts in inventory.items():
        st.markdown(f"#### `[{section}]`")
        if not hosts:
            st.caption("*(no nodes configured)*")
            continue

        cols = st.columns(max(len(hosts), 1))
        for col, (hostname, vars_str) in zip(cols, hosts):
            ip = _extract_ip(vars_str)
            # Extract location_id if present
            location_id = None
            if vars_str:
                for part in vars_str.split():
                    if part.startswith("location_id="):
                        location_id = part.split("=", 1)[1]
            with col:
                st.metric(label=hostname, value=ip, delta="configured")
                if location_id:
                    st.caption(f"location: `{location_id}`")

