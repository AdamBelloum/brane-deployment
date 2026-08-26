import re
from pathlib import Path

import streamlit as st

from modules import task_manager
from modules.config import REPO_ROOT, get_brane_executable
from modules.task_ui import render_task_monitor


WORKFLOW_DIR = Path(REPO_ROOT) / "workflow_codes"
SCRIPT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.bs$")
REMOTE_WORKFLOW_PAUSE_MESSAGE = (
    "Remote workflow submission is paused pending Brane developer "
    "clarification of planner/checker-selection behaviour."
)


def _save_workflow(filename: str, source: str) -> Path:
    """Save one validated workflow in the repository workflow directory."""
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    workflow_path = WORKFLOW_DIR / filename
    workflow_path.write_text(source, encoding="utf-8")
    return workflow_path


def render_brane_scripts() -> None:
    """Render the user-facing workflow authoring and execution page."""
    st.title("Workflow Studio")
    st.markdown(
        "Write a BraneScript workflow, save it locally, and run it on this "
        "workstation."
    )

    with st.expander("Before you run a workflow"):
        st.markdown(
            "1. Build the required package in **User Workspace → Packages**.\n"
            "2. Configure the required local Brane environment.\n"
            "3. Ensure any applicable policy has been managed by a "
            "Policy Manager.\n"
            "4. Remote workflow submission is currently paused."
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
            ["Local workstation", "Remote configured instance (paused)"],
            horizontal=False,
            key="workflow_execution_mode",
        )

        remote_execution_selected = execution_mode.startswith("Remote")

        if remote_execution_selected:
            st.warning(REMOTE_WORKFLOW_PAUSE_MESSAGE)
            st.caption(
                "Remote execution will remain unavailable until the deployment "
                "can be accepted end-to-end."
            )
        else:
            st.caption(
                "The workflow runs using the local Brane command configuration."
            )

    if st.button(
        "Run local workflow",
        type="primary",
        key="workflow_editor_launch",
        disabled=remote_execution_selected,
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
            st.success("Local workflow execution started in the background.")
            st.rerun()

    task_id = st.session_state.get("workflow_editor_task_id")
    if task_id:
        render_task_monitor(task_id, title="Workflow execution progress")
