"""Disk and S.M.A.R.T. operations for TrueNAS SCALE (read-only).

Read over ``/disk`` and S.M.A.R.T. test results over ``/smart/test/results``.

PREVIEW: mock-validated only — verify endpoint paths against a live system.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.governance import opt_str
from truenas_aiops.ops._util import as_list


def _disk_summary(disk: dict) -> dict:
    """Reduce a disk record to a high-signal summary."""
    return {
        "name": opt_str(disk.get("name"), 64),
        "serial": opt_str(disk.get("serial"), 64),
        "model": opt_str(disk.get("model"), 128),
        "size": disk.get("size"),
        "type": opt_str(disk.get("type"), 16),
        "pool": opt_str(disk.get("pool"), 128),
    }


def list_disks(conn: Any) -> list[dict]:
    """[READ] List physical disks with name, serial, model, size, pool."""
    return [_disk_summary(d) for d in as_list(conn.get("/disk"))]


def smart_test_results(conn: Any) -> list[dict]:
    """[READ] Return recent S.M.A.R.T. self-test results per disk."""
    rows = []
    for r in as_list(conn.get("/smart/test/results")):
        tests = r.get("tests") or []
        latest = tests[0] if isinstance(tests, list) and tests else {}
        if not isinstance(latest, dict):
            latest = {}
        rows.append(
            {
                "disk": opt_str(r.get("disk"), 64),
                "latestStatus": opt_str(latest.get("status"), 32),
                "description": opt_str(latest.get("description"), 128),
                "remaining": latest.get("remaining"),
            }
        )
    return rows
