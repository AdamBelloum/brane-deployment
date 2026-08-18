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


def _display_timestamp(value: object) -> str:
    """Render an ISO task timestamp compactly while retaining its UTC offset."""
    if not value:
        return "—"
    return str(value).replace("T", " ")


def _task_option_label(task: dict) -> str:
    """Create a readable, unique task-history selector label."""
    icon = STATUS_ICON.get(task.get("status"), "•")
    created_at = _display_timestamp(task.get("created_at"))
    short_id = str(task.get("id", ""))[-8:]
    return f"{icon} {created_at} — {task.get('label', 'Unnamed task')} [{short_id}]"


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
        st.sidebar.caption("Open **Task History** for logs and details.")


def render_task_monitor(task_id: str, title: str = "Operation progress") -> None:
    """Render persistent state, metadata, timestamps, and the task-log tail."""
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

    columns = st.columns(4)
    columns[0].metric("Status", status.capitalize())
    columns[1].metric("Role", task.get("role", "—"))
    columns[2].metric("Operation", task.get("operation", "—"))
    columns[3].metric("Exit code", str(task.get("exit_code", "—")))

    time_columns = st.columns(3)
    time_columns[0].caption(f"Created: {_display_timestamp(task.get('created_at'))}")
    time_columns[1].caption(f"Started: {_display_timestamp(task.get('started_at'))}")
    time_columns[2].caption(f"Finished: {_display_timestamp(task.get('finished_at'))}")

    if st.button("Refresh task status", key=f"refresh-{task_id}"):
        st.rerun()

    with st.expander("Task metadata", expanded=False):
        metadata = task.get("metadata") or {}
        if metadata:
            st.json(metadata)
        else:
            st.caption("No metadata was recorded for this task.")

    show_log = status in task_store.ACTIVE_STATUSES or status in {"failed", "interrupted"}
    with st.expander("Task log", expanded=show_log):
        st.code(task_store.read_log_tail(task), language="text")


def render_task_history() -> None:
    """Render a filterable history of local frontend tasks."""
    st.title("Task History")
    st.caption(
        "Tasks and logs are stored locally on this control machine. "
        "Select a task to inspect its persistent state and log."
    )

    tasks = _reconciled_tasks(limit=100)
    if not tasks:
        st.info("No frontend tasks have been recorded yet.")
        return

    roles = sorted({str(task.get("role", "unknown")) for task in tasks})
    statuses = sorted({str(task.get("status", "unknown")) for task in tasks})

    filter_columns = st.columns(2)
    selected_role = filter_columns[0].selectbox(
        "Role",
        ["All roles", *roles],
        key="task-history-role",
    )
    selected_status = filter_columns[1].selectbox(
        "Status",
        ["All statuses", *statuses],
        key="task-history-status",
    )

    filtered_tasks = [
        task
        for task in tasks
        if (selected_role == "All roles" or task.get("role") == selected_role)
        and (selected_status == "All statuses" or task.get("status") == selected_status)
    ]

    if not filtered_tasks:
        st.info("No tasks match the selected filters.")
        return

    task_by_id = {task["id"]: task for task in filtered_tasks}
    selected_task_id = st.selectbox(
        "Recorded task",
        list(task_by_id),
        format_func=lambda task_id: _task_option_label(task_by_id[task_id]),
        key="task-history-selection",
    )
    render_task_monitor(selected_task_id, title="Task details")
