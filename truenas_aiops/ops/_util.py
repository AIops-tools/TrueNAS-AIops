"""Shared helpers for TrueNAS ops modules.

TrueNAS SCALE REST v2.0 list endpoints return a bare JSON array; a few wrap
results in ``{"data": [...]}``. ``as_list`` normalises both. All API-returned
text reaches the caller only after ``sanitize()`` (output hygiene).
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.governance import sanitize


def as_list(data: Any) -> list[dict]:
    """Normalise a list endpoint's payload to a list of dicts."""
    if isinstance(data, dict):
        items = data.get("data", [])
    else:
        items = data
    return [i for i in (items or []) if isinstance(i, dict)]


def s(value: Any, limit: int = 128) -> str:
    """Sanitize an arbitrary value to a bounded, injection-safe string."""
    return sanitize(str(value if value is not None else ""), limit)


# ─── best-effort BEFORE-state probes ───────────────────────────────────────
#
# A write op that captures "what did this look like before?" has THREE possible
# outcomes, and they must stay distinguishable in the payload:
#
#   found   — the probe ran and the subject was there
#   absent  — the probe ran and the subject genuinely was not there
#   failed  — the probe could not run, so we know nothing either way
#
# Collapsing the last two into a bare ``{}`` is the bug class that hid MinIO's
# ``drive_status`` defect for that tool's entire life: a scrape that failed
# looked exactly like a server with nothing to report, so "healthy" and "broken"
# rendered identically. ``found`` is ``None`` — not ``False`` — on failure,
# because unknown is not the same claim as absent (see ``opt_str``: missing is
# null, only genuinely-empty is empty).


def probe_found(state: dict) -> dict:
    """The probe ran and the subject was there; ``state`` is its summary."""
    return {"found": True, "state": state, "error": None}


def probe_absent() -> dict:
    """The probe ran cleanly and the subject was genuinely not present."""
    return {"found": False, "state": None, "error": None}


def probe_failed(exc: Any) -> dict:
    """The probe itself failed. ``found`` is null: this is UNKNOWN, not absent."""
    return {"found": None, "state": None, "error": s(exc, 200)}
