"""File-backed task records and logs for local Streamlit operations.

The frontend runs on the local control machine. Task state is kept in local
JSON and log files rather than a database, so it remains visible after normal
navigation or a browser reload.

Do not persist JWTs, private keys, or commands containing secrets in task
metadata or logs.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from modules.config import FRONTEND_RUNTIME_DIR


TASKS_DIR = FRONTEND_RUNTIME_DIR / "tasks"
LOCKS_DIR = FRONTEND_RUNTIME_DIR / "locks"
ACTIVE_STATUSES = {"queued", "running"}


def now() -> str:
    """Return a timezone-aware local timestamp for task metadata."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ensure_runtime_dirs() -> None:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)


def task_state_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.json"


def create_task(
    *,
    role: str,
    operation: str,
    label: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a queued task together with an empty log file."""
    ensure_runtime_dirs()
    task_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{operation}-{uuid4().hex[:8]}"
    log_path = TASKS_DIR / f"{task_id}.log"
    state_path = task_state_path(task_id)

    task: dict[str, Any] = {
        "id": task_id,
        "role": role,
        "operation": operation,
        "label": label,
        "status": "queued",
        "created_at": now(),
        "started_at": None,
        "finished_at": None,
        "pid": None,
        "exit_code": None,
        "log_path": str(log_path),
        "state_path": str(state_path),
        "metadata": metadata or {},
    }
    log_path.touch(exist_ok=False)
    write_task(task)
    return task


def write_task(task: dict[str, Any]) -> None:
    """Atomically write task state; readers never see partial JSON."""
    ensure_runtime_dirs()
    path = Path(task["state_path"])
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def update_task(task: dict[str, Any], **changes: Any) -> dict[str, Any]:
    task.update(changes)
    write_task(task)
    return task


def read_task(task_id: str) -> dict[str, Any] | None:
    path = task_state_path(task_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_tasks(limit: int | None = None) -> list[dict[str, Any]]:
    ensure_runtime_dirs()
    tasks: list[dict[str, Any]] = []
    for path in TASKS_DIR.glob("*.json"):
        try:
            tasks.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    tasks.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return tasks if limit is None else tasks[:limit]


def append_log(task: dict[str, Any], text: str) -> None:
    with Path(task["log_path"]).open("a", encoding="utf-8") as log_file:
        log_file.write(text)


def read_log_tail(task: dict[str, Any], max_bytes: int = 60_000) -> str:
    """Read the most recent part of a potentially large task log."""
    path = Path(task["log_path"])
    if not path.exists():
        return "Log file is not available yet."

    try:
        with path.open("rb") as log_file:
            log_file.seek(0, os.SEEK_END)
            size = log_file.tell()
            log_file.seek(max(0, size - max_bytes))
            data = log_file.read()
    except OSError as exc:
        return f"Could not read task log: {exc}"

    prefix = "… earlier log output omitted …\n" if size > max_bytes else ""
    return prefix + data.decode("utf-8", errors="replace")


def pid_is_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reconcile_task(task: dict[str, Any]) -> dict[str, Any]:
    """Handle stale state after a reload when the worker monitor is absent.

    The normal monitor records a succeeded/failed result. If a process has
    disappeared without a monitor result, the actual exit code is unknown, so
    expose the state honestly as ``interrupted``.
    """
    if task.get("status") == "running" and not pid_is_alive(task.get("pid")):
        append_log(task, "\n[frontend] Process is no longer present; final status could not be recovered.\n")
        update_task(task, status="interrupted", finished_at=now())
    return task


def lock_path(name: str) -> Path:
    return LOCKS_DIR / f"{name}.lock"


def read_lock(name: str) -> dict[str, Any] | None:
    path = lock_path(name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"task_id": "unknown"}


def acquire_lock(name: str, task_id: str) -> bool:
    """Acquire a local exclusive lock, recovering a stale known lock."""
    ensure_runtime_dirs()
    path = lock_path(name)

    existing = read_lock(name)
    if existing:
        existing_task = read_task(existing.get("task_id", ""))
        if existing_task:
            reconcile_task(existing_task)
            if existing_task.get("status") not in ACTIVE_STATUSES:
                path.unlink(missing_ok=True)
        # Unknown lock ownership is intentionally treated as active.
        if path.exists():
            return False

    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False

    with os.fdopen(descriptor, "w", encoding="utf-8") as lock_file:
        json.dump({"task_id": task_id, "created_at": now()}, lock_file)
    return True


def release_lock(name: str, task_id: str) -> None:
    path = lock_path(name)
    lock = read_lock(name)
    if lock is None or lock.get("task_id") == task_id:
        path.unlink(missing_ok=True)
