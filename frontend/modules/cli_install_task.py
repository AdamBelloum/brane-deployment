"""Download, atomically install, and verify the local Brane CLI binary."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path


def _run(description: str, command: list[str]) -> int:
    """Run a command and stream its combined output to the task log."""
    print(f"\n[cli-install] {description}", flush=True)

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        print(f"[cli-install] Could not start command: {exc}", flush=True)
        return 1

    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)

    return process.wait()


def _target_path() -> Path:
    """Return the conventional user-local destination for this platform."""
    if platform.system() == "Windows":
        return Path.home() / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "brane.exe"

    return Path.home() / ".local" / "bin" / "brane"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and install the Brane CLI in user-local storage."
    )
    parser.add_argument("--download-url", required=True)
    args = parser.parse_args()

    target = _target_path()
    temporary_target = target.with_name(f"{target.name}.download")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_target.unlink(missing_ok=True)

        if _run(
            f"Downloading the Brane CLI to {temporary_target}...",
            [
                "curl",
                "--fail",
                "--location",
                "--output",
                str(temporary_target),
                args.download_url,
            ],
        ) != 0:
            return 1

        if platform.system() != "Windows":
            os.chmod(temporary_target, 0o755)

        # Atomic replacement prevents a failed download from corrupting an
        # existing working binary.
        temporary_target.replace(target)

        if _run("Verifying the installed Brane CLI...", [str(target), "--version"]) != 0:
            return 1

        print(
            f"\n[cli-install] Installation succeeded: {target}\n"
            f"[cli-install] Add {target.parent} to PATH if it is not already present.",
            flush=True,
        )
        return 0

    except OSError as exc:
        print(f"[cli-install] Installation failed: {exc}", flush=True)
        return 1
    finally:
        try:
            temporary_target.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
