"""Smoke + ops tests for truenas-aiops.

Proves: every module imports, the CLI Typer app builds and --help works, the
MCP server exposes the expected tools, EVERY MCP tool carries the harness
marker ``_is_governed_tool``, read ops shape correctly against a mocked REST
client, and the write tools (undo capture, BEFORE-state, risk tiers) behave.
No real TrueNAS is needed — the connection is a MagicMock.
"""

import asyncio
import importlib
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

EXPECTED_TOOLS = {
    # system
    "system_info",
    # pools
    "pool_list", "pool_get", "pool_status", "scrub_status", "pool_capacity",
    "pool_scrub_start",
    # datasets
    "dataset_list", "dataset_get", "dataset_create",
    # snapshots
    "snapshot_list", "snapshot_create", "snapshot_delete",
    # disks
    "disk_list", "smart_test_results",
    # alerts
    "alert_list",
    # services
    "service_list", "service_restart",
    # replication
    "replication_list", "cloudsync_list",
    # overview
    "overview",
}

WRITE_TOOLS = {
    "pool_scrub_start", "dataset_create", "snapshot_create",
    "snapshot_delete", "service_restart",
}


@pytest.mark.unit
def test_all_modules_import():
    for name in (
        "truenas_aiops",
        "truenas_aiops.config",
        "truenas_aiops.connection",
        "truenas_aiops.doctor",
        "truenas_aiops.secretstore",
        "truenas_aiops.ops.system",
        "truenas_aiops.ops.pools",
        "truenas_aiops.ops.datasets",
        "truenas_aiops.ops.snapshots",
        "truenas_aiops.ops.disks",
        "truenas_aiops.ops.alerts",
        "truenas_aiops.ops.services",
        "truenas_aiops.ops.replication",
        "truenas_aiops.ops.overview",
        "truenas_aiops.cli",
        "truenas_aiops.cli._root",
        "truenas_aiops.cli._common",
        "truenas_aiops.cli.init",
        "truenas_aiops.cli.secret",
        "truenas_aiops.cli.pool",
        "truenas_aiops.cli.dataset",
        "truenas_aiops.cli.snapshot",
        "truenas_aiops.cli.disk",
        "truenas_aiops.cli.alert",
        "truenas_aiops.cli.service",
        "truenas_aiops.cli.replication",
        "truenas_aiops.cli.system",
        "truenas_aiops.cli.overview",
        "truenas_aiops.cli.doctor",
        "mcp_server.server",
        "mcp_server._shared",
        "mcp_server.tools.system",
        "mcp_server.tools.pools",
        "mcp_server.tools.datasets",
        "mcp_server.tools.snapshots",
        "mcp_server.tools.disks",
        "mcp_server.tools.alerts",
        "mcp_server.tools.services",
        "mcp_server.tools.replication",
        "mcp_server.tools.overview",
    ):
        importlib.import_module(name)


@pytest.mark.unit
def test_version():
    import truenas_aiops

    assert truenas_aiops.__version__ == "0.1.0"


@pytest.mark.unit
def test_cli_app_builds_and_help_works():
    from truenas_aiops.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for sub in (
        "pool", "dataset", "snapshot", "disk", "alert", "service",
        "replication", "secret", "init", "overview", "system", "doctor", "mcp",
    ):
        assert sub in result.output


@pytest.mark.unit
def test_cli_leaf_help_triggers_lazy_imports():
    """Recurse into leaf commands so any broken lazy import surfaces."""
    from truenas_aiops.cli import app

    runner = CliRunner()
    for cmd in (
        ["pool", "--help"], ["dataset", "--help"], ["snapshot", "--help"],
        ["disk", "--help"], ["alert", "--help"], ["service", "--help"],
        ["replication", "--help"], ["secret", "--help"], ["doctor", "--help"],
    ):
        result = runner.invoke(app, cmd)
        assert result.exit_code == 0, f"{cmd} failed: {result.output}"
    for cmd in (
        ["pool", "list", "--help"], ["pool", "get", "--help"],
        ["pool", "status", "--help"], ["pool", "scrub-status", "--help"],
        ["pool", "capacity", "--help"], ["pool", "scrub-start", "--help"],
        ["dataset", "list", "--help"], ["dataset", "get", "--help"],
        ["dataset", "create", "--help"],
        ["snapshot", "list", "--help"], ["snapshot", "create", "--help"],
        ["snapshot", "delete", "--help"],
        ["disk", "list", "--help"], ["disk", "smart", "--help"],
        ["alert", "list", "--help"],
        ["service", "list", "--help"], ["service", "restart", "--help"],
        ["replication", "list", "--help"], ["replication", "cloudsync", "--help"],
        ["secret", "list", "--help"], ["secret", "set", "--help"],
        ["init", "--help"], ["overview", "--help"], ["system", "--help"],
    ):
        result = runner.invoke(app, cmd)
        assert result.exit_code == 0, f"{cmd} failed: {result.output}"


@pytest.mark.unit
def test_mcp_list_tools_exposes_expected_tools():
    from mcp_server.server import mcp

    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert EXPECTED_TOOLS <= names, f"missing: {EXPECTED_TOOLS - names}"


@pytest.mark.unit
def test_every_mcp_tool_is_governed_by_harness():
    """Every registered tool callable must carry the @governed_tool marker."""
    from mcp_server import _shared

    tool_objs = _shared.mcp._tool_manager._tools
    assert EXPECTED_TOOLS <= set(tool_objs), "tool registry incomplete"
    for name, tool in tool_objs.items():
        fn = getattr(tool, "fn", None)
        assert fn is not None, f"{name} has no fn"
        assert getattr(fn, "_is_governed_tool", False), (
            f"{name} is not wrapped with @governed_tool (harness marker missing)"
        )


