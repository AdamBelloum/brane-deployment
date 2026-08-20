#!/usr/bin/env python3
"""Create a checker policy-store JWK set with distinct store/expert key IDs.

The source HMAC key values are preserved. This script changes only `kid`
metadata and writes a combined checker verification keystore.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store-secret", type=Path, required=True)
    parser.add_argument("--expert-secret", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_single_hs256_key(path: Path) -> tuple[dict, dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    keys = document.get("keys")

    if not isinstance(keys, list) or len(keys) != 1:
        raise ValueError(f"{path}: expected exactly one JWK in `keys`")

    key = keys[0]
    if key.get("kty") != "oct" or key.get("alg") != "HS256":
        raise ValueError(f"{path}: expected one HS256 symmetric JWK")

    if not isinstance(key.get("k"), str) or not key["k"]:
        raise ValueError(f"{path}: missing symmetric key material")

    return document, key


def write_json_atomic(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    args = parse_args()

    store_document, store_key = load_single_hs256_key(args.store_secret)
    expert_document, expert_key = load_single_hs256_key(args.expert_secret)

    if store_key["k"] == expert_key["k"]:
        raise ValueError(
            "Store and expert HMAC keys must remain distinct; refusing migration"
        )

    # `kid` selects the right key from the combined checker keystore.
    store_key["kid"] = "store"
    expert_key["kid"] = "expert"

    combined_document = {
        "keys": [
            store_key,
            expert_key,
        ]
    }

    write_json_atomic(args.store_secret, store_document)
    write_json_atomic(args.expert_secret, expert_document)
    write_json_atomic(args.output, combined_document)

    print(
        "Created checker verification keystore with kid=store and kid=expert"
    )


if __name__ == "__main__":
    main()
