"""System information operations for TrueNAS SCALE (read-only).

Thin wrapper over ``GET /system/info``. Returns a high-signal summary, not the
full blob.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.ops._util import s


def system_info(conn: Any) -> dict:
    """[READ] Return a high-signal TrueNAS system summary (version, uptime, model)."""
    info = conn.get("/system/info")
    if not isinstance(info, dict):
        return {}
    return {
        "version": s(info.get("version"), 64),
        "hostname": s(info.get("hostname"), 128),
        "systemProduct": s(info.get("system_product"), 128),
        "physmem": info.get("physmem"),
        "cores": info.get("cores"),
        "uptime": s(info.get("uptime"), 64),
        "loadavg": info.get("loadavg"),
    }
