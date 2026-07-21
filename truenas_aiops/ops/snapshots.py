"""ZFS snapshot operations for TrueNAS SCALE.

Read over ``/zfs/snapshot``; create maps to ``POST /zfs/snapshot``; delete maps
to ``DELETE /zfs/snapshot/id/{id}``. A snapshot id is ``dataset@name``.

Reversibility:
  * ``create_snapshot`` (medium) records an inverse ``snapshot_delete`` undo
    descriptor — the freshly-created snapshot can be safely removed.
  * ``delete_snapshot`` (high) is irreversible; it captures the snapshot's BEFORE
    state (best-effort) for the audit record but declares no undo.

PREVIEW: mock-validated only — verify endpoint paths against a live system.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.connection import _seg
from truenas_aiops.governance import opt_str
from truenas_aiops.ops._util import as_list, probe_absent, probe_failed, probe_found, s


def _snapshot_summary(snap: dict) -> dict:
    """Reduce a snapshot record to a high-signal summary."""
    props = snap.get("properties") or {}
    used = props.get("used", {}) if isinstance(props, dict) else {}
    return {
        "id": opt_str(snap.get("id"), 256),
        "name": opt_str(snap.get("name"), 256),
        "dataset": opt_str(snap.get("dataset"), 256),
        "snapshotName": opt_str(snap.get("snapshot_name"), 128),
        "used": used.get("value") if isinstance(used, dict) else None,
    }


#: Default cap on rows returned by :func:`list_snapshots`.
DEFAULT_SNAPSHOT_LIMIT = 200


def list_snapshots(
    conn: Any, dataset: str | None = None, limit: int = DEFAULT_SNAPSHOT_LIMIT
) -> dict:
    """[READ] List ZFS snapshots, optionally filtered to a single dataset.

    Returns an envelope rather than a bare list::

        {"snapshots": [...], "returned": 200, "limit": 200, "truncated": true}

    so a truncated read announces itself. A bare list cannot say "there is more"
    — the consumer has to infer it from the length happening to equal the limit,
    and a smaller local model faced with a long result tends to report that
    nothing came back at all. This matters more on TrueNAS than almost anywhere:
    a periodic snapshot task retaining hourly/daily/weekly snapshots across a
    handful of datasets produces thousands of rows.

    ``truncated`` is *measured*: the middleware returns the whole snapshot list
    in one call, so the full post-filter count is known before slicing.
    """
    requested = max(1, int(limit))
    rows = [_snapshot_summary(x) for x in as_list(conn.get("/zfs/snapshot"))]
    if dataset:
        rows = [r for r in rows if r.get("dataset") == dataset]
    return {
        "snapshots": rows[:requested],
        "returned": len(rows[:requested]),
        "limit": requested,
        "truncated": len(rows) > requested,
    }


def _find_snapshot(conn: Any, snapshot_id: str) -> dict:
    """BEFORE-state probe for one snapshot, as a three-outcome envelope.

    Returns ``probe_found`` / ``probe_absent`` / ``probe_failed`` — see
    :mod:`truenas_aiops.ops._util`.

    This used to return a bare ``{}`` both when the snapshot was not in the list
    and when the list could not be read at all. ``delete_snapshot`` is
    irreversible and declares no undo, so this envelope is the *only* surviving
    record of what was destroyed: an audit row reading ``priorState: {}`` could
    mean "we checked, it was already gone" or "we destroyed something and never
    found out what". Those are opposite facts about how much evidence exists,
    and the second must never be able to look like the first.
    """
    try:
        rows = as_list(conn.get("/zfs/snapshot"))
    except Exception as exc:  # noqa: BLE001 — reported, never silently swallowed
        return probe_failed(exc)
    for x in rows:
        if x.get("id") == snapshot_id:
            return probe_found(_snapshot_summary(x))
    return probe_absent()


def create_snapshot(conn: Any, dataset: str, name: str) -> dict:
    """[WRITE] Create a ZFS snapshot ``dataset@name`` (medium). Inverse: delete."""
    body = {"dataset": dataset, "name": name}
    result = conn.post("/zfs/snapshot", json=body)
    snap_id = result.get("id") if isinstance(result, dict) else None
    snap_id = snap_id or f"{dataset}@{name}"
    return {
        "id": s(snap_id, 256),
        "dataset": s(dataset, 256),
        "snapshotName": s(name, 128),
        "action": "create_snapshot",
    }


def delete_snapshot(conn: Any, snapshot_id: str) -> dict:
    """[WRITE] Delete a ZFS snapshot by id ``dataset@name`` (high, irreversible).

    Captures the snapshot's prior state for the audit record; declares no undo
    (a deleted snapshot cannot be reconstructed).

    ``priorState`` is a three-outcome envelope
    ``{"found": bool | null, "state": {...} | null, "error": str | null}``:
    ``found=true`` carries the summary, ``found=false`` means the snapshot was
    confirmed already gone, and ``found=null`` with an ``error`` means the
    BEFORE-state could not be read — the delete still happened, but there is no
    record of what it removed. Treat that last case as evidence missing, not as
    an empty snapshot.
    """
    prior = _find_snapshot(conn, snapshot_id)
    conn.delete(f"/zfs/snapshot/id/{_seg(snapshot_id)}")
    return {"id": s(snapshot_id, 256), "action": "delete_snapshot", "priorState": prior}
