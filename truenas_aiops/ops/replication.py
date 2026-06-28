"""Replication and cloud-sync operations for TrueNAS SCALE (read-only).

Read over ``/replication`` and ``/cloudsync``. Returns high-signal summaries
of each task and its last run.

PREVIEW: mock-validated only — verify endpoint paths against a live system.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.ops._util import as_list, s


def _job_state(record: dict) -> dict:
    """Extract the embedded last-run job state, if any."""
    job = record.get("job") or {}
    if not isinstance(job, dict):
        return {}
    return {"state": s(job.get("state"), 32), "progress": (job.get("progress") or {})}


def list_replication(conn: Any) -> list[dict]:
    """[READ] List replication tasks with id, name, direction, transport, state."""
    rows = []
    for r in as_list(conn.get("/replication")):
        rows.append(
            {
                "id": r.get("id"),
                "name": s(r.get("name"), 128),
                "direction": s(r.get("direction"), 16),
                "transport": s(r.get("transport"), 16),
                "enabled": r.get("enabled"),
                "state": _job_state(r).get("state", ""),
            }
        )
    return rows


def list_cloudsync(conn: Any) -> list[dict]:
    """[READ] List cloud-sync tasks with id, description, direction, path, state."""
    rows = []
    for r in as_list(conn.get("/cloudsync")):
        rows.append(
            {
                "id": r.get("id"),
                "description": s(r.get("description"), 128),
                "direction": s(r.get("direction"), 16),
                "path": s(r.get("path"), 256),
                "enabled": r.get("enabled"),
                "state": _job_state(r).get("state", ""),
            }
        )
    return rows
