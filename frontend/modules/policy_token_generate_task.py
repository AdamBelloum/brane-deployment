"""Generate and persist a policy token without exposing its JWT in task logs."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_component(value: str, label: str) -> str:
    """Validate values used both by branectl and the output filename."""
    if not SAFE_NAME.fullmatch(value):
        raise ValueError(
            f"{label} must contain 1–64 letters, digits, dots, underscores, or hyphens."
        )
    return value


def normalize_token_output(output: str) -> dict:
    """Convert branectl output into the JSON shape consumed by Policy Manager."""
    output = output.strip()
    if not output:
        raise ValueError("branectl returned an empty token response.")

    try:
        token_data = json.loads(output)
    except json.JSONDecodeError:
        token_data = {"token": output}

    if not isinstance(token_data, dict):
        raise ValueError("branectl returned token data that is not a JSON object.")

    token = token_data.get("token") or token_data.get("access_token")
    if token is None and token_data:
        token = next(iter(token_data.values()))

    if (
        not isinstance(token, str)
        or not token.strip()
        or "\n" in token
        or "\r" in token
    ):
        raise ValueError("branectl returned no usable token value.")

    return token_data


def write_token_file(
    *,
    token_dir: Path,
    manager_name: str,
    domain_id: str,
    token_data: dict,
) -> Path:
    """Atomically persist token JSON with owner-only directory and file modes."""
    token_dir.mkdir(parents=True, exist_ok=True)
    token_dir.chmod(0o700)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"policy_token_{manager_name}_{domain_id}_{timestamp}.json"
    destination = token_dir / filename

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

        # A timestamped name avoids overwriting previously issued tokens.
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manager-name", required=True)
    parser.add_argument("--domain-id", required=True)
    parser.add_argument("--validity", required=True)
    parser.add_argument("--token-dir", required=True)
    args = parser.parse_args()

    try:
        manager_name = validate_component(args.manager_name, "Manager name")
        domain_id = validate_component(args.domain_id, "Domain ID")

        if (
            not args.validity
            or len(args.validity) > 32
            or any(character.isspace() for character in args.validity)
        ):
            raise ValueError("Validity must be a non-empty, whitespace-free value.")

        result = subprocess.run(
            [
                "branectl",
                "generate",
                "policy_token",
                manager_name,
                domain_id,
                args.validity,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            # Do not emit captured output: a failing tool must not be able to
            # leak token-like material to the persistent task log.
            print(
                "[policy-token] branectl failed to generate a token "
                f"(exit code {result.returncode}).",
                flush=True,
            )
            return 1

        token_data = normalize_token_output(result.stdout)
        destination = write_token_file(
            token_dir=Path(args.token_dir),
            manager_name=manager_name,
            domain_id=domain_id,
            token_data=token_data,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"[policy-token] Token generation failed: {exc}", flush=True)
        return 1

    print(
        f"[policy-token] Token saved securely as {destination.name}.",
        flush=True,
    )
    print(
        "[policy-token] Select the file below to download it; "
        "the token value is intentionally not shown in task logs.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
