import re
import sys
import tempfile
from pathlib import Path

import streamlit as st

from modules import task_manager
from modules.config import REPO_ROOT, get_brane_executable, get_central_ip
from modules.task_ui import render_task_monitor


PACKAGE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _create_workspace(prefix: str) -> Path:
    staging_root = Path(REPO_ROOT) / ".task-staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=staging_root))


def _start_task(
    *,
    operation: str,
    label: str,
    command: list[str],
    metadata: dict,
) -> None:
    task, error = task_manager.start_task(
        role="user",
        operation=operation,
        label=label,
        command=command,
        cwd=REPO_ROOT,
        metadata=metadata,
        lock_name="package-deployment",
    )
    if error:
        st.error(error)
        return

    st.session_state.package_deploy_task_id = task["id"]
    st.success("Package deployment started in the background.")
    st.rerun()


def render_packages_deploy() -> None:
    st.title("Brane Package Deployment & Integration Testing")
    st.markdown(
        "Compile, register, and run package workflows through persistent tasks."
    )

    central_ip = get_central_ip()
    if central_ip:
        st.info(f"Connected to central hub: `{central_ip}`")
    else:
        st.warning(
            "No central hub IP detected. Configure the inventory in "
            "**Cluster Configurator** first."
        )

    tab_custom, tab_smoke = st.tabs(
        ["Upload Custom Package", "Run Smoke Test"]
    )

    with tab_custom:
        st.subheader("Upload Custom Package")
        st.caption(
            "The manifest and ZIP are staged locally, then built and pushed "
            "by a background task."
        )

        col_manifest, col_source = st.columns(2)
        with col_manifest:
            uploaded_manifest = st.file_uploader(
                "Package Manifest (`container.yml`)",
                type=["yml", "yaml"],
            )
        with col_source:
            uploaded_source = st.file_uploader(
                "Source Files Bundle (`.zip`)",
                type=["zip"],
            )

        package_name = st.text_input(
            "Package Name",
            placeholder="e.g. image_processor",
        )

        if st.button(
            "Build and Push Package",
            type="primary",
            disabled=central_ip is None,
        ):
            if not uploaded_manifest or not uploaded_source or not package_name:
                st.error("Supply a manifest, source ZIP, and package name.")
            elif not PACKAGE_NAME_PATTERN.fullmatch(package_name):
                st.error(
                    "Package name must be 1–64 characters using letters, "
                    "numbers, dots, underscores, or hyphens."
                )
            else:
                workspace = _create_workspace("custom-package-")
                try:
                    (workspace / "container.yml").write_bytes(
                        uploaded_manifest.getvalue()
                    )
                    (workspace / "source.zip").write_bytes(
                        uploaded_source.getvalue()
                    )
                except OSError as exc:
                    st.error(f"Could not stage uploaded files: {exc}")
                else:
                    brane_cli = get_brane_executable()
                    _start_task(
                        operation="package_build_push",
                        label=f"Build and push package: {package_name}",
                        command=[
                            sys.executable,
                            str(Path(__file__).with_name("package_deploy_task.py")),
                            "custom",
                            "--workspace",
                            str(workspace),
                            "--brane-cli",
                            brane_cli,
                            "--central-ip",
                            central_ip,
                            "--package-name",
                            package_name,
                        ],
                        metadata={
                            "package_name": package_name,
                            "central_ip": central_ip,
                            "source": "uploaded",
                        },
                    )

    with tab_smoke:
        st.subheader("Run Smoke Test")
        st.caption(
            "Builds, pushes, and executes the baseline hello-world workflow."
        )

        test_mode = st.selectbox(
            "Runtime",
            ["Python-based Package (Recommended)", "Bash Shell-based Package"],
        )

        if st.button(
            "Run Hello World Smoke Test",
            type="primary",
            disabled=central_ip is None,
        ):
            mode = "python" if "Python" in test_mode else "bash"
            workspace = _create_workspace("hello-world-smoke-")
            brane_cli = get_brane_executable()

            _start_task(
                operation="package_smoke_test",
                label=f"Run {mode} hello-world smoke test",
                command=[
                    sys.executable,
                    str(Path(__file__).with_name("package_deploy_task.py")),
                    "smoke",
                    "--workspace",
                    str(workspace),
                    "--brane-cli",
                    brane_cli,
                    "--central-ip",
                    central_ip,
                    "--mode",
                    mode,
                ],
                metadata={
                    "central_ip": central_ip,
                    "runtime": mode,
                },
            )

    task_id = st.session_state.get("package_deploy_task_id")
    if task_id:
        render_task_monitor(
            task_id,
            title="Package deployment and smoke-test progress",
        )
