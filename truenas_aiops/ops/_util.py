"""Shared helpers for TrueNAS ops modules.

TrueNAS SCALE REST v2.0 list endpoints return a bare JSON array; a few wrap
results in ``{"data": [...]}``. ``as_list`` normalises both. All API-returned
text reaches the caller only after ``sanitize()`` (prompt-injection defense).
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
