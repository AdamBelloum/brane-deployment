"""Safely upload a policy to a worker and add it through branectl.

The token is read only inside this short-lived helper. It must never be
included in persistent task metadata, task commands, or task-log output.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path


def _read_token(token_path: Path) -> str:
    """Read a supported token value without ever displaying it."""
    token_data = json.loads(token_path.read_text(encoding="utf-8"))
    if not isinstance(token_data, dict):
        raise ValueError("The token file must contain a JSON object.")

    token = token_data.get("token") or token_data.get("access_token")
    if token is None and token_data:
        token = next(iter(token_data.values()))

    if not isinstance(token, str) or not token:
        raise ValueError("The token file does not contain a usable token.")

    return token


def _redact(text: str, token: str) -> str:
    """Prevent an unexpectedly echoed token from reaching the task log."""
    return text.replace(token, "[REDACTED]")


def _run_step(
    description: str,
    command: list[str],
    token: str,
    stdin_text: str | None = None,
) -> int:
    """Run one command, streaming only redacted output to the task log.

    ``stdin_text`` is used only for secret transport. It is never logged and
    is not included in command arguments or persistent task metadata.
    """
    print(f"\n[policy-upload] {description}", flush=True)

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        print(f"[policy-upload] Could not start {description.lower()}: {exc}", flush=True)
        return 1

    if stdin_text is not None:
        assert process.stdin is not None
        try:
            process.stdin.write(stdin_text)
            process.stdin.close()
        except BrokenPipeError:
            # The remote command exited before consuming stdin. Its output and
            # return code below provide the actionable error.
            pass

    assert process.stdout is not None
    for line in process.stdout:
        print(_redact(line, token), end="", flush=True)

    return process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload and add a Brane policy safely.")
    parser.add_argument("--policy-path", required=True)
    parser.add_argument("--token-path", required=True)
    parser.add_argument("--worker-host", required=True)
    parser.add_argument("--ssh-user", required=True)
    parser.add_argument("--brane-port", required=True)
    args = parser.parse_args()

    policy_path = Path(args.policy_path)
    token_path = Path(args.token_path)

    if not policy_path.is_file():
        print("[policy-upload] Selected policy file does not exist.", flush=True)
        return 1
    if not token_path.is_file():
        print("[policy-upload] Selected token file does not exist.", flush=True)
        return 1

    try:
        token = _read_token(token_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[policy-upload] Could not read the token file: {exc}", flush=True)
        return 1

    destination = f"{args.ssh_user}@{args.worker_host}"
    ssh_options = [
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    remote_path = f"/tmp/brane_policy/{policy_path.name}"

    if _run_step(
        "Creating the remote policy directory...",
        ["ssh", *ssh_options, destination, "mkdir -p /tmp/brane_policy"],
        token,
    ) != 0:
        return 1

    if _run_step(
        "Uploading the policy file...",
        [
            "scp",
            *ssh_options,
            str(policy_path),
            f"{destination}:{remote_path}",
        ],
        token,
    ) != 0:
        return 1

    # Read the JWT over SSH stdin and expose it only as the TOKEN environment
    # variable required by branectl. The token is deliberately absent from all
    # local and remote process arguments.
    remote_command = (
        "IFS= read -r TOKEN; export TOKEN; "
        f"exec branectl policies add {shlex.quote(remote_path)} "
        f"--address {shlex.quote(f'localhost:{args.brane_port}')}"
    )
    if _run_step(
        "Adding the policy on the worker...",
        ["ssh", *ssh_options, destination, remote_command],
        token,
        stdin_text=f"{token}\n",
    ) != 0:
        return 1

    print(
        "\n[policy-upload] Policy added successfully. "
        "Copy the version ID from the output before activating it.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
