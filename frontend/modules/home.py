from __future__ import annotations

import configparser
import os

import streamlit as st

from modules.config import INVENTORY_PATH


def _parse_inventory() -> dict[str, list[tuple[str, str]]]:
    """Parse hosts.ini and return {section: [(hostname, variables)]}."""
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

    return {
        section: list(config.items(section))
        for section in config.sections()
    }


def _extract_variable(variables: str, variable_name: str) -> str | None:
    """Return a single Ansible-style variable value from an inventory line."""
    if not variables:
        return None

    prefix = f"{variable_name}="
    for part in variables.split():
        if part.startswith(prefix):
            return part.split("=", 1)[1]

    return None


def _request_page(page_id: str) -> None:
    """Request navigation through the application shell."""
    st.session_state.requested_page = page_id
    st.rerun()


def _render_role_card(
    *,
    title: str,
    description: str,
    primary_label: str,
    primary_page: str,
    secondary_label: str | None = None,
    secondary_page: str | None = None,
) -> None:
    """Render one role entry point."""
    with st.container(border=True):
        st.subheader(title)
        st.write(description)

        st.button(
            primary_label,
            key=f"home_{primary_page}",
            type="primary",
            use_container_width=True,
            on_click=_request_page,
            args=(primary_page,),
        )

        if secondary_label and secondary_page:
            st.button(
                secondary_label,
                key=f"home_{secondary_page}",
                use_container_width=True,
                on_click=_request_page,
                args=(secondary_page,),
            )


def _inventory_rows(
    inventory: dict[str, list[tuple[str, str]]],
) -> list[dict[str, str]]:
    """Convert configured hosts to rows suitable for display."""
    rows: list[dict[str, str]] = []

    for group, hosts in inventory.items():
        if not hosts:
            rows.append(
                {
                    "Group": group,
                    "Host": "No nodes configured",
                    "Address": "—",
                    "Location": "—",
                }
            )
            continue

        for hostname, variables in hosts:
            rows.append(
                {
                    "Group": group,
                    "Host": hostname,
                    "Address": _extract_variable(variables, "ansible_host") or "—",
                    "Location": _extract_variable(variables, "location_id") or "—",
                }
            )

    return rows


def render_home_dashboard() -> None:
    """Render the Brane Control Center landing page."""
    st.title("Brane Control Center")

    st.caption( "Manage Brane infrastructure, policy lifecycle, and distributed workflow execution from one workspace.")
    st.divider()

    st.subheader("Getting started")
    st.markdown(
        """
        Use the navigation menu on the left to select the workspace that
        matches your responsibility:

        1. **Administration** — configure, deploy, and inspect the Brane
           infrastructure.
        2. **Policy management** — inspect policy state, upload policy
           versions, and activate policies.
        3. **User workspace** — manage instances and packages, then submit
           local or remote workflows.

        Active and completed background operations remain available in
        **Task history**.
        """
    )

    st.divider()

    inventory = _parse_inventory()

    st.subheader("Deployment overview")

    if not inventory:
        st.info(
            "No Ansible inventory is configured. Use Cluster configuration "
            "in the Administration menu before deploying infrastructure or "
            "connecting to worker nodes."
        )
        return

    rows = _inventory_rows(inventory)
    configured_nodes = sum(
        1
        for row in rows
        if row["Host"] != "No nodes configured"
    )

    node_metric, group_metric = st.columns(2)
    node_metric.metric("Configured nodes", configured_nodes)
    group_metric.metric("Inventory groups", len(inventory))

    st.dataframe(
        rows,
        column_config={
            "Group": st.column_config.TextColumn("Inventory group"),
            "Host": st.column_config.TextColumn("Host"),
            "Address": st.column_config.TextColumn("Address"),
            "Location": st.column_config.TextColumn("Location"),
        },
        hide_index=True,
        use_container_width=True,
    )
