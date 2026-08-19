import re
import subprocess
import sys
from pathlib import Path
from typing import List

import streamlit as st

from modules import task_manager
from modules.config import REPO_ROOT, get_brane_executable
from modules.task_ui import render_task_monitor


WORKFLOW_DIR = Path(REPO_ROOT) / "workflow_codes"
REMOTE_RUNNER = Path(__file__).with_name("run_remote_workflow.py")
SCRIPT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.bs$")


def _get_instances() -> List[str]:
    """Return configured local Brane instance names."""
    try:
        result = subprocess.run(
            [get_brane_executable(), "instance", "list"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    if result.returncode != 0:
        return []

    instances = []
    for line in result.stdout.splitlines():
        fields = line.replace("\x00", "").strip().split()
        if fields and fields[0].upper() != "NAME":
            instances.append(fields[0])

    return instances


def _save_workflow(filename: str, source: str) -> Path:
    """Save one validated workflow in the repository workflow directory."""
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    workflow_path = WORKFLOW_DIR / filename
    workflow_path.write_text(source, encoding="utf-8")
    return workflow_path


def render_brane_scripts() -> None:
    """Render the single user-facing workflow authoring and execution page."""
    st.title("Workflow Studio")
    st.markdown(
        "Write a BraneScript workflow, save it locally, and run it on this "
        "workstation or through a configured Brane instance."
    )

    with st.expander("Before you run a workflow"):
        st.markdown(
            "1. Build the required package in **User Workspace → Packages**.\n"
            "2. Configure a Brane instance in **User Workspace → Instances** "
            "for remote execution.\n"
            "3. Ensure the applicable domain policy has been activated by a "
            "Policy Manager."
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

    editor_column, settings_column = st.columns([3, 2])

    with editor_column:
        st.subheader("Workflow")
        script_name = st.text_input(
            "Workflow filename",
            key="workflow_editor_filename",
            help="Use a .bs filename. Directory paths are not allowed.",
        )
        workflow_code = st.text_area(
            "BraneScript code",
            height=420,
            key="workflow_editor_code",
        )

    with settings_column:
        st.subheader("Execution settings")

        workflow_user = st.text_input(
            "Workflow label",
            key="workflow_user_label",
            placeholder="Your name or project label",
            help=(
                "This label identifies the workflow submission. "
                "It is not an Administrator-provisioned login."
            ),
        )

        execution_mode = st.radio(
            "Execution target",
            ["Remote configured instance", "Local workstation"],
            horizontal=False,
            key="workflow_execution_mode",
        )

        selected_instance = None
        if execution_mode == "Remote configured instance":
            instances = _get_instances()

            if instances:
                selected_instance = st.selectbox(
                    "Brane instance",
                    instances,
                    key="workflow_instance",
                )
                st.caption(
                    "The selected instance is activated immediately before "
                    "remote workflow submission."
                )
            else:
                st.warning(
                    "No configured instances were found. Add one in "
                    "**User Workspace → Instances** before running remotely."
                )
        else:
            st.caption(
                "The workflow runs using the local Brane command configuration."
            )

    remote_unavailable = (
        execution_mode == "Remote configured instance" and not selected_instance
    )

    if st.button(
        "Run workflow",
        type="primary",
        key="workflow_editor_launch",
        disabled=remote_unavailable,
    ):
        if not SCRIPT_NAME_PATTERN.fullmatch(script_name):
            st.error(
                "Use a simple .bs filename containing letters, numbers, "
                "dots, underscores, or hyphens."
            )
            return

        if not workflow_user.strip():
            st.error("Enter a workflow label before running the workflow.")
            return

        try:
            workflow_path = _save_workflow(script_name, workflow_code)
        except OSError as exc:
            st.error(f"Could not save the workflow: {exc}")
            return

        if execution_mode == "Remote configured instance":
            if not REMOTE_RUNNER.is_file():
                st.error(
                    "The remote workflow runner is missing: "
                    f"`{REMOTE_RUNNER}`"
                )
                return

            command = [
                sys.executable,
                str(REMOTE_RUNNER),
                "--instance",
                selected_instance,
                "--username",
                workflow_user.strip(),
                "--workflow",
                str(workflow_path),
            ]
            operation = "workflow_editor_run_remote"
            label = f"Remote workflow: {script_name} via {selected_instance}"
            metadata = {
                "workflow": script_name,
                "mode": "remote",
                "instance": selected_instance,
                "username": workflow_user.strip(),
            }
        else:
            command = [
                get_brane_executable(),
                "workflow",
                "run",
                workflow_user.strip(),
                script_name,
            ]
            operation = "workflow_editor_run_local"
            label = f"Local workflow: {script_name}"
            metadata = {
                "workflow": script_name,
                "mode": "local",
                "username": workflow_user.strip(),
            }

        task, error = task_manager.start_task(
            role="user",
            operation=operation,
            label=label,
            command=command,
            cwd=WORKFLOW_DIR,
            metadata=metadata,
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
        render_task_monitor(task_id, title="Workflow execution progress")