@pytest.mark.unit
def test_snapshot_delete_is_high_risk():
    """The data-destroying snapshot delete must be tagged high risk."""
    from mcp_server.tools import snapshots as snap_tools

    assert snap_tools.snapshot_delete._risk_level == "high"
    assert snap_tools.snapshot_create._risk_level == "medium"


@pytest.mark.unit
def test_write_tool_records_undo_token_via_harness(monkeypatch):
    """snapshot_create through the harness records an inverse snapshot_delete."""
    import truenas_aiops.governance.undo as undo_mod
    from mcp_server.tools import snapshots as snap_tools

    conn = MagicMock(name="conn")
    conn.post.return_value = {"id": "tank/data@snap1"}
    monkeypatch.setattr(snap_tools, "_get_connection", lambda target=None: conn)

    recorded = {}

    class _Store:
        def record(self, *, skill, tool, undo_descriptor, orig_params):
            recorded["descriptor"] = undo_descriptor
            recorded["tool"] = tool
            return "undo-123"

    monkeypatch.setattr(undo_mod, "get_undo_store", lambda: _Store())

    result = snap_tools.snapshot_create(dataset="tank/data", name="snap1")
    assert "error" not in result
    assert recorded["descriptor"]["tool"] == "snapshot_delete"  # inverse of create
    assert recorded["descriptor"]["params"]["snapshot_id"] == "tank/data@snap1"
    assert result.get("_undo_id") == "undo-123"


@pytest.mark.unit
def test_snapshot_delete_captures_before_state():
    """delete_snapshot records the snapshot's prior state for undo/audit."""
    from truenas_aiops.ops import snapshots as ops

    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"id": "tank/data@snap1", "name": "tank/data@snap1",
         "dataset": "tank/data", "snapshot_name": "snap1",
         "properties": {"used": {"value": "10M"}}},
    ]
    conn.delete.return_value = True
    result = ops.delete_snapshot(conn, "tank/data@snap1")
    assert result["action"] == "delete_snapshot"
    assert result["priorState"]["id"] == "tank/data@snap1"
    conn.delete.assert_called_once_with("/zfs/snapshot/id/tank/data@snap1")


@pytest.mark.unit
def test_dry_run_gates_destructive_cli(monkeypatch):
    """snapshot delete --dry-run must not call the connection."""
    from truenas_aiops.cli import app

    conn = MagicMock(name="conn")
    monkeypatch.setattr(
        "truenas_aiops.cli.snapshot.get_connection", lambda target: (conn, None)
    )
    runner = CliRunner()
    result = runner.invoke(app, ["snapshot", "delete", "tank/data@snap1", "--dry-run"])
    assert result.exit_code == 0
    assert "DRY-RUN" in result.output
    conn.delete.assert_not_called()


@pytest.mark.unit
def test_read_ops_shape_against_mock():
    """Read ops return high-signal shapes from a mocked REST client."""
    from truenas_aiops.ops import datasets as ds_ops
    from truenas_aiops.ops import pools as pool_ops

    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"id": "tank", "name": "tank", "status": "ONLINE", "healthy": True,
         "size": 1000, "allocated": 850, "free": 150},
    ]
    rows = pool_ops.pool_capacity(conn)
    assert rows[0]["name"] == "tank"
    assert rows[0]["usedPercent"] == 85.0

    pools = pool_ops.list_pools(conn)
    assert pools[0]["status"] == "ONLINE"

    conn.get.return_value = [
        {"id": "tank/data", "name": "tank/data", "type": "FILESYSTEM",
         "pool": "tank", "used": {"value": "100M"}, "available": {"value": "1G"},
         "mountpoint": "/mnt/tank/data"},
    ]
    datasets = ds_ops.list_datasets(conn)
    assert datasets[0]["id"] == "tank/data"
    assert datasets[0]["used"] == "100M"


@pytest.mark.unit
def test_overview_is_resilient_to_partial_failure():
    """One failing collection should not blank the whole overview."""
    from truenas_aiops.ops import overview as ov

    conn = MagicMock(name="conn")

    def _get(path, **kw):
        if path == "/pool":
            raise RuntimeError("pool query boom")
        return []

    conn.get.side_effect = _get
    conn.post.return_value = []
    data = ov.health_overview(conn)
    assert "error" in data["pools"]
    assert data["alerts"]["total"] == 0


@pytest.mark.unit
def test_connection_bearer_auth_and_error_translation(monkeypatch):
    """TrueNASConnection sends Bearer auth and translates non-2xx to TrueNASApiError."""
    from truenas_aiops.config import TargetConfig
    from truenas_aiops.connection import TrueNASApiError, TrueNASConnection

    monkeypatch.setenv("TRUENAS_NAS1_APIKEY", "secret-key")
    target = TargetConfig(name="nas1", host="nas.local", verify_ssl=False)

    class _Resp:
        def __init__(self, status, payload=None, content=b"{}"):
            self.status_code = status
            self._payload = payload or {}
            self.content = content
            self.text = "body"

        def json(self):
            return self._payload

    class _Client:
        def __init__(self):
            self.headers = {}

        def request(self, method, path, **k):
            if path == "/notfound":
                return _Resp(404, content=b"x")
            return _Resp(200, {"version": "TrueNAS-SCALE-24.04"}, content=b"{}")

        def close(self):
            pass

    conn = TrueNASConnection(target, client=_Client())
    assert conn.get("/system/info")["version"] == "TrueNAS-SCALE-24.04"
    with pytest.raises(TrueNASApiError) as ei:
        conn.get("/notfound")
    assert ei.value.status_code == 404
    assert "not found" in str(ei.value).lower()
