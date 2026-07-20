"""Absent fields come back as null, not as an empty string.

An empty string reads as "this field exists and is empty"; a missing field is a
different fact. Collapsing the two hides information from any consumer, and a
smaller local model will confidently invent the difference. These tests pin the
contract end-to-end: helper, ops layer, and the CLI rendering that has to cope
with a null.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from truenas_aiops.cli import app
from truenas_aiops.governance import opt_str
from truenas_aiops.ops import disks as disk_ops
from truenas_aiops.ops import pools as pool_ops

runner = CliRunner()


@pytest.mark.unit
def test_opt_str_distinguishes_absent_from_empty():
    assert opt_str(None) is None, "absent must stay absent"
    assert opt_str("") == "", "a genuinely empty value is not the same as absent"
    assert opt_str("tank/data", 64) == "tank/data"


@pytest.mark.unit
def test_opt_str_still_sanitizes_and_truncates():
    assert opt_str("a\x00b") == "ab"  # control character stripped
    # A cut announces itself: the ellipsis is the only signal a reader gets
    # that what they are looking at is not the whole value.
    assert opt_str("abcdef", 3) == "ab\u2026"
    assert opt_str("abc", 3) == "abc"  # exactly at the cap is not truncated


@pytest.mark.unit
def test_opt_str_accepts_non_string_values():
    assert opt_str(42) == "42"


@pytest.mark.unit
def test_ops_report_absent_fields_as_none():
    """A pool row with no name/status reports null, not ''."""
    conn = MagicMock()
    conn.get.return_value = [{"id": "tank", "healthy": True}]  # name/status absent
    rows = pool_ops.list_pools(conn)
    assert rows[0]["id"] == "tank"
    assert rows[0]["name"] is None
    assert rows[0]["status"] is None


@pytest.mark.unit
def test_ops_keep_empty_string_when_source_is_empty():
    """An explicitly empty upstream value is preserved as '' — not turned into null."""
    conn = MagicMock()
    conn.get.return_value = [{"id": "tank", "name": "", "status": "HEALTHY"}]
    rows = pool_ops.list_pools(conn)
    assert rows[0]["name"] == ""
    assert rows[0]["status"] == "HEALTHY"


@pytest.mark.unit
def test_ops_never_drop_the_key_itself():
    """Keys are always present; only their value may be null.

    Omitting a key entirely is worse than a null — the consumer cannot tell the
    field was even considered.
    """
    conn = MagicMock()
    conn.get.return_value = [{}]
    row = pool_ops.list_pools(conn)[0]
    for key in ("id", "name", "status", "healthy", "size", "allocated", "free"):
        assert key in row, f"{key} must be present even when the source omitted it"


@pytest.mark.unit
def test_disk_serial_and_model_are_null_when_absent():
    """A disk the middleware reports without a serial/model must not read as ''.

    A blank serial is operationally meaningful ("this bay has an unlabelled
    disk"); an absent one only means the query did not return it.
    """
    conn = MagicMock()
    conn.get.return_value = [{"name": "sda", "size": 4000787030016}]
    row = disk_ops.list_disks(conn)[0]
    assert row["name"] == "sda"
    assert row["serial"] is None
    assert row["model"] is None
    assert row["pool"] is None


@pytest.mark.unit
def test_pool_status_string_is_passed_through_verbatim():
    """DEGRADED/HEALTHY must reach the caller unchanged — never normalised."""
    conn = MagicMock()
    conn.get.return_value = [{"id": "tank", "name": "tank", "status": "DEGRADED"}]
    assert pool_ops.list_pools(conn)[0]["status"] == "DEGRADED"


@pytest.mark.unit
def test_cli_renders_rows_with_null_fields(monkeypatch):
    """The table must survive a null field rather than crashing on render."""
    import truenas_aiops.cli.pool as pool_cli

    conn = MagicMock()
    # A pool with no name and no status — both become None at the ops layer.
    conn.get.return_value = [{"id": "tank", "healthy": True, "free": 100}]
    monkeypatch.setattr(pool_cli, "get_connection", lambda target=None: (conn, object()))

    result = runner.invoke(app, ["pool", "list"])
    assert result.exit_code == 0, result.output
    assert "tank" in result.output
