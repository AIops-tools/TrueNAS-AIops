"""ZFS pool operations for TrueNAS SCALE.

Read ops over ``/pool``; the one mutating op (``scrub_start``) maps to
``POST /pool/scrub/run``. Returns are high-signal summaries. All API text is
sanitized before reaching the caller.

PREVIEW: endpoint paths are modelled against the documented TrueNAS SCALE REST
v2.0 API and are mock-validated only — verify against a live system.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.connection import _seg
from truenas_aiops.governance import opt_str
from truenas_aiops.ops._util import as_list, probe_absent, probe_failed, probe_found, s


def _pool_summary(pool: dict) -> dict:
    """Reduce a pool record to a high-signal summary."""
    return {
        "id": pool.get("id"),
        "name": opt_str(pool.get("name"), 128),
        "status": opt_str(pool.get("status"), 32),
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
    pool = conn.get(f"/pool/id/{_seg(pool_id)}")
    summary = _pool_summary(pool if isinstance(pool, dict) else {})
    if isinstance(pool, dict):
        summary["path"] = opt_str(pool.get("path"), 256)
        summary["encrypt"] = pool.get("encrypt")
    return summary


def pool_status(conn: Any, pool_id: str) -> dict:
    """[READ] Return the health/scan status of a single pool (topology summary)."""
    pool = conn.get(f"/pool/id/{_seg(pool_id)}")
    if not isinstance(pool, dict):
        return {}
    scan = pool.get("scan") or {}
    topology = pool.get("topology") or {}
    return {
        "id": pool.get("id"),
        "name": opt_str(pool.get("name"), 128),
        "status": opt_str(pool.get("status"), 32),
        "healthy": pool.get("healthy"),
        "scan": {
            "function": opt_str(scan.get("function"), 32) if isinstance(scan, dict) else None,
            "state": opt_str(scan.get("state"), 32) if isinstance(scan, dict) else None,
            "percentage": scan.get("percentage") if isinstance(scan, dict) else None,
        },
        "dataVdevs": len(topology.get("data", [])) if isinstance(topology, dict) else None,
    }


def scrub_status(conn: Any, pool_id: str) -> dict:
    """[READ] Return the current scrub scan state for a pool."""
    pool = conn.get(f"/pool/id/{_seg(pool_id)}")
    scan = pool.get("scan") or {} if isinstance(pool, dict) else {}
    if not isinstance(scan, dict):
        scan = {}
    return {
        "id": pool.get("id") if isinstance(pool, dict) else None,
        "function": opt_str(scan.get("function"), 32),
        "state": opt_str(scan.get("state"), 32),
        "percentage": scan.get("percentage"),
        "errors": scan.get("errors"),
        "startTime": opt_str(scan.get("start_time"), 64),
        "endTime": opt_str(scan.get("end_time"), 64),
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
                "name": opt_str(p.get("name"), 128),
                "status": opt_str(p.get("status"), 32),
                "healthy": p.get("healthy"),
                "size": size,
                "allocated": allocated,
                "free": p.get("free"),
                "usedPercent": used_pct,
            }
        )
    return rows


def _prior_scan(conn: Any, pool_name: str) -> dict:
    """BEFORE-state probe for a pool's scan status, as a three-outcome envelope.

    Returns ``probe_found`` / ``probe_absent`` / ``probe_failed`` — see
    :mod:`truenas_aiops.ops._util`.

    This used to collapse three different facts into a bare ``{}``: the pool was
    not in ``/pool``, the pool was there but reported no ``scan`` block, and
    ``/pool`` could not be read at all. The middle one is the dangerous
    collapse — "this pool has never been scrubbed" and "we could not tell" read
    identically, and the first is exactly the state an operator starts a scrub
    to change. ``found=false`` now means the pool itself was not listed, which
    is worth noticing before the POST that follows.
    """
    try:
        rows = as_list(conn.get("/pool"))
    except Exception as exc:  # noqa: BLE001 — reported, never silently swallowed
        return probe_failed(exc)
    for p in rows:
        if p.get("name") == pool_name:
            scan = p.get("scan")
            # A pool with no scan block has genuinely never been scrubbed: the
            # probe succeeded, so this is a real null, not an unknown.
            state = opt_str(scan.get("state"), 32) if isinstance(scan, dict) else None
            return probe_found({"state": state})
    return probe_absent()


def scrub_start(conn: Any, pool_name: str) -> dict:
    """[WRITE] Start a scrub on a pool (medium risk). Captures prior scan state.

    Maps to ``POST /pool/scrub/run`` with the pool name. A scrub is a
    non-destructive integrity check; there is no clean inverse beyond cancelling
    it, so no undo descriptor is recorded.

    ``priorScan`` is a three-outcome envelope
    ``{"found": bool | null, "state": {...} | null, "error": str | null}``.
    ``found=null`` with an ``error`` means the prior scan state could not be
    read — the scrub was still started; only the BEFORE record is missing.
    """
    prior = _prior_scan(conn, pool_name)
    conn.post("/pool/scrub/run", json={"name": pool_name})
    return {"pool": s(pool_name, 128), "action": "scrub_start", "priorScan": prior}
