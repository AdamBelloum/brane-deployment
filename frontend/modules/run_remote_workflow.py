#!/usr/bin/env python3
"""Guard against remote workflow submission while validation is paused."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "Remote workflow submission is paused pending Brane developer "
        "clarification of planner/checker-selection behaviour.",
        file=sys.stderr,
        flush=True,
    )
    print(
        "No Brane instance was selected and no workflow was submitted.",
        file=sys.stderr,
        flush=True,
    )
    return 75


if __name__ == "__main__":
    raise SystemExit(main())
