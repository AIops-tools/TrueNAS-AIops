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

from truenas_aiops.ops._util import as_list, s


def _snapshot_summary(snap: dict) -> dict:
    """Reduce a snapshot record to a high-signal summary."""
    props = snap.get("properties") or {}
    used = props.get("used", {}) if isinstance(props, dict) else {}
    return {
        "id": s(snap.get("id"), 256),
        "name": s(snap.get("name"), 256),
        "dataset": s(snap.get("dataset"), 256),
        "snapshotName": s(snap.get("snapshot_name"), 128),
        "used": used.get("value") if isinstance(used, dict) else None,
    }


def list_snapshots(conn: Any, dataset: str | None = None) -> list[dict]:
    """[READ] List ZFS snapshots, optionally filtered to a single dataset."""
    rows = [_snapshot_summary(x) for x in as_list(conn.get("/zfs/snapshot"))]
    if dataset:
        rows = [r for r in rows if r.get("dataset") == dataset]
    return rows


def _find_snapshot(conn: Any, snapshot_id: str) -> dict:
    """Best-effort lookup of one snapshot record by id, or {} (advisory)."""
    try:
        for x in as_list(conn.get("/zfs/snapshot")):
            if x.get("id") == snapshot_id:
                return _snapshot_summary(x)
    except Exception:  # noqa: BLE001 — advisory context only
        return {}
    return {}


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
    """
    prior = _find_snapshot(conn, snapshot_id)
    conn.delete(f"/zfs/snapshot/id/{snapshot_id}")
    return {"id": s(snapshot_id, 256), "action": "delete_snapshot", "priorState": prior}
