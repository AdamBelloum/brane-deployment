"""Generate a policy-manager token on its domain worker without logging its JWT."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SAFE_DOMAIN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SSH_OPTIONS = [
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    "-o", "StrictHostKeyChecking=accept-new",
]


def validate(value: str, pattern: re.Pattern[str], label: str) -> str:
    """Validate an argument that is used in a remote command or filename."""
    if not pattern.fullmatch(value):
        raise ValueError(f"Invalid {label}.")
    return value


def normalize_token_output(output: str) -> dict:
    """Convert raw or JSON token-file content into the stored JSON representation."""
    output = output.strip()
    if not output:
        raise ValueError("The generated token file is empty.")

    try:
        token_data = json.loads(output)
    except json.JSONDecodeError:
        token_data = {"token": output}

    if not isinstance(token_data, dict):
        raise ValueError("The generated token data is not a JSON object.")

    token = token_data.get("token") or token_data.get("access_token")
    if token is None and token_data:
        token = next(iter(token_data.values()))

    if (
        not isinstance(token, str)
        or not token.strip()
        or "\n" in token
        or "\r" in token
    ):
        raise ValueError("The generated token data contains no usable token.")

    return token_data


def write_token_file(
    *,
    token_dir: Path,
    manager_name: str,
    domain_id: str,
    token_data: dict,
) -> Path:
    """Atomically save a token file with owner-only permissions."""
    token_dir.mkdir(parents=True, exist_ok=True)
    token_dir.chmod(0o700)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = token_dir / f"policy_token_{manager_name}_{domain_id}_{timestamp}.json"
    payload = (json.dumps(token_data, indent=2) + "\n").encode("utf-8")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".policy_token_",
        suffix=".tmp",
        dir=token_dir,
        text=False,
    )
    temporary_path = Path(temporary_name)

    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        if destination.exists():
            raise FileExistsError(
                "A token file with this timestamp already exists; please retry."
            )

        os.replace(temporary_path, destination)
        destination.chmod(0o600)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return destination


def resolve_worker(inventory: Path, worker_alias: str) -> tuple[str, str]:
    """Resolve the SSH host and user exactly from the selected inventory host."""
    result = subprocess.run(
        ["ansible-inventory", "-i", str(inventory), "--host", worker_alias],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"Could not resolve inventory host '{worker_alias}'.")

    try:
        host_data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Inventory returned invalid host data.") from exc

    worker_host = host_data.get("ansible_host")
    worker_user = host_data.get("ansible_user")
    if not isinstance(worker_host, str) or not isinstance(worker_user, str):
        raise ValueError(
            f"Inventory host '{worker_alias}' has no ansible_host or ansible_user."
        )
    if not worker_host or not worker_user:
        raise ValueError(
            f"Inventory host '{worker_alias}' has no ansible_host or ansible_user."
        )

    return worker_host, worker_user


def quiet_run(
    command: list[str],
    *,
    timeout: int,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Capture subprocess output so token-like data never enters task logs."""
    return subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def cleanup_remote_token(destination: str, remote_token: str) -> None:
    """Best-effort cleanup; no remote output is exposed in task logs."""
    try:
        quiet_run(
            [
                "ssh",
                *SSH_OPTIONS,
                destination,
                f"rm -f -- {shlex.quote(remote_token)}",
            ],
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def generate_remote_token(
    *,
    destination: str,
    manager_name: str,
    domain_id: str,
    validity: str,
    remote_token: str,
) -> None:
    """Ask the selected worker to sign a token with its deployed policy secret."""
    remote_command = shlex.join(
        [
            "bash",
            "-s",
            "--",
            manager_name,
            domain_id,
            validity,
            remote_token,
        ]
    )
    remote_script = """\
set -eu
manager_name="$1"
domain_id="$2"
validity="$3"
token_path="$4"

umask 077
cd "$HOME/brane-worker"
"$HOME/.local/bin/branectl" generate policy_token \
    "$manager_name" "$domain_id" "$validity" \
    --secret-path ./config/secrets/policy_expert_secret.json \
    --path "$token_path"
chmod 600 "$token_path"
"""

    result = quiet_run(
        ["ssh", *SSH_OPTIONS, destination, remote_command],
        timeout=45,
        input_text=remote_script,
    )
    if result.returncode != 0:
        raise RuntimeError("The selected worker could not generate a policy token.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manager-name", required=True)
    parser.add_argument("--domain-id", required=True)
    parser.add_argument("--worker-alias", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--validity", required=True)
    parser.add_argument("--token-dir", required=True)
    args = parser.parse_args()

    temporary_download: Path | None = None
    remote_token = ""
    destination = ""

    try:
        manager_name = validate(args.manager_name, SAFE_NAME, "policy manager name")
        domain_id = validate(args.domain_id, SAFE_DOMAIN_ID, "domain ID")
        worker_alias = validate(args.worker_alias, SAFE_NAME, "worker inventory host")

        if (
            not args.validity
            or len(args.validity) > 32
            or any(character.isspace() for character in args.validity)
        ):
            raise ValueError("Validity must be non-empty and contain no whitespace.")

        inventory = Path(args.inventory)
        if not inventory.is_file():
            raise ValueError("The configured Ansible inventory does not exist.")

        token_dir = Path(args.token_dir)
        token_dir.mkdir(parents=True, exist_ok=True)
        token_dir.chmod(0o700)

        worker_host, worker_user = resolve_worker(inventory, worker_alias)
        destination = f"{worker_user}@{worker_host}"
        remote_token = (
            f"/tmp/brane-policy-token-{manager_name}-"
            f"{secrets.token_hex(12)}.json"
        )

        print(
            f"[policy-token] Generating a token on inventory worker '{worker_alias}'...",
            flush=True,
        )
        generate_remote_token(
            destination=destination,
            manager_name=manager_name,
            domain_id=domain_id,
            validity=args.validity,
            remote_token=remote_token,
        )

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".policy_token_download_",
            suffix=".tmp",
            dir=token_dir,
            text=False,
        )
        os.close(descriptor)
        temporary_download = Path(temporary_name)
        temporary_download.chmod(0o600)

        download = quiet_run(
            [
                "scp",
                *SSH_OPTIONS,
                f"{destination}:{remote_token}",
                str(temporary_download),
            ],
            timeout=30,
        )
        if download.returncode != 0:
            raise RuntimeError("Could not download the generated policy token.")

        token_data = normalize_token_output(
            temporary_download.read_text(encoding="utf-8")
        )
        saved_token = write_token_file(
            token_dir=token_dir,
            manager_name=manager_name,
            domain_id=domain_id,
            token_data=token_data,
        )
    except (
        OSError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(f"[policy-token] Token generation failed: {exc}", flush=True)
        return 1
    finally:
        if temporary_download is not None:
            temporary_download.unlink(missing_ok=True)
        if destination and remote_token:
            cleanup_remote_token(destination, remote_token)

    print(
        f"[policy-token] Token saved securely as {saved_token.name}.",
        flush=True,
    )
    print(
        "[policy-token] Download it only through an approved secure channel; "
        "the token value is intentionally not shown in task logs.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
