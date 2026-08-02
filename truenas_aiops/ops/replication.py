"""Replication and cloud-sync operations for TrueNAS SCALE (read-only).

Read over ``/replication`` and ``/cloudsync``. Returns high-signal summaries
of each task and its last run.

The two endpoints report a task's outcome differently, and they were verified
separately against a live appliance — do not unify them:

* ``replication`` injects a top-level ``state`` dict — ``{"state": "PENDING" |
  "RUNNING" | "FINISHED" | "ERROR" | "HOLD", "datetime", "error",
  "last_snapshot"}`` — which is present from the moment a task is created.
* ``cloudsync`` has **no** top-level state at all; its only outcome signal is
  the generic ``job`` record, whose vocabulary is ``SUCCESS``/``FAILED``.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.governance import opt_str
from truenas_aiops.ops._util import as_list


def _job_state(record: dict) -> dict:
    """Extract the embedded last-run job state, if any."""
    job = record.get("job") or {}
    if not isinstance(job, dict):
        return {}
    return {"state": opt_str(job.get("state"), 32), "progress": (job.get("progress") or {})}


def _replication_state(record: dict) -> dict:
    """A replication task's own last-run state, not the generic job's.

    Reading ``job.state`` here was wrong twice over: ``job`` is absent until a
    run has been triggered in this middleware's lifetime — so a task the
    appliance plainly calls ``PENDING`` was reported as ``null`` — and when it
    is present it speaks the job vocabulary (``SUCCESS``) rather than the
    replication one (``FINISHED``), so no value ever matched what the appliance
    and its UI show. The ``error`` sentence, which names what to fix, was
    dropped entirely.
    """
    state = record.get("state")
    if not isinstance(state, dict):
        # Defensive: a build that does not inject `state` still has the job.
        return {
            "state": _job_state(record).get("state"),
            "error": None,
            "lastSnapshot": None,
            "lastRun": None,
        }
    when = state.get("datetime")
    return {
        "state": opt_str(state.get("state"), 32),
        # The appliance's own sentence is the diagnostic ("Dataset 'tank/empty'
        # does not have any matching snapshots to replicate.") — keep it whole.
        "error": opt_str(state.get("error"), 800),
        "lastSnapshot": opt_str(state.get("last_snapshot"), 256),
        "lastRun": opt_str(
            when.get("$date") if isinstance(when, dict) else when, 64
        ),
    }


def list_replication(conn: Any) -> list[dict]:
    """[READ] List replication tasks with id, name, direction, transport, state."""
    rows = []
    for r in as_list(conn.get("/replication")):
        rows.append(
            {
                "id": r.get("id"),
                "name": opt_str(r.get("name"), 128),
                "direction": opt_str(r.get("direction"), 16),
                "transport": opt_str(r.get("transport"), 16),
                "enabled": r.get("enabled"),
                **_replication_state(r),
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
                "description": opt_str(r.get("description"), 128),
                "direction": opt_str(r.get("direction"), 16),
                "path": opt_str(r.get("path"), 256),
                "enabled": r.get("enabled"),
                "state": _job_state(r).get("state"),
            }
        )
    return rows
