import re
from pathlib import Path

import streamlit as st

from modules import task_manager
from modules.config import REPO_ROOT, get_brane_executable
from modules.task_ui import render_task_monitor


WORKFLOW_DIR = Path(REPO_ROOT) / "workflow_codes"
SCRIPT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.bs$")


def _remote_url(host: str, port: str) -> str | None:
    """Validate and construct the remote Brane workflow endpoint."""
    host = host.strip()
    port = port.strip()

    if not host:
        return None
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        return None

    # This field accepts a hostname or IP address, not a complete URL.
    if any(character in host for character in ("/", "?", "#", "@", ":")):
        return None

    return f"http://{host}:{port}"


def render_brane_scripts() -> None:
    st.title("📜 BraneScript Workflow Studio")
    st.write(
        "Author workflows locally and execute them through persistent "
        "background tasks."
    )

    with st.expander("Workflow Execution Guidelines", expanded=True):
        st.markdown(
            "Packages must be built and published before execution. "
            "Remote execution requires a configured Central Hub endpoint."
        )

    if "workflow_editor_filename" not in st.session_state:
        st.session_state.workflow_editor_filename = "my_analysis.bs"

    if "workflow_editor_code" not in st.session_state:
        st.session_state.workflow_editor_code = """// Import compiled package modules
import hello_world;

let patient_data := new Data { name := "patient_records" };
let count := 42;

if count > 10 {
    let result := hello_world();
    println(result);
} else {
    println("Threshold constraint not met.");
}
"""

    editor_column, documentation_column = st.columns([3, 2])

    with editor_column:
        st.subheader("Script Canvas")
        script_name = st.text_input(
            "Workflow filename",
            key="workflow_editor_filename",
            help="Use a filename ending in .bs; directory paths are not allowed.",
        )
        workflow_code = st.text_area(
            "BraneScript code",
            height=400,
            key="workflow_editor_code",
        )

    with documentation_column:
        st.subheader("Execution Settings")
        execution_mode = st.radio(
            "Execution target",
            ["Remote Instance", "Local"],
            horizontal=True,
        )

        remote_host = st.text_input(
            "Central instance host or IP address",
            placeholder="e.g. 145.100.135.209",
            disabled=execution_mode == "Local",
        )
        remote_port = st.text_input(
            "Central workflow port",
            value="50053",
            disabled=execution_mode == "Local",
        )

        st.caption(
            "Remote execution uses the active local Brane CLI configuration. "
            "No credentials are stored in task metadata."
        )

    if st.button(
        "Launch Workflow Execution",
        type="primary",
        key="workflow_editor_launch",
    ):
        if not SCRIPT_NAME_PATTERN.fullmatch(script_name):
            st.error(
                "Use a simple .bs filename containing letters, numbers, "
                "dots, underscores, or hyphens."
            )
        else:
            remote_url = None
            if execution_mode == "Remote Instance":
                remote_url = _remote_url(remote_host, remote_port)
                if remote_url is None:
                    st.error(
                        "Enter a valid host/IP address and a port from 1 to 65535."
                    )
                    return

            try:
                WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
                workflow_path = WORKFLOW_DIR / script_name
                workflow_path.write_text(workflow_code, encoding="utf-8")
            except OSError as exc:
                st.error(f"Could not save the workflow: {exc}")
                return

            command = [
                get_brane_executable(),
                "workflow",
                "run",
                script_name,
            ]
            if remote_url:
                command.extend(["--remote", remote_url])

            task, error = task_manager.start_task(
                role="user",
                operation="workflow_editor_run",
                label=f"Run workflow: {script_name}",
                command=command,
                cwd=WORKFLOW_DIR,
                metadata={
                    "workflow": script_name,
                    "mode": "remote" if remote_url else "local",
                    "remote_url": remote_url,
                },
                # Shares the workflow lock with User Workspace execution.
                lock_name="workflow-execution",
            )

            if error:
                st.error(error)
            else:
                st.session_state.workflow_editor_task_id = task["id"]
                st.success("Workflow execution started in the background.")
                st.rerun()

    task_id = st.session_state.get("workflow_editor_task_id")
    if task_id:
        render_task_monitor(
            task_id,
            title="Workflow execution progress",
        )
