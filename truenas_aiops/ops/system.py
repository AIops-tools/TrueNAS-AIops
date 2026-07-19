"""System information operations for TrueNAS SCALE (read-only).

Thin wrapper over ``GET /system/info``. Returns a high-signal summary, not the
full blob.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.governance import opt_str


def system_info(conn: Any) -> dict:
    """[READ] Return a high-signal TrueNAS system summary (version, uptime, model)."""
    info = conn.get("/system/info")
    if not isinstance(info, dict):
        return {}
    return {
        "version": opt_str(info.get("version"), 64),
        "hostname": opt_str(info.get("hostname"), 128),
        "systemProduct": opt_str(info.get("system_product"), 128),
        "physmem": info.get("physmem"),
        "cores": info.get("cores"),
        "uptime": opt_str(info.get("uptime"), 64),
        "loadavg": info.get("loadavg"),
    }
