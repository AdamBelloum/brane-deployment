"""Run one policy operation through the deployed checker network namespace."""

from __future__ import annotations

import secrets
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Sequence


SSH_OPTIONS = [
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    "-o", "StrictHostKeyChecking=accept-new",
]


def _redact(text: str, token: str) -> str:
    """Prevent an unexpectedly echoed JWT from entering task output."""
    return text.replace(token, "[REDACTED]")


def _run(
    description: str,
    command: Sequence[str],
    *,
    token: str,
    stdin_text: str | None = None,
) -> int:
    """Run a command while streaming only token-redacted output."""
    print(f"\n[policy-operation] {description}", flush=True)

    try:
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        print(f"[policy-operation] Could not start command: {exc}", flush=True)
        return 1

    if stdin_text is not None:
        assert process.stdin is not None
        try:
            process.stdin.write(stdin_text)
            process.stdin.close()
        except BrokenPipeError:
            pass

    assert process.stdout is not None
    for line in process.stdout:
        print(_redact(line, token), end="", flush=True)

    return process.wait()


def _remote_command(*arguments: str) -> str:
    """Create one shell-safe command for the remote SSH login shell."""
    return " ".join(shlex.quote(argument) for argument in arguments)


def run_policy_operation(
    *,
    token: str,
    worker_host: str,
    ssh_user: str,
    domain_id: str,
    node_config: str,
    checker_port: str,
    operation: str,
    payload: str = "",
    local_policy_path: Path | None = None,
) -> int:
    """Use the same staged-runner model as brane_helper_policy.sh."""
    destination = f"{ssh_user}@{worker_host}"
    nonce = secrets.token_hex(12)
    remote_directory = "/tmp/brane_policy"
    remote_token = f"{remote_directory}/token-{nonce}.jwt"
    remote_runner = f"{remote_directory}/runner-{nonce}.sh"
    remote_policy = ""

    repository_root = Path(__file__).resolve().parents[2]
    local_runner = repository_root / "scripts" / "brane_policy_remote_runner.sh"

    if not local_runner.is_file():
        print(
            "[policy-operation] Canonical policy runner is unavailable: "
            f"{local_runner}",
            flush=True,
        )
        return 1

    if operation not in {"add", "list", "activate"}:
        print(f"[policy-operation] Unsupported operation: {operation}", flush=True)
        return 1

    checker_container = f"brane-chk-{domain_id}"
    checker_address = f"127.0.0.1:{checker_port}"

    try:
        stage_token_command = (
            f"umask 077; mkdir -p {shlex.quote(remote_directory)}; "
            f"cat > {shlex.quote(remote_token)}; "
            f"chmod 600 {shlex.quote(remote_token)}"
        )
        if _run(
            "Staging the policy token securely on the worker...",
            ["ssh", *SSH_OPTIONS, destination, stage_token_command],
            token=token,
            stdin_text=f"{token}\n",
        ) != 0:
            return 1

        if _run(
            "Uploading the canonical policy runner...",
            [
                "scp",
                *SSH_OPTIONS,
                str(local_runner),
                f"{destination}:{remote_runner}",
            ],
            token=token,
        ) != 0:
            return 1

        runner_payload = payload
        if local_policy_path is not None:
            remote_policy = f"{remote_directory}/policy-{nonce}.eflint"
            if _run(
                "Uploading the eFLINT policy file...",
                [
                    "scp",
                    *SSH_OPTIONS,
                    str(local_policy_path),
                    f"{destination}:{remote_policy}",
                ],
                token=token,
            ) != 0:
                return 1
            runner_payload = remote_policy

        runner_command = _remote_command(
            "bash",
            remote_runner,
            checker_container,
            node_config,
            checker_address,
            remote_token,
            operation,
            runner_payload,
        )
        return _run(
            f"Running '{operation}' in {checker_container}'s network namespace...",
            ["ssh", "-tt", *SSH_OPTIONS, destination, runner_command],
            token=token,
        )
    finally:
        cleanup_paths = [remote_token, remote_runner]
        if remote_policy:
            cleanup_paths.append(remote_policy)

        cleanup_command = "rm -f -- " + " ".join(
            shlex.quote(item) for item in cleanup_paths
        )
        _run(
            "Removing temporary policy-operation files...",
            ["ssh", *SSH_OPTIONS, destination, cleanup_command],
            token=token,
        )
