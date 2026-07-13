"""ZFS dataset operations for TrueNAS SCALE.

Read ops over ``/pool/dataset``; the one mutating op (``create_dataset``) maps
to ``POST /pool/dataset``. Creating an empty dataset is non-destructive, so no
undo descriptor is recorded (deleting datasets is intentionally out of scope).

PREVIEW: mock-validated only — verify endpoint paths against a live system.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.connection import _seg
from truenas_aiops.ops._util import as_list, s


def _dataset_summary(ds: dict) -> dict:
    """Reduce a dataset record to a high-signal summary.

    TrueNAS nests many properties as ``{"value": ..., "rawvalue": ...}``; this
    flattens the ones we surface to their displayed value.
    """

    def _val(key: str) -> Any:
        v = ds.get(key)
        if isinstance(v, dict):
            return v.get("value")
        return v

    return {
        "id": s(ds.get("id"), 256),
        "name": s(ds.get("name"), 256),
        "type": s(ds.get("type"), 32),
        "pool": s(ds.get("pool"), 128),
        "used": _val("used"),
        "available": _val("available"),
        "mountpoint": s(ds.get("mountpoint"), 256),
    }


def list_datasets(conn: Any) -> list[dict]:
    """[READ] List ZFS datasets with id, name, type, pool, used/available."""
    return [_dataset_summary(d) for d in as_list(conn.get("/pool/dataset"))]


def get_dataset(conn: Any, dataset_id: str) -> dict:
    """[READ] Return detail for a single dataset by id (e.g. ``tank/data``)."""
    ds = conn.get(f"/pool/dataset/id/{_seg(dataset_id)}")
    return _dataset_summary(ds if isinstance(ds, dict) else {})


def create_dataset(conn: Any, name: str, pool: str | None = None) -> dict:
    """[WRITE] Create a ZFS dataset (medium risk).

    ``name`` is the full path including the pool, e.g. ``tank/projects``. Maps
    to ``POST /pool/dataset``. No undo descriptor — dataset deletion is out of
    scope (data-destroying).
    """
    body = {"name": name, "type": "FILESYSTEM"}
    result = conn.post("/pool/dataset", json=body)
    created_id = result.get("id") if isinstance(result, dict) else None
    return {
        "name": s(name, 256),
        "pool": s(pool, 128),
        "action": "create_dataset",
        "id": s(created_id, 256) if created_id else s(name, 256),
    }
