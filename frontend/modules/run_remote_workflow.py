#!/usr/bin/env python3
"""Select a Brane instance and submit one remote workflow."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def run_command(command: Sequence[str]) -> int:
    """Run a command, forwarding its combined output to this process."""
    print("$ " + " ".join(command), flush=True)
    try:
        result = subprocess.run(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError as exc:
        print(f"Could not start command: {exc}", file=sys.stderr, flush=True)
        return 127
    return result.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select a Brane instance and submit a remote workflow."
    )
    parser.add_argument("--instance", required=True, help="Configured Brane instance name")
    parser.add_argument("--username", required=True, help="Brane workflow username")
    parser.add_argument("--workflow", required=True, type=Path, help="Workflow .bs file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workflow = args.workflow.resolve()

    if not workflow.is_file():
        print(f"Workflow not found: {workflow}", file=sys.stderr, flush=True)
        return 2

    select_exit_code = run_command(["brane", "instance", "select", args.instance])
    if select_exit_code != 0:
        print(
            f"Instance selection failed with exit code {select_exit_code}; "
            "remote workflow was not submitted.",
            file=sys.stderr,
            flush=True,
        )
        return select_exit_code

    return run_command(
        ["brane", "workflow", "run", "--remote", args.username, str(workflow)]
    )


if __name__ == "__main__":
    raise SystemExit(main())
