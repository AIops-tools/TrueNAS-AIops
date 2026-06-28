"""ZFS pool operations for TrueNAS SCALE.

Read ops over ``/pool``; the one mutating op (``scrub_start``) maps to
``POST /pool/scrub/run``. Returns are high-signal summaries. All API text is
sanitized before reaching the caller.

PREVIEW: endpoint paths are modelled against the documented TrueNAS SCALE REST
v2.0 API and are mock-validated only — verify against a live system.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.ops._util import as_list, s


def _pool_summary(pool: dict) -> dict:
    """Reduce a pool record to a high-signal summary."""
    return {
        "id": pool.get("id"),
        "name": s(pool.get("name"), 128),
        "status": s(pool.get("status"), 32),
        "healthy": pool.get("healthy"),
        "size": pool.get("size"),
        "allocated": pool.get("allocated"),
        "free": pool.get("free"),
    }


def list_pools(conn: Any) -> list[dict]:
    """[READ] List ZFS pools with id, name, status, health, capacity."""
    return [_pool_summary(p) for p in as_list(conn.get("/pool"))]


def get_pool(conn: Any, pool_id: str) -> dict:
    """[READ] Return detail for a single pool by id."""
    pool = conn.get(f"/pool/id/{pool_id}")
    summary = _pool_summary(pool if isinstance(pool, dict) else {})
    if isinstance(pool, dict):
        summary["path"] = s(pool.get("path"), 256)
        summary["encrypt"] = pool.get("encrypt")
    return summary


def pool_status(conn: Any, pool_id: str) -> dict:
    """[READ] Return the health/scan status of a single pool (topology summary)."""
    pool = conn.get(f"/pool/id/{pool_id}")
    if not isinstance(pool, dict):
        return {}
    scan = pool.get("scan") or {}
    topology = pool.get("topology") or {}
    return {
        "id": pool.get("id"),
        "name": s(pool.get("name"), 128),
        "status": s(pool.get("status"), 32),
        "healthy": pool.get("healthy"),
        "scan": {
            "function": s(scan.get("function"), 32) if isinstance(scan, dict) else "",
            "state": s(scan.get("state"), 32) if isinstance(scan, dict) else "",
            "percentage": scan.get("percentage") if isinstance(scan, dict) else None,
        },
        "dataVdevs": len(topology.get("data", [])) if isinstance(topology, dict) else None,
    }


def scrub_status(conn: Any, pool_id: str) -> dict:
    """[READ] Return the current scrub scan state for a pool."""
    pool = conn.get(f"/pool/id/{pool_id}")
    scan = pool.get("scan") or {} if isinstance(pool, dict) else {}
    if not isinstance(scan, dict):
        scan = {}
    return {
        "id": pool.get("id") if isinstance(pool, dict) else None,
        "function": s(scan.get("function"), 32),
        "state": s(scan.get("state"), 32),
        "percentage": scan.get("percentage"),
        "errors": scan.get("errors"),
        "startTime": s(scan.get("start_time"), 64),
        "endTime": s(scan.get("end_time"), 64),
    }


def pool_capacity(conn: Any) -> list[dict]:
    """[READ] Capacity summary per pool: size/allocated/free and used percent."""
    rows = []
    for p in as_list(conn.get("/pool")):
        size = p.get("size")
        allocated = p.get("allocated")
        used_pct = None
        if isinstance(size, (int, float)) and size and isinstance(allocated, (int, float)):
            used_pct = round(allocated / size * 100, 1)
        rows.append(
            {
                "name": s(p.get("name"), 128),
                "status": s(p.get("status"), 32),
                "healthy": p.get("healthy"),
                "size": size,
                "allocated": allocated,
                "free": p.get("free"),
                "usedPercent": used_pct,
            }
        )
    return rows


def scrub_start(conn: Any, pool_name: str) -> dict:
    """[WRITE] Start a scrub on a pool (medium risk). Captures prior scan state.

    Maps to ``POST /pool/scrub/run`` with the pool name. A scrub is a
    non-destructive integrity check; there is no clean inverse beyond cancelling
    it, so no undo descriptor is recorded.
    """
    prior = {}
    try:
        for p in as_list(conn.get("/pool")):
            if p.get("name") == pool_name:
                scan = p.get("scan") or {}
                prior = {"state": s(scan.get("state"), 32)} if isinstance(scan, dict) else {}
                break
    except Exception:  # noqa: BLE001 — advisory context only
        prior = {}
    conn.post("/pool/scrub/run", json={"name": pool_name})
    return {"pool": s(pool_name, 128), "action": "scrub_start", "priorScan": prior}
