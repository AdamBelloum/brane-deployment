"""Non-blocking local subprocess execution for frontend operations."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Sequence

from modules import task_store


def _monitor_process(
    process: subprocess.Popen,
    task: dict,
    lock_name: str | None,
) -> None:
    """Persist task completion without using Streamlit APIs."""
    try:
        exit_code = process.wait()
        status = "succeeded" if exit_code == 0 else "failed"
        task_store.append_log(task, f"\n[frontend] Process exited with code {exit_code}.\n")
        task_store.update_task(
            task,
            status=status,
            exit_code=exit_code,
            finished_at=task_store.now(),
        )
    except Exception as exc:  # Defensive path: task reporting must not crash the UI.
        task_store.append_log(task, f"\n[frontend] Task monitor failed: {exc}\n")
        task_store.update_task(task, status="interrupted", finished_at=task_store.now())
    finally:
        if lock_name:
            task_store.release_lock(lock_name, task["id"])


def start_task(
    *,
    role: str,
    operation: str,
    label: str,
    command: Sequence[str],
    cwd: str | Path,
    metadata: dict | None = None,
    lock_name: str | None = None,
) -> tuple[dict | None, str | None]:
    """Start a local command without blocking Streamlit.

    ``command`` must be an argument list. Do not concatenate user input into a
    shell command string.
    """
    task = task_store.create_task(
        role=role,
        operation=operation,
        label=label,
        metadata=metadata,
    )

    if lock_name and not task_store.acquire_lock(lock_name, task["id"]):
        task_store.append_log(task, "[frontend] Another exclusive operation is already running.\n")
        task_store.update_task(task, status="failed", finished_at=task_store.now())
        active_lock = task_store.read_lock(lock_name)
        active_task_id = active_lock.get("task_id", "unknown") if active_lock else "unknown"
        return None, f"Another infrastructure deployment is active (task: {active_task_id})."

    try:
        log_handle = Path(task["log_path"]).open("a", encoding="utf-8", buffering=1)
        log_handle.write("[frontend] Starting: " + " ".join(command) + "\n\n")
        process = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        # Popen owns a duplicate of this descriptor; the parent must close its copy.
        log_handle.close()
    except (OSError, subprocess.SubprocessError) as exc:
        if lock_name:
            task_store.release_lock(lock_name, task["id"])
        task_store.append_log(task, f"[frontend] Could not start task: {exc}\n")
        task_store.update_task(task, status="failed", finished_at=task_store.now())
        return None, f"Could not start operation: {exc}"

    task_store.update_task(
        task,
        status="running",
        started_at=task_store.now(),
        pid=process.pid,
    )
    threading.Thread(
        target=_monitor_process,
        args=(process, task, lock_name),
        name=f"brane-task-{task['id']}",
        daemon=True,
    ).start()
    return task, None
