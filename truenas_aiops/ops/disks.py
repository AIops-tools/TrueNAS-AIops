"""Disk and S.M.A.R.T. operations for TrueNAS SCALE (read-only).

Read over ``/disk`` and S.M.A.R.T. test results over ``/smart/test/results``.

PREVIEW: mock-validated only — verify endpoint paths against a live system.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.ops._util import as_list, s


def _disk_summary(disk: dict) -> dict:
    """Reduce a disk record to a high-signal summary."""
    return {
        "name": s(disk.get("name"), 64),
        "serial": s(disk.get("serial"), 64),
        "model": s(disk.get("model"), 128),
        "size": disk.get("size"),
        "type": s(disk.get("type"), 16),
        "pool": s(disk.get("pool"), 128),
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
                "disk": s(r.get("disk"), 64),
                "latestStatus": s(latest.get("status"), 32),
                "description": s(latest.get("description"), 128),
                "remaining": latest.get("remaining"),
            }
        )
    return rows
