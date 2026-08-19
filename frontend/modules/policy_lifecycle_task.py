"""Background tasks for inspecting and activating Brane policy versions.

The worker-side ``branectl`` client speaks to brane-chk using its native gRPC
protocol. JWT values are read locally and delivered to the remote command only
over SSH standard input. They are never placed in task metadata, command
arguments, or task logs.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path


VERSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def read_token(token_path: Path) -> str:
    """Read a JSON-wrapped or raw JWT without ever displaying it."""
    raw_value = token_path.read_text(encoding="utf-8").strip()

    if not raw_value:
        raise ValueError("The token file is empty.")

    if not raw_value.startswith("{"):
        return raw_value

    token_data = json.loads(raw_value)
    if not isinstance(token_data, dict):
        raise ValueError("The JSON token file must contain an object.")

    token = token_data.get("token") or token_data.get("access_token")
    if token is None and token_data:
        token = next(iter(token_data.values()))

    if not isinstance(token, str) or not token.strip():
        raise ValueError("The token file does not contain a usable token.")

    return token.strip()


def redact(text: str, token: str) -> str:
    """Prevent an unexpectedly echoed JWT from entering the task log."""
    return text.replace(token, "[REDACTED]")


def run_remote_branectl(
    *,
    description: str,
    destination: str,
    ssh_options: list[str],
    token: str,
    brane_port: str,
    operation: str,
    version_id: str | None = None,
) -> int:
    """Run a worker-side branectl policy command without exposing its JWT."""
    print(f"\n[policy-lifecycle] {description}", flush=True)

    command_parts = [
        "branectl",
        "policies",
        operation,
    ]
    if version_id:
        command_parts.append(version_id)
    command_parts.extend([
        "--address",
        f"localhost:{brane_port}",
    ])
    remote_branectl = " ".join(shlex.quote(part) for part in command_parts)

    remote_command = (
        "IFS= read -r TOKEN; export TOKEN; "
        f"exec {remote_branectl}"
    )

    try:
        process = subprocess.Popen(
            ["ssh", *ssh_options, destination, remote_command],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        print(f"[policy-lifecycle] Could not start SSH: {exc}", flush=True)
        return 1

    assert process.stdin is not None
    try:
        process.stdin.write(f"{token}\n")
        process.stdin.close()
    except BrokenPipeError:
        pass

    assert process.stdout is not None
    for line in process.stdout:
        print(redact(line, token), end="", flush=True)

    return process.wait()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["list", "activate"])
    parser.add_argument("--token-path", required=True)
    parser.add_argument("--worker-host", required=True)
    parser.add_argument("--ssh-user", required=True)
    parser.add_argument("--brane-port", required=True)
    parser.add_argument("--version-id")
    args = parser.parse_args()

    token_path = Path(args.token_path)
    if not token_path.is_file():
        print("[policy-lifecycle] Selected token file does not exist.", flush=True)
        return 1

    if not args.brane_port.isdecimal() or not 1 <= int(args.brane_port) <= 65535:
        print("[policy-lifecycle] brane-chk port must be between 1 and 65535.", flush=True)
        return 1

    if args.operation == "activate":
        if not args.version_id or not VERSION_ID_PATTERN.fullmatch(args.version_id):
            print("[policy-lifecycle] Invalid policy version ID.", flush=True)
            return 1

    try:
        token = read_token(token_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[policy-lifecycle] Could not read token file: {exc}", flush=True)
        return 1

    destination = f"{args.ssh_user}@{args.worker_host}"
    ssh_options = [
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
    ]

    if args.operation == "list":
        return run_remote_branectl(
            description="Inspecting policy versions and active policy state...",
            destination=destination,
            ssh_options=ssh_options,
            token=token,
            brane_port=args.brane_port,
            operation="list",
        )

    if run_remote_branectl(
        description=f"Activating policy version {args.version_id}...",
        destination=destination,
        ssh_options=ssh_options,
        token=token,
        brane_port=args.brane_port,
        operation="activate",
        version_id=args.version_id,
    ) != 0:
        return 1

    return run_remote_branectl(
        description="Inspecting policy state after activation...",
        destination=destination,
        ssh_options=ssh_options,
        token=token,
        brane_port=args.brane_port,
        operation="list",
    )


if __name__ == "__main__":
    raise SystemExit(main())
