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


def _resolve_pool(conn: Any, pool_id: str) -> dict:
    """Fetch a pool by numeric id **or** by name.

    ``/pool/id/{id}`` takes TrueNAS's numeric id, so passing a pool NAME —
    which is what every caller actually has — 404s with "the id may be stale",
    sending the operator to hunt a staleness problem that does not exist. That
    is not hypothetical: this tool's own pool-health RCA reports
    ``resource: tank`` and advises ``Inspect 'pool status tank'``, so following
    its advice verbatim failed on a real appliance (TrueNAS 25.04.2.1,
    2026-08-02). An agent reading a finding has the name, never the id.

    A numeric id is still tried first, so nothing about existing callers
    changes; the name lookup is the fallback.
    """
    if str(pool_id).isdigit():
        pool = conn.get(f"/pool/id/{_seg(pool_id)}")
        if isinstance(pool, dict):
            return pool
    for candidate in as_list(conn.get("/pool")):
        if isinstance(candidate, dict) and str(candidate.get("name")) == str(pool_id):
            return candidate
    # Neither an id nor a known name: let the API produce the canonical 404.
    pool = conn.get(f"/pool/id/{_seg(pool_id)}")
    return pool if isinstance(pool, dict) else {}


def get_pool(conn: Any, pool_id: str) -> dict:
    """[READ] Return detail for a single pool by id **or** name."""
    pool = _resolve_pool(conn, pool_id)
    summary = _pool_summary(pool)
    if pool:
        # Only decorate a record that actually came back. An empty resolve means
        # the response was not a pool at all, and answering with a full skeleton
        # of nulls would read as "the pool exists and has no path".
        summary["path"] = opt_str(pool.get("path"), 256)
        summary["encrypt"] = pool.get("encrypt")
    return summary


#: ZFS member states that mean this device is not carrying data right now.
UNHEALTHY_MEMBER_STATES = frozenset(
    {"REMOVED", "FAULTED", "DEGRADED", "OFFLINE", "UNAVAIL"}
)


def _members(topology: Any) -> list[dict]:
    """Flatten a pool's topology into one row per leaf device.

    A degraded pool's first question is *which disk*, and the answer is only in
    ``topology``. Each row names the device, its ZFS state, and its error
    counters, so the caller never has to walk the tree itself.
    """
    rows: list[dict] = []
    if not isinstance(topology, dict):
        return rows
    for group_name, group in topology.items():
        for vdev in group if isinstance(group, list) else []:
            if not isinstance(vdev, dict):
                continue
            children = vdev.get("children") or []
            leaves = children if isinstance(children, list) and children else [vdev]
            for leaf in leaves:
                if not isinstance(leaf, dict):
                    continue
                stats = leaf.get("stats") if isinstance(leaf.get("stats"), dict) else {}
                rows.append({
                    "group": opt_str(group_name, 32),
                    "vdev": opt_str(vdev.get("type"), 32),
                    # A REMOVED member reports disk=null on a real appliance —
                    # the device is gone, so there is no name to give. Absent
                    # stays absent rather than becoming "" (null-vs-empty).
                    "device": opt_str(leaf.get("disk"), 128),
                    "guid": opt_str(leaf.get("guid"), 64),
                    "status": opt_str(leaf.get("status"), 32),
                    "readErrors": stats.get("read_errors"),
                    "writeErrors": stats.get("write_errors"),
                    "checksumErrors": stats.get("checksum_errors"),
                })
    return rows


def unhealthy_members(topology: Any) -> list[dict]:
    """Members whose ZFS state means they are not carrying data."""
    return [m for m in _members(topology)
            if (m.get("status") or "") in UNHEALTHY_MEMBER_STATES]


def pool_status(conn: Any, pool_id: str) -> dict:
    """[READ] Return the health/scan status of a single pool (topology summary).

    ``pool_id`` accepts the numeric id **or** the pool name — see
    :func:`_resolve_pool`.
    """
    pool = _resolve_pool(conn, pool_id)
    if not pool:
        return {}
    scan = pool.get("scan") or {}
    topology = pool.get("topology") or {}
    members = _members(topology)
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
        # Without these a DEGRADED verdict is unactionable: the operator is told
        # the pool is broken and left to find the failed device by hand.
        "members": members,
        "unhealthyMembers": [m for m in members
                             if (m.get("status") or "") in UNHEALTHY_MEMBER_STATES],
    }


def scrub_status(conn: Any, pool_id: str) -> dict:
    """[READ] Return the current scrub scan state for a pool (id or name)."""
    pool = _resolve_pool(conn, pool_id)
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
    # threshold=0 is REQUIRED, not a tuning knob. TrueNAS documents
    # pool.scrub.run as "initiate a scrub ... IF the last scrub was performed
    # more than `threshold` days before", and its default is 35 — so omitting it
    # means a pool scanned within the last 35 days is SILENTLY SKIPPED while the
    # call still succeeds. Verified against TrueNAS SCALE 25.04.2.1 (2026-08-02):
    # run(tank, 35) returned null and left the scan state untouched; run(tank, 0)
    # returned the same null and actually scrubbed. An operator asking to scrub a
    # pool they are worried about was being told it started when nothing ran.
    # The day-threshold exists for SCHEDULED scrub tasks, not for an explicit
    # "scrub this pool now".
    conn.post("/pool/scrub/run", json={"name": pool_name, "threshold": 0})
    return {"pool": s(pool_name, 128), "action": "scrub_start", "priorScan": prior}
