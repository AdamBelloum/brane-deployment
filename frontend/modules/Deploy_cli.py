# =============================================================
# Deploy_cli.py
# Shared workstation setup for the local Brane command
# =============================================================

import platform
import subprocess
import sys
from pathlib import Path
from typing import Tuple

import streamlit as st

from modules import task_manager
from modules.config import REPO_ROOT, get_brane_executable
from modules.task_ui import render_task_monitor


def _detect_local_brane_command() -> Tuple[str, str]:
    """Return the resolved local command and its version when executable."""
    executable = get_brane_executable()

    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return executable, ""

    if result.returncode != 0:
        return executable, ""

    version = (result.stdout or result.stderr).strip().splitlines()
    return executable, version[0] if version else "Installed"


def _platform_options() -> tuple[dict[str, str], int]:
    """Return supported release artifacts and a sensible local default."""
    detected_os = platform.system()
    detected_arch = platform.machine().lower()

    options = {
        "Linux (x86_64)": "brane-linux-x86_64",
        "Linux (ARM64 / aarch64)": "brane-linux-aarch64",
        "macOS (Apple Silicon)": "brane-macos-aarch64",
        "macOS (Intel)": "brane-macos-x86_64",
        "Windows (x86_64)": "brane-windows-x86_64.exe",
    }

    if detected_os == "Darwin":
        return options, 2 if ("arm" in detected_arch or "aarch" in detected_arch) else 3
    if detected_os == "Linux":
        return options, 0 if "x86" in detected_arch else 1
    if detected_os == "Windows":
        return options, 4

    return options, 0


def render_cli_panel() -> None:
    """Render shared local setup without infrastructure lifecycle controls."""
    st.title("Workstation setup")
    st.markdown(
        "Install and verify the local `brane` command used by this workstation. "
        "Infrastructure deployment and service lifecycle are managed in "
        "**Administration**."
    )

    st.divider()
    st.markdown("### Local Brane command")

    detected_os = platform.system()
    detected_arch = platform.machine()
    executable, version = _detect_local_brane_command()

    status_col, platform_col, path_col = st.columns(3)
    with status_col:
        st.metric("Command status", "Available" if version else "Not verified")
    with platform_col:
        st.metric("Workstation", f"{detected_os} · {detected_arch}")
    with path_col:
        st.metric("Command path", Path(executable).name)

    if version:
        st.success(f"Local command verified: `{version}`")
        st.caption(f"Resolved command: `{executable}`")
    else:
        st.info(
            "No working local `brane` command was detected. "
            "Install or update it below."
        )

    binary_options, default_index = _platform_options()
    selected_platform = st.selectbox(
        "Download target",
        list(binary_options.keys()),
        index=default_index,
        key="workstation_cli_platform",
    )

    binary_name = binary_options[selected_platform]
    download_url = (
        "https://github.com/BraneFramework/brane/releases/download/nightly/"
        f"{binary_name}"
    )

    st.caption(
        "The installer downloads the selected nightly release to the local "
        "user environment. Administrator privileges are not required."
    )

    if st.button(
        "Install or update local Brane command",
        key="workstation_install_cli",
        type="primary",
    ):
        task, error = task_manager.start_task(
            role="user",
            operation="cli_install",
            label=f"Install local Brane command: {selected_platform}",
            command=[
                sys.executable,
                str(Path(__file__).with_name("cli_install_task.py")),
                "--download-url",
                download_url,
            ],
            cwd=REPO_ROOT,
            metadata={
                "platform_variant": selected_platform,
                "download_url": download_url,
            },
            lock_name="cli-install",
        )

        if error:
            st.error(error)
        else:
            st.session_state.cli_install_task_id = task["id"]
            st.success("Local command installation started in the background.")
            st.rerun()

    task_id = st.session_state.get("cli_install_task_id")
    if task_id:
        render_task_monitor(task_id, title="Local command installation progress")

    st.divider()
    st.markdown("### Using the local command")
    st.caption(
        "These references are copyable examples. Run infrastructure lifecycle "
        "operations through Administration → Deploy infrastructure."
    )

    with st.expander("Command reference"):
        user_col, admin_col = st.columns(2)

        with user_col:
            st.markdown("#### Packages and workflows")
            st.code(
                """# Inspect configured Brane instances
brane instance list

# Build a package from its directory
brane package build ./packages/hello_world

# Submit a workflow
brane workflow run ./workflow.bscript""",
                language="bash",
            )

        with admin_col:
            st.markdown("#### Deployment reference")
            st.code(
                """# Inspect the local Brane command
brane --version

# Use the repository helpers for infrastructure operations
bash scripts/brane_healthcheck.sh

# Use Administration → Deploy infrastructure
# for Ansible deployment phases and smoke tests.""",
                language="bash",
            )

    with st.expander("Advanced details"):
        st.code(
            "\n".join(
                [
                    f"Detected operating system: {detected_os}",
                    f"Detected architecture: {detected_arch}",
                    f"Resolved local command: {executable}",
                    f"Nightly download URL: {download_url}",
                    f"Repository root: {REPO_ROOT}",
                ]
            ),
            language="text",
        )
