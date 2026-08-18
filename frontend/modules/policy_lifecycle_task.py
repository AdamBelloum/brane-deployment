"""Background tasks for listing and activating Brane policy versions.

JWT values are read locally and sent to the worker only over SSH stdin.
They are never placed in task metadata, command arguments, or task logs.
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
    """Read one supported JWT field without displaying its value."""
    token_data = json.loads(token_path.read_text(encoding="utf-8"))
    if not isinstance(token_data, dict):
        raise ValueError("The token file must contain a JSON object.")

    token = token_data.get("token") or token_data.get("access_token")
    if token is None and token_data:
        token = next(iter(token_data.values()))

    if not isinstance(token, str) or not token:
        raise ValueError("The token file does not contain a usable token.")

    return token


def redact(text: str, token: str) -> str:
    """Prevent an unexpectedly echoed JWT from entering the task log."""
    return text.replace(token, "[REDACTED]")


def run_remote_curl(
    *,
    description: str,
    destination: str,
    ssh_options: list[str],
    url: str,
    token: str,
    method: str | None = None,
) -> int:
    """Run Curl remotely without placing the JWT in process arguments."""
    print(f"\n[policy-lifecycle] {description}", flush=True)

    method_option = f"-X {shlex.quote(method)} " if method else ""

    # SSH stdin carries only the token. The remote shell reads it once, then
    # pipes a Curl config containing the Authorization header to `curl --config -`.
    # Neither SSH nor Curl receives the token as a command-line argument.
    remote_command = (
        "IFS= read -r TOKEN; export TOKEN; "
        "printf 'header = \"Authorization: Bearer %s\"\\n' \"$TOKEN\" "
        f"| curl --silent --show-error --fail --config - {method_option}"
        f"{shlex.quote(url)}"
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
    base_url = f"http://localhost:{args.brane_port}/v1/policies"

    if args.operation == "list":
        return run_remote_curl(
            description="Listing policy versions...",
            destination=destination,
            ssh_options=ssh_options,
            url=base_url,
            token=token,
        )

    activation_url = f"{base_url}/{args.version_id}/activate"
    if run_remote_curl(
        description=f"Activating policy version {args.version_id}...",
        destination=destination,
        ssh_options=ssh_options,
        url=activation_url,
        token=token,
        method="POST",
    ) != 0:
        return 1

    return run_remote_curl(
        description="Verifying the active policy...",
        destination=destination,
        ssh_options=ssh_options,
        url=f"{base_url}/active",
        token=token,
    )


if __name__ == "__main__":
    sys.exit(main())
