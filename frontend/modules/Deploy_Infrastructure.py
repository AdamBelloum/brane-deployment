"""Admin deployment page backed by persistent local task files."""

from __future__ import annotations

import os

import streamlit as st

from modules.config import ANSIBLE_DIR, INVENTORY_PATH, PLAYBOOK
from modules.task_manager import start_task
from modules.task_store import ACTIVE_STATUSES, list_tasks
from modules.task_ui import render_task_monitor


DEPLOYMENT_OPTIONS = {
    "Full deployment — recommended": {
        "tags": None,
        "description": "Run the full deployment: prerequisites → branectl → workers → central → certs → start → smoke.",
    },
    "Prerequisites": {
        "tags": "prerequisites",
        "description": "Install and validate required deployment prerequisites.",
    },
    "Install Branectl": {
        "tags": "branectl",
        "description": "Install the Brane administration tooling.",
    },
    "Configure workers": {
        "tags": "workers",
        "description": "Configure worker nodes and their Brane services.",
    },
    "Configure central": {
        "tags": "central",
        "description": "Configure the central Brane services.",
    },
    "Exchange certificates": {
        "tags": "certs",
        "description": "Generate and distribute node certificates.",
    },
    "Start services": {
        "tags": "start",
        "description": "Start the configured Brane services.",
    },
    "Run smoke test": {
        "tags": "smoke",
        "description": "Run the end-to-end smoke test.",
    },
}

def _deployment_tasks() -> list[dict]:
    return [
        task
        for task in list_tasks()
        if task.get("operation") == "ansible_deployment"
    ]


def _start_deployment(label: str, tags: str | None) -> tuple[dict | None, str | None]:
    command = ["ansible-playbook", "-i", INVENTORY_PATH, PLAYBOOK]
    if tags:
        command.extend(["--tags", tags])

    return start_task(
        role="admin",
        operation="ansible_deployment",
        label=label,
        command=command,
        cwd=ANSIBLE_DIR,
        metadata={"tags": tags.split(",") if tags else ["all"]},
        lock_name="infrastructure-deployment",
    )


def render_infra_deploy() -> None:
    st.title("Deploy & Configure")
    st.write("Run the same Ansible deployment stages exposed by the Admin helper script.")
    st.info(
        "Recommended order: prerequisites → branectl → workers → central → certs → start → smoke. "
        "Full deployment runs this sequence in one operation."
    )

    if not os.path.isfile(INVENTORY_PATH):
        st.error(f"Inventory not found: `{INVENTORY_PATH}`")
        st.caption("Configure the cluster inventory before starting a deployment.")
        return
    if not os.path.isfile(PLAYBOOK):
        st.error(f"Playbook not found: `{PLAYBOOK}`")
        return

    tasks = _deployment_tasks()
    active_tasks = [task for task in tasks if task.get("status") in ACTIVE_STATUSES]
    latest_task = tasks[0] if tasks else None

    if active_tasks:
        st.warning("A deployment is active. Starting another infrastructure deployment is disabled until it completes.")

    selected_label = st.selectbox("Deployment action", list(DEPLOYMENT_OPTIONS))
    selected = DEPLOYMENT_OPTIONS[selected_label]
    st.caption(selected["description"])

    if st.button("Start deployment", type="primary", disabled=bool(active_tasks)):
        task, error = _start_deployment(selected_label, selected["tags"])
        if error:
            st.error(error)
        elif task:
            st.session_state.selected_deployment_task_id = task["id"]
            st.success("Deployment started in the background.")
            st.rerun()

    if latest_task:
        selected_task_id = st.session_state.get("selected_deployment_task_id", latest_task["id"])
        if active_tasks:
            render_task_monitor(selected_task_id, title="Deployment progress")
        else:
            st.info(
                "No deployment is currently running. "
                "Showing the most recent recorded deployment task."
            )
            render_task_monitor(
                selected_task_id,
                title="Most recent deployment task",
                historical=True,
            )
    else:
        st.caption("No deployment task has been started from this frontend yet.")
