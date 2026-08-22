#!/usr/bin/env python3
"""Select a checksum-locked Brane release and reset a changed deployment."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import certifi

REPOSITORY = "BraneFramework/brane"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=100"

REQUIRED_ASSETS = (
    "brane-linux-x86_64",
    "branectl-linux-x86_64",
    "branelet-linux-x86_64",
    "central-instance-x86_64.tar.gz",
    "worker-instance-x86_64.tar.gz",
)

# Generated control-node state only. Repository source directories, such as
# packages/, certs/, datasets/, policies/, and policy_tokens/, are preserved.
LOCAL_GENERATED_PATHS = (
    "artifacts/certs",
    "artifacts/release-cache",
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def repository_root() -> Path:
    root = Path(__file__).resolve().parent.parent
    if not (root / "group_vars" / "all.yml").is_file():
        fail(f"Cannot locate group_vars/all.yml beneath {root}")
    return root


def github_releases() -> list[dict[str, Any]]:
    releases: list[dict[str, Any]] = []
    url: str | None = API_URL

    while url:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "brane-deployment-release-selector",
        }
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(
                request,
                timeout=30,
                context=ssl.create_default_context(cafile=certifi.where()),
            ) as response:
                payload = json.load(response)
                releases.extend(payload)

                link_header = response.headers.get("Link", "")
                match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
                url = match.group(1) if match else None
        except urllib.error.HTTPError as error:
            if error.code == 403:
                fail(
                    "GitHub API request was rejected or rate-limited. "
                    "Set GITHUB_TOKEN and retry if this persists."
                )
            fail(f"GitHub API returned HTTP {error.code}.")
        except urllib.error.URLError as error:
            fail(f"Cannot reach the GitHub API: {error.reason}")

    return releases


def asset_map(release: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {asset["name"]: asset for asset in release.get("assets", [])}


def incompatibility(release: dict[str, Any]) -> list[str]:
    assets = asset_map(release)
    missing = [name for name in REQUIRED_ASSETS if name not in assets]
    missing_digests = [
        name
        for name in REQUIRED_ASSETS
        if name in assets
        and not str(assets[name].get("digest") or "").startswith("sha256:")
    ]

    problems: list[str] = []
    if missing:
        problems.append("missing assets: " + ", ".join(missing))
    if missing_digests:
        problems.append("missing SHA-256 digests: " + ", ".join(missing_digests))
    return problems


def current_tag(all_yml: Path) -> str:
    text = all_yml.read_text()
    match = re.search(
        r"(?ms)^brane_release:\n(?:^[ \t].*\n)*?^[ \t]*tag:\s*[\"']?([^\"'\s#]+)",
        text,
    )
    if not match:
        fail("Cannot read brane_release.tag from group_vars/all.yml.")
    return match.group(1)


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def locked_release_block(release: dict[str, Any]) -> str:
    assets = asset_map(release)
    lines = [
        "brane_release:",
        f"  tag: {yaml_quote(release['tag_name'])}",
        f"  published_at: {yaml_quote(release.get('published_at') or '')}",
        f"  target_commitish: {yaml_quote(release.get('target_commitish') or '')}",
        "  assets:",
    ]

    for name in REQUIRED_ASSETS:
        asset = assets[name]
        digest = str(asset["digest"]).removeprefix("sha256:")
        lines.extend(
            [
                f"    {name}:",
                f"      url: {yaml_quote(asset['browser_download_url'])}",
                f"      sha256: {yaml_quote(digest)}",
            ]
        )

    return "\n".join(lines) + "\n"


def update_release_lock(all_yml: Path, release: dict[str, Any]) -> None:
    text = all_yml.read_text()
    replacement = locked_release_block(release)

    updated, replacements = re.subn(
        r"(?ms)^brane_release:\n.*?(?=^# Images are loaded from the locked archives)",
        replacement,
        text,
        count=1,
    )
    if replacements != 1:
        fail("Could not replace exactly one brane_release block in group_vars/all.yml.")

    temporary = all_yml.with_suffix(".yml.tmp")
    temporary.write_text(updated)
    temporary.replace(all_yml)


def remove_local_generated_state(root: Path) -> None:
    for relative_path in LOCAL_GENERATED_PATHS:
        path = root / relative_path
        if path.is_dir():
            shutil.rmtree(path)
            print(f"Removed local generated directory: {relative_path}")
        elif path.exists():
            path.unlink()
            print(f"Removed local generated file: {relative_path}")


def run_remote_cleanup(root: Path) -> None:
    command = [
        "ansible-playbook",
        "-i",
        "inventories/production/hosts.ini",
        "site.yml",
        "--tags",
        "cleanup",
    ]
    print("\nRunning remote Brane cleanup:")
    print("  " + " ".join(command))
    result = subprocess.run(command, cwd=root)
    if result.returncode != 0:
        fail(
            "Cleanup failed. group_vars/all.yml was not changed; "
            "resolve the failure before selecting a new release."
        )


def release_status(release: dict[str, Any]) -> str:
    problems = incompatibility(release)
    if problems:
        return "INCOMPATIBLE — " + "; ".join(problems)
    if release.get("prerelease"):
        return "DEPLOYABLE PRE-RELEASE"
    return "DEPLOYABLE"


def choose_release(releases: list[dict[str, Any]]) -> dict[str, Any]:
    print("\nAvailable Brane releases")
    print("=" * 100)
    for index, release in enumerate(releases, start=1):
        published = release.get("published_at") or "unknown publication date"
        name = release.get("name") or release["tag_name"]
        print(
            f"{index:>2}. {release['tag_name']:<18} "
            f"{published[:10]:<12} {release_status(release)}"
        )
        print(f"    {name}")

    while True:
        choice = input("\nChoose a release number (or q to quit): ").strip().lower()
        if choice in {"q", "quit"}:
            raise SystemExit(0)

        try:
            selected = releases[int(choice) - 1]
        except (ValueError, IndexError):
            print("Enter one of the displayed release numbers.")
            continue

        problems = incompatibility(selected)
        if problems:
            print(
                f"{selected['tag_name']} cannot be selected for this deployment:\n"
                + "\n".join(f"  - {problem}" for problem in problems)
            )
            continue

        return selected


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select and checksum-lock a deployable Brane release."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the release lock that would be written, without cleanup or edits.",
    )
    arguments = parser.parse_args()

    root = repository_root()
    all_yml = root / "group_vars" / "all.yml"
    old_tag = current_tag(all_yml)

    print(f"Repository:       {root}")
    print(f"Current lock tag: {old_tag}")
    print("Retrieving releases from the GitHub Releases API...")

    selected = choose_release(github_releases())
    new_tag = selected["tag_name"]

    print(f"\nSelected release: {new_tag}")

    if new_tag == old_tag:
        print(
            "The selected release already matches group_vars/all.yml. "
            "No cleanup or configuration change was performed."
        )
        return

    if arguments.dry_run:
        print(
            "\nDRY RUN: no cleanup and no configuration change will be performed.\n"
            "The replacement brane_release lock would be:\n"
        )
        print(locked_release_block(selected), end="")
        return

    if selected.get("prerelease"):
        print(
            "\nWARNING: This is a pre-release or mutable release tag. "
            "The selected asset digests will nevertheless be recorded in all.yml."
        )

    print(
        "\nA version change requires a clean Brane deployment reset.\n"
        "The reset removes Brane containers, Compose volumes, Brane service images,\n"
        "generated installation directories, downloaded release archives, and local\n"
        "generated deployment state. It preserves repository source, inventories,\n"
        "SSH configuration, packages/, certs/, datasets/, policies/, and policy_tokens/.\n"
        f"\nCurrent tag:  {old_tag}\nSelected tag: {new_tag}"
    )
    confirmation = input("\nType CLEAN to continue, or press Enter to cancel: ").strip()
    if confirmation != "CLEAN":
        print("Cancelled. No cleanup and no configuration change was performed.")
        return

    run_remote_cleanup(root)
    remove_local_generated_state(root)
    update_release_lock(all_yml, selected)

    print(
        f"\nRelease lock updated: {old_tag} -> {new_tag}\n"
        "The deployment is clean. Run the normal infrastructure deployment next:\n"
        "  ansible-playbook -i inventories/production/hosts.ini site.yml"
    )


if __name__ == "__main__":
    main()
