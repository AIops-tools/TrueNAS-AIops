"""Environment health overview for TrueNAS SCALE (read-only).

A single high-signal summary an agent can call first: pool capacity and health,
active alerts by level, and how many services are running. Built by fanning out
over the other read ops; each sub-query is best-effort so one failing collection
never blanks the whole picture.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.ops import alerts as alert_ops
from truenas_aiops.ops import pools as pool_ops
from truenas_aiops.ops import services as service_ops

# Pools at or above this used-% are flagged as "near full".
_NEAR_FULL_PERCENT = 80.0


def _pool_health(conn: Any) -> dict:
    try:
        rows = pool_ops.pool_capacity(conn)
    except Exception as exc:  # noqa: BLE001 — report as partial
        return {"error": str(exc)[:200]}
    unhealthy = [r["name"] for r in rows if r.get("healthy") is False]
    near_full = [
        {"name": r.get("name"), "usedPercent": r.get("usedPercent")}
        for r in rows
        if isinstance(r.get("usedPercent"), (int, float))
        and r["usedPercent"] >= _NEAR_FULL_PERCENT
    ]
    return {"total": len(rows), "unhealthy": unhealthy, "nearFull": near_full}


def _alert_health(conn: Any) -> dict:
    try:
        rows = alert_ops.list_alerts(conn)
    except Exception as exc:  # noqa: BLE001 — report as partial
        return {"error": str(exc)[:200]}
    by_level: dict[str, int] = {}
    for a in rows:
        key = (a.get("level") or "UNKNOWN") or "UNKNOWN"
        by_level[key] = by_level.get(key, 0) + 1
    return {"total": len(rows), "byLevel": by_level}


def _service_health(conn: Any) -> dict:
    try:
        rows = service_ops.list_services(conn)
    except Exception as exc:  # noqa: BLE001 — report as partial
        return {"error": str(exc)[:200]}
    # ``state`` is now optional (None when the middleware omitted it), so
    # coalesce before upper-casing rather than stringifying a None into "NONE".
    running = [r.get("service") for r in rows if (r.get("state") or "").upper() == "RUNNING"]
    return {"total": len(rows), "running": running}


def health_overview(conn: Any) -> dict:
    """[READ] One-shot health summary: pools (capacity/health), alerts, services."""
    return {
        "pools": _pool_health(conn),
        "alerts": _alert_health(conn),
        "services": _service_health(conn),
        "nearFullThresholdPercent": _NEAR_FULL_PERCENT,
    }
