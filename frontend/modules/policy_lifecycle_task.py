"""Background tasks for inspecting and activating domain-local policies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from policy_remote_task import run_policy_operation


DOMAIN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VERSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def read_token(token_path: Path) -> str:
    """Read a JSON-wrapped or raw JWT without displaying it."""
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["list", "activate"])
    parser.add_argument("--token-path", required=True)
    parser.add_argument("--worker-host", required=True)
    parser.add_argument("--ssh-user", required=True)
    parser.add_argument("--domain-id", required=True)
    parser.add_argument("--node-config", required=True)
    parser.add_argument("--brane-port", required=True)
    parser.add_argument("--version-id")
    args = parser.parse_args()

    token_path = Path(args.token_path)

    if not token_path.is_file():
        print("[policy-lifecycle] Selected token file does not exist.", flush=True)
        return 1
    if not DOMAIN_ID_PATTERN.fullmatch(args.domain_id):
        print("[policy-lifecycle] Invalid Brane domain ID.", flush=True)
        return 1
    if not args.brane_port.isdecimal() or not 1 <= int(args.brane_port) <= 65535:
        print("[policy-lifecycle] Checker port must be between 1 and 65535.", flush=True)
        return 1
    if args.operation == "activate" and (
        not args.version_id or not VERSION_ID_PATTERN.fullmatch(args.version_id)
    ):
        print("[policy-lifecycle] Invalid policy version ID.", flush=True)
        return 1

    try:
        token = read_token(token_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[policy-lifecycle] Could not read token file: {exc}", flush=True)
        return 1

    common = {
        "token": token,
        "worker_host": args.worker_host,
        "ssh_user": args.ssh_user,
        "domain_id": args.domain_id,
        "node_config": args.node_config,
        "checker_port": args.brane_port,
    }

    if args.operation == "list":
        return run_policy_operation(operation="list", **common)

    if run_policy_operation(
        operation="activate",
        payload=args.version_id,
        **common,
    ) != 0:
        return 1

    return run_policy_operation(operation="list", **common)


if __name__ == "__main__":
    raise SystemExit(main())
