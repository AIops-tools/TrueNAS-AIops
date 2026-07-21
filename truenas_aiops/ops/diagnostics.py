"""Flagship signature analyses over TrueNAS SCALE telemetry (pure analysis).

TrueNAS-AIops was born read-heavy (inventory + a few guarded writes); these two
analyses give it a *transparent* RCA in the style of the rest of the line: every
finding is reported with the measured number that tripped it, so an operator
sees **why** something was flagged — never a black-box verdict.

  1. ``pool_health_findings`` — flag ZFS pools that are DEGRADED/FAULTED/OFFLINE,
     pools with non-zero read/write/checksum/scan error counters, and pools whose
     capacity is over threshold (ZFS slows sharply as it fills), each citing the
     status string / error counts / used-percent and a concrete action.
  2. ``alert_capacity_findings`` — surface active (non-dismissed) TrueNAS alerts
     by level and datasets whose usage is near their quota/available ceiling,
     each citing the measured level/percent.

Both are pure functions (no I/O): pass them the already-fetched records (raw
``/pool`` / ``/pool/dataset`` dicts and the normalized alert summaries) and they
return the analysis. The MCP / CLI layers do the collection; keeping the
heuristics pure makes them trivially unit-testable without a live NAS.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from truenas_aiops.ops._util import s

# Thresholds that flip a signal on. Each is surfaced in the finding text next to
# the measured value so the ranking is auditable, not opaque.
CAP_WARN_PCT = 80.0  # ZFS write performance degrades as a pool/dataset fills
CAP_CRIT_PCT = 90.0  # above ~90% ZFS fragments and slows sharply

# ZFS pool states that mean lost redundancy or an unavailable pool.
BAD_POOL_STATES = {"DEGRADED", "FAULTED", "OFFLINE", "UNAVAIL", "REMOVED"}

# TrueNAS alert levels mapped to finding severities.
_CRIT_LEVELS = {"CRITICAL", "ERROR", "ALERT", "EMERGENCY"}
_WARN_LEVELS = {"WARNING"}

# Severity ordering used to rank findings most-urgent first.
_SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


# The three coercers below return None / 0 on unparseable input, and that is
# deliberate — they are *parsers*, not probes. Their input is a value already
# fetched by a caller that raises on a failed fetch, so "not a number" here means
# the middleware really did send something non-numeric (or omitted the field),
# never that a request failed. None therefore reads correctly as "not
# computable", matching opt_str's missing-is-null rule. Do not convert these to
# error envelopes: an envelope per scalar would say nothing a null does not, and
# the failure they would supposedly report cannot reach them.


def _pct(used: Any, total: Any) -> float | None:
    """Percentage used, or None when the total is missing / zero."""
    try:
        u = float(used)
        t = float(total)
    except (TypeError, ValueError):
        return None
    if t <= 0:
        return None
    return round(u / t * 100.0, 1)


def _int(value: Any) -> int:
    """Coerce to int, treating missing / non-numeric as 0.

    Unlike its two neighbours this collapses "absent" into a real value, which
    is safe *only* because its callers sum ZFS error counters: a vdev that
    reports no ``read_errors`` key has recorded no read errors, so 0 is the
    true count rather than a stand-in for unknown. Do not reuse it for a metric
    where a missing field could mean "not measured" — there, 0 would read as a
    clean result and hide the gap.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _num(value: Any) -> float | None:
    """Coerce to float, or None when missing / non-numeric."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parsed(record: dict, key: str) -> Any:
    """TrueNAS nests size properties as ``{parsed, rawvalue, value}``; return the
    numeric ``parsed`` byte count (or the bare value when not nested)."""
    v = record.get(key)
    return v.get("parsed") if isinstance(v, dict) else v


def _finding(
    severity: str, resource: str, signal: str, detail: str, cause: str, action: str
) -> dict:
    """Build one cited finding (immutable dict — callers never mutate it)."""
    return {
        "severity": severity,
        "resource": resource,
        "signal": signal,
        "detail": detail,
        "cause": cause,
        "action": action,
    }


def _rank(findings: list[dict]) -> list[dict]:
    """Return findings most-urgent first, each carrying its explicit 1-based rank.

    The priority is stated in the payload rather than left implicit in list
    order: a consumer — notably a smaller local model summarising the result —
    should never have to infer urgency from position. Returns new dicts; the
    inputs are not mutated.
    """
    ordered = sorted(findings, key=lambda f: _SEVERITY_RANK.get(f["severity"], 9))
    return [{**finding, "rank": i} for i, finding in enumerate(ordered, 1)]


def _walk_vdevs(group: Any) -> Iterator[dict]:
    """Yield every vdev in a topology group, recursing into raidz/mirror children."""
    if not isinstance(group, list):
        return
    for vdev in group:
        if isinstance(vdev, dict):
            yield vdev
            yield from _walk_vdevs(vdev.get("children"))


def _pool_error_totals(pool: dict) -> dict:
    """Sum read/write/checksum errors across every vdev, plus scan errors."""
    totals = {"read": 0, "write": 0, "checksum": 0, "scan": 0}
    topology = pool.get("topology")
    if isinstance(topology, dict):
        for group in topology.values():
            for vdev in _walk_vdevs(group):
                stats = vdev.get("stats")
                if isinstance(stats, dict):
                    totals["read"] += _int(stats.get("read_errors"))
                    totals["write"] += _int(stats.get("write_errors"))
                    totals["checksum"] += _int(stats.get("checksum_errors"))
    scan = pool.get("scan")
    if isinstance(scan, dict):
        totals["scan"] = _int(scan.get("errors"))
    return totals


def _pool_status_finding(name: str, status: str, healthy: Any) -> dict | None:
    """Flag a pool that is in a bad ZFS state, or flagged unhealthy while online."""
    if status in BAD_POOL_STATES:
        return _finding(
            "critical", name, "pool not healthy", f"pool status is {status}",
            "A vdev is faulted/offline; redundancy is lost or the pool is unavailable.",
            f"Inspect 'pool status {name}'; replace/reattach the failed disk, then scrub.",
        )
    if healthy is False:
        return _finding(
            "warning", name, "pool flagged unhealthy",
            f"status {status or 'ONLINE'} but healthy=false",
            "ZFS reports a condition (recent errors or an incomplete resilver).",
            f"Review 'pool status {name}' and clear the condition after investigating.",
        )
    return None


def _pool_error_finding(name: str, status: str, errors: dict) -> dict | None:
    """Flag a pool with any non-zero ZFS error counter."""
    total = errors["read"] + errors["write"] + errors["checksum"] + errors["scan"]
    if total <= 0:
        return None
    return _finding(
        "critical" if status in BAD_POOL_STATES else "warning", name, "pool I/O errors",
        f"read={errors['read']} write={errors['write']} "
        f"checksum={errors['checksum']} scan={errors['scan']}",
        "Non-zero ZFS error counters indicate a failing disk, cable, or bit rot.",
        f"Run a scrub ('pool scrub-start {name}'); replace the disk if counts grow.",
    )


def _pool_capacity_finding(name: str, used_pct: float | None) -> dict | None:
    """Flag a pool whose used-percent is over the warning/critical threshold."""
    if used_pct is None:
        return None
    if used_pct >= CAP_CRIT_PCT:
        return _finding(
            "critical", name, "pool almost full", f"used {used_pct}% >= {CAP_CRIT_PCT}%",
            "ZFS is copy-on-write; above ~90% full it fragments and slows sharply.",
            "Free space, expand the pool, or prune old snapshots/datasets.",
        )
    if used_pct >= CAP_WARN_PCT:
        return _finding(
            "warning", name, "pool capacity high", f"used {used_pct}% >= {CAP_WARN_PCT}%",
            "ZFS write performance degrades as a pool approaches full.",
            "Plan capacity: prune snapshots or add vdevs before it reaches 90%.",
        )
    return None


def pool_health_findings(pools: list[dict]) -> dict:
    """[ANALYSIS] Flag pools by ZFS state, error counters, and capacity.

    Args:
        pools: raw ``/pool`` records, each with ``name``, ``status``, ``healthy``,
            ``size``/``allocated``, ``scan.errors``, and a ``topology`` whose vdev
            ``stats`` carry read/write/checksum error counts.

    Returns a dict with the worst-first ``findings`` list and a per-pool
    ``summary`` of the measured status / used-percent / error totals.
    """
    findings: list[dict] = []
    summary: list[dict] = []
    for p in pools:
        name = s(p.get("name") or p.get("id") or "?", 128)
        status = str(p.get("status") or "").upper()
        used_pct = _pct(p.get("allocated"), p.get("size"))
        errors = _pool_error_totals(p)
        summary.append({"pool": name, "status": status, "usedPercent": used_pct,
                        "errors": errors})
        for f in (
            _pool_status_finding(name, status, p.get("healthy")),
            _pool_error_finding(name, status, errors),
            _pool_capacity_finding(name, used_pct),
        ):
            if f is not None:
                findings.append(f)
    return {"findings": _rank(findings), "summary": summary,
            "poolsAnalyzed": len(pools)}


def _alert_findings(alerts: list[dict]) -> tuple[list[dict], dict]:
    """One finding per active (non-dismissed) alert at WARNING+; count by level."""
    findings: list[dict] = []
    counts: dict[str, int] = {}
    for a in alerts:
        if a.get("dismissed"):
            continue
        level = str(a.get("level") or "").upper()
        counts[level] = counts.get(level, 0) + 1
        msg = s(a.get("formatted") or a.get("klass") or "alert", 256)
        if level in _CRIT_LEVELS:
            findings.append(_finding(
                "critical", "alerts", f"{level} alert", f"[{level}] {msg}",
                "TrueNAS raised a high-severity alert needing operator attention.",
                "Resolve the underlying condition; dismiss the alert once cleared.",
            ))
        elif level in _WARN_LEVELS:
            findings.append(_finding(
                "warning", "alerts", "WARNING alert", f"[WARNING] {msg}",
                "TrueNAS raised a warning-level alert.",
                "Investigate before it escalates; dismiss the alert once cleared.",
            ))
    return findings, counts


def _dataset_pct(ds: dict) -> float | None:
    """Used-percent against quota (if set) else against used+available headroom."""
    used = _num(_parsed(ds, "used"))
    quota = _num(_parsed(ds, "quota"))
    avail = _num(_parsed(ds, "available"))
    if quota and quota > 0:
        return _pct(used, quota)
    if used is not None and avail is not None and (used + avail) > 0:
        return round(used / (used + avail) * 100.0, 1)
    return None


def _dataset_findings(datasets: list[dict]) -> list[dict]:
    """Flag datasets whose usage is near their quota/available ceiling."""
    findings: list[dict] = []
    for ds in datasets:
        name = s(ds.get("name") or ds.get("id") or "?", 256)
        pct = _dataset_pct(ds)
        if pct is None:
            continue
        if pct >= CAP_CRIT_PCT:
            findings.append(_finding(
                "critical", name, "dataset almost full",
                f"{name} used {pct}% of its quota/available",
                "Writes into a full dataset fail; quota exhaustion blocks apps/shares.",
                f"Raise the quota, free space, or prune snapshots on {name}.",
            ))
        elif pct >= CAP_WARN_PCT:
            findings.append(_finding(
                "warning", name, "dataset capacity high",
                f"{name} used {pct}% of its quota/available",
                "A dataset approaching its ceiling risks imminent write failures.",
                f"Plan capacity for {name}: raise the quota or free space.",
            ))
    return findings


def alert_capacity_findings(alerts: list[dict], datasets: list[dict]) -> dict:
    """[ANALYSIS] Surface active alerts by level and datasets near full.

    Args:
        alerts: normalized alert summaries (``level``, ``formatted``, ``klass``,
            ``dismissed``) from ``ops.alerts.list_alerts``.
        datasets: raw ``/pool/dataset`` records, each with nested ``used`` /
            ``available`` / ``quota`` (``{parsed: <bytes>}``).

    Returns a dict with the worst-first ``findings`` list, an ``alertLevels``
    count map, and the analyzed counts.
    """
    alert_findings, level_counts = _alert_findings(alerts)
    ds_findings = _dataset_findings(datasets)
    return {
        "findings": _rank(alert_findings + ds_findings),
        "alertLevels": level_counts,
        "alertsAnalyzed": len(alerts),
        "datasetsAnalyzed": len(datasets),
    }
