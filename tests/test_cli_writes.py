"""CLI confirmed-write path — past dry-run, through governance, onto disk.

The CLI write commands delegate real execution to the ``@governed_tool``
functions in ``mcp_server.tools``. These tests drive a write command PAST the
dry-run branch and the double-confirm prompts and assert the call really went
through the governed path (audit row on disk) — the regression test for the
"CLI writes were unaudited" line-wide fix.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

import truenas_aiops.governance.audit as audit_mod
import truenas_aiops.governance.policy as policy_mod
import truenas_aiops.governance.undo as undo_mod


@pytest.fixture
def gov_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUENAS_AIOPS_HOME", str(tmp_path))
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()
    yield tmp_path
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()


def _audit_tools(db_path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT tool FROM audit_log ORDER BY id")]
    finally:
        conn.close()


@pytest.fixture
def fake_conn(monkeypatch):
    """Route the governed snapshot tools to a mocked REST connection."""
    import mcp_server.tools.snapshots as gov_snapshots

    conn = MagicMock(name="conn")
    conn.get.return_value = []
    conn.delete.return_value = True
    monkeypatch.setattr(gov_snapshots, "_get_connection", lambda target=None: conn)
    return conn


@pytest.mark.unit
def test_cli_snapshot_delete_dry_run_makes_no_call_and_no_audit(gov_home, fake_conn):
    from truenas_aiops.cli import app

    result = CliRunner().invoke(app, ["snapshot", "delete", "tank/data@snap1", "--dry-run"])
    assert result.exit_code == 0
    assert "DRY-RUN" in result.output
    fake_conn.delete.assert_not_called()
    assert not (gov_home / "audit.db").exists()


@pytest.mark.unit
def test_cli_snapshot_delete_confirmed_goes_through_governance(gov_home, fake_conn):
    """Confirmed CLI write must execute via the governed twin: the API call runs
    AND an audit row lands in audit.db (this is what the reroute fix bought)."""
    from truenas_aiops.cli import app

    result = CliRunner().invoke(
        app, ["snapshot", "delete", "tank/data@snap1"], input="y\ny\n"
    )
    assert result.exit_code == 0, result.output
    fake_conn.delete.assert_called_once_with("/zfs/snapshot/id/tank%2Fdata%40snap1")
    assert _audit_tools(gov_home / "audit.db") == ["snapshot_delete"]


@pytest.mark.unit
def test_cli_snapshot_delete_aborts_without_double_confirm(gov_home, fake_conn):
    from truenas_aiops.cli import app

    result = CliRunner().invoke(app, ["snapshot", "delete", "tank/data@snap1"], input="y\nn\n")
    assert result.exit_code != 0
    fake_conn.delete.assert_not_called()
    assert not (gov_home / "audit.db").exists()
