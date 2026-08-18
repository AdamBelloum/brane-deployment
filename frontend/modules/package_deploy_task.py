"""Background tasks for package deployment and smoke-test execution."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def run_command(description: str, command: list[str], cwd: Path) -> int:
    """Run a command and stream combined stdout/stderr to the task log."""
    print(f"\n[package-deploy] {description}", flush=True)
    print(f"[package-deploy] Command: {' '.join(command)}", flush=True)

    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        print(f"[package-deploy] Could not start command: {exc}", flush=True)
        return 1

    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)

    return process.wait()


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    """Extract ZIP contents while rejecting entries outside destination."""
    destination = destination.resolve()

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if target != destination and destination not in target.parents:
                raise ValueError(
                    f"Unsafe ZIP entry rejected: {member.filename!r}"
                )

        archive.extractall(destination)


def make_executable_files(directory: Path) -> None:
    """Preserve the dashboard's previous executable-file behaviour."""
    for path in directory.rglob("*"):
        if path.is_file():
            path.chmod(0o755)


def login(brane_cli: str, central_ip: str, username: str, cwd: Path) -> int:
    return run_command(
        "Logging in to the central registry...",
        [brane_cli, "login", f"http://{central_ip}", "--username", username],
        cwd,
    )


def run_custom(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    manifest = workspace / "container.yml"
    source_zip = workspace / "source.zip"

    if not manifest.is_file() or not source_zip.is_file():
        print("[package-deploy] Staged manifest or source ZIP is missing.", flush=True)
        return 1

    try:
        safe_extract_zip(source_zip, workspace)
        make_executable_files(workspace)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"[package-deploy] Could not safely extract source ZIP: {exc}", flush=True)
        return 1
    finally:
        source_zip.unlink(missing_ok=True)

    if run_command(
        "Building package...",
        [args.brane_cli, "package", "build", "./container.yml"],
        workspace,
    ) != 0:
        return 1

    if login(args.brane_cli, args.central_ip, "dashboard_user", workspace) != 0:
        return 1

    return run_command(
        f"Pushing package {args.package_name!r}...",
        [args.brane_cli, "package", "push", args.package_name],
        workspace,
    )


def run_smoke(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    if args.mode == "python":
        package_name = "python_hello"
        action_name = "hello"
        (workspace / "analyze.py").write_text(
            "#!/usr/bin/env python3\n"
            "import yaml\n"
            'print(yaml.dump({"output": "Hello from Python!"}, '
            "default_flow_style=True).strip())\n",
            encoding="utf-8",
        )
        container_yml = (
            "name: python_hello\nversion: 1.0.0\nkind: ecu\n"
            "dependencies:\n - python3\n - python3-yaml\n"
            "files:\n - analyze.py\nentrypoint:\n kind: task\n exec: analyze.py\n"
            "actions:\n 'hello':\n  command:\n  input:\n  output:\n"
            "   - name: output\n     type: string\n"
        )
    else:
        package_name = "bash_hello"
        action_name = "hello_world"
        (workspace / "hello_world.sh").write_text(
            '#!/bin/bash\necho \'output: "Hello from Bash!"\'\n',
            encoding="utf-8",
        )
        container_yml = (
            "name: bash_hello\nversion: 1.0.0\nkind: ecu\n"
            "files:\n - hello_world.sh\nentrypoint:\n kind: task\n exec: hello_world.sh\n"
            "actions:\n 'hello_world':\n  command:\n  input:\n  output:\n"
            "   - name: output\n     type: string\n"
        )

    (workspace / "container.yml").write_text(container_yml, encoding="utf-8")
    make_executable_files(workspace)

    if run_command(
        "Building smoke-test package...",
        [args.brane_cli, "package", "build", "./container.yml"],
        workspace,
    ) != 0:
        return 1

    if login(args.brane_cli, args.central_ip, "smoke_tester", workspace) != 0:
        return 1

    if run_command(
        "Pushing smoke-test package...",
        [args.brane_cli, "package", "push", package_name],
        workspace,
    ) != 0:
        return 1

    (workspace / "workflow.bs").write_text(
        f"import {package_name};\nprint({package_name}.{action_name}());\n",
        encoding="utf-8",
    )

    return run_command(
        "Running remote smoke-test workflow...",
        [
            args.brane_cli,
            "workflow",
            "run",
            "workflow.bs",
            "--remote",
            f"http://{args.central_ip}:50053",
        ],
        workspace,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)

    custom = subparsers.add_parser("custom")
    custom.add_argument("--workspace", required=True)
    custom.add_argument("--brane-cli", required=True)
    custom.add_argument("--central-ip", required=True)
    custom.add_argument("--package-name", required=True)

    smoke = subparsers.add_parser("smoke")
    smoke.add_argument("--workspace", required=True)
    smoke.add_argument("--brane-cli", required=True)
    smoke.add_argument("--central-ip", required=True)
    smoke.add_argument("--mode", choices=["python", "bash"], required=True)

    args = parser.parse_args()

    try:
        if args.operation == "custom":
            return run_custom(args)
        return run_smoke(args)
    finally:
        workspace = Path(args.workspace)
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
