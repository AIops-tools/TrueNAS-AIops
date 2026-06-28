"""Alert operations for TrueNAS SCALE (read-only).

Read over ``POST /alert/list`` (TrueNAS exposes the alert list as a POST query
with no body in v2.0). Returns a high-signal summary per active alert.

PREVIEW: mock-validated only — verify endpoint paths against a live system.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.ops._util import as_list, s


def _alert_summary(alert: dict) -> dict:
    """Reduce an alert record to a high-signal summary."""
    return {
        "id": s(alert.get("id"), 128),
        "level": s(alert.get("level"), 32),
        "formatted": s(alert.get("formatted"), 256),
        "klass": s(alert.get("klass"), 64),
        "dismissed": alert.get("dismissed"),
        "datetime": s((alert.get("datetime") or {}).get("$date")
                      if isinstance(alert.get("datetime"), dict) else alert.get("datetime"), 64),
    }


def list_alerts(conn: Any) -> list[dict]:
    """[READ] List active TrueNAS alerts with level, message, class, dismissed."""
    return [_alert_summary(a) for a in as_list(conn.post("/alert/list"))]
