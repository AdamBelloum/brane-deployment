"""Streamlit components for file-backed frontend tasks."""

from __future__ import annotations

import streamlit as st

from modules import task_store


STATUS_ICON = {
    "queued": "⏳",
    "running": "⚡",
    "succeeded": "✓",
    "failed": "✗",
    "interrupted": "!",
}


def _reconciled_tasks(limit: int | None = None) -> list[dict]:
    return [task_store.reconcile_task(task) for task in task_store.list_tasks(limit)]


def render_activity_sidebar() -> None:
    """Global activity summary, visible on every frontend page."""
    tasks = _reconciled_tasks(limit=8)
    active = [task for task in tasks if task.get("status") in task_store.ACTIVE_STATUSES]

    st.sidebar.divider()
    st.sidebar.markdown("### Activity")
    if active:
        st.sidebar.warning(f"{len(active)} background task{'s' if len(active) != 1 else ''} active")
        for task in active:
            st.sidebar.caption(f"⚡ {task['label']}")
    else:
        st.sidebar.caption("No background tasks are active.")

    if tasks:
        with st.sidebar.expander("Recent tasks", expanded=False):
            for task in tasks[:5]:
                icon = STATUS_ICON.get(task.get("status"), "•")
                st.caption(f"{icon} {task['label']} — {task['status']}")


def render_task_monitor(task_id: str, title: str = "Operation progress") -> None:
    """Render persistent state and the current tail of a task log."""
    task = task_store.read_task(task_id)
    if task is None:
        st.warning("The selected task record no longer exists.")
        return

    task = task_store.reconcile_task(task)
    status = task.get("status", "unknown")
    icon = STATUS_ICON.get(status, "•")

    st.subheader(title)
    st.caption(f"Task `{task['id']}`")
    if status == "running":
        st.warning(f"{icon} {task['label']} is running.")
    elif status == "succeeded":
        st.success(f"{icon} {task['label']} completed successfully.")
    elif status == "failed":
        st.error(f"{icon} {task['label']} failed; inspect the log below.")
    elif status == "interrupted":
        st.warning("! The process is no longer present; its final exit status could not be recovered.")
    else:
        st.info(f"{icon} {task['label']} is {status}.")

    columns = st.columns(3)
    columns[0].metric("Role", task.get("role", "—"))
    columns[1].metric("Operation", task.get("operation", "—"))
    columns[2].metric("Exit code", str(task.get("exit_code", "—")))

    if st.button("Refresh task status", key=f"refresh-{task_id}"):
        st.rerun()

    st.code(task_store.read_log_tail(task), language="text")
