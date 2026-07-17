"""MCP governed-twin coverage for the read/write tool bodies.

Each tool is called directly (it is the fully-decorated governed callable) with
``_get_connection`` monkeypatched to a MagicMock REST client. Reads assert the
normalized shape flows through the harness; writes assert the API call fires and
an audit row lands on an isolated audit.db.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

import truenas_aiops.governance.audit as audit_mod
import truenas_aiops.governance.policy as policy_mod
import truenas_aiops.governance.undo as undo_mod
from mcp_server.tools import alerts as alert_tools
from mcp_server.tools import datasets as ds_tools
from mcp_server.tools import disks as disk_tools
from mcp_server.tools import overview as ov_tools
from mcp_server.tools import pools as pool_tools
from mcp_server.tools import replication as repl_tools
from mcp_server.tools import services as svc_tools
from mcp_server.tools import system as sys_tools


@pytest.fixture
def gov_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUENAS_AIOPS_HOME", str(tmp_path))
    monkeypatch.setenv("TRUENAS_AUDIT_APPROVED_BY", "pytest")
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()
    yield tmp_path
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()


def _patch_conn(monkeypatch, module, conn):
    monkeypatch.setattr(module, "_get_connection", lambda target=None: conn)


def _audit_tools(db_path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT tool FROM audit_log ORDER BY id")]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# read tools — body flows conn -> ops -> normalized shape
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_pool_read_tools_shape(gov_home, monkeypatch):
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"id": "tank", "name": "tank", "status": "ONLINE", "healthy": True,
         "size": 100, "allocated": 40, "free": 60},
    ]
    _patch_conn(monkeypatch, pool_tools, conn)

    assert pool_tools.pool_list()[0]["name"] == "tank"
    assert pool_tools.pool_capacity()[0]["usedPercent"] == 40.0

    conn.get.return_value = {"id": "tank", "name": "tank", "status": "ONLINE",
                             "healthy": True, "path": "/mnt/tank", "encrypt": 0,
                             "scan": {"function": "SCRUB", "state": "FINISHED"},
                             "topology": {"data": [{}]}}
    assert pool_tools.pool_get(pool_id="tank")["path"] == "/mnt/tank"
    assert pool_tools.pool_status(pool_id="tank")["dataVdevs"] == 1
    assert pool_tools.scrub_status(pool_id="tank")["state"] == "FINISHED"


@pytest.mark.unit
def test_dataset_read_tools_shape(gov_home, monkeypatch):
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"id": "tank/data", "name": "tank/data", "type": "FILESYSTEM", "pool": "tank",
         "used": {"value": "1G"}, "available": {"value": "9G"}, "mountpoint": "/mnt/tank/data"},
    ]
    _patch_conn(monkeypatch, ds_tools, conn)
    assert ds_tools.dataset_list()[0]["used"] == "1G"

    conn.get.return_value = {"id": "tank/data", "name": "tank/data", "type": "FILESYSTEM"}
    assert ds_tools.dataset_get(dataset_id="tank/data")["id"] == "tank/data"


@pytest.mark.unit
def test_disk_read_tools_shape(gov_home, monkeypatch):
    conn = MagicMock(name="conn")
    conn.get.return_value = [{"name": "sda", "serial": "S1", "model": "M", "size": 1,
                              "type": "HDD", "pool": "tank"}]
    _patch_conn(monkeypatch, disk_tools, conn)
    assert disk_tools.disk_list()[0]["name"] == "sda"

    conn.get.return_value = [{"disk": "sda", "tests": [{"status": "SUCCESS"}]}]
    assert disk_tools.smart_test_results()[0]["latestStatus"] == "SUCCESS"


@pytest.mark.unit
def test_replication_and_service_and_system_read(gov_home, monkeypatch):
    conn = MagicMock(name="conn")
    conn.get.return_value = [{"id": 1, "name": "r", "job": {"state": "FINISHED"}}]
    _patch_conn(monkeypatch, repl_tools, conn)
    assert repl_tools.replication_list()[0]["state"] == "FINISHED"
    conn.get.return_value = [{"id": 2, "description": "cs", "job": {"state": "RUNNING"}}]
    assert repl_tools.cloudsync_list()[0]["state"] == "RUNNING"

    conn2 = MagicMock(name="conn2")
    conn2.get.return_value = [{"id": 1, "service": "smb", "state": "RUNNING", "enable": True}]
    _patch_conn(monkeypatch, svc_tools, conn2)
    assert svc_tools.service_list()[0]["service"] == "smb"

    conn3 = MagicMock(name="conn3")
    conn3.get.return_value = {"version": "TrueNAS-SCALE-24.04", "hostname": "n"}
    _patch_conn(monkeypatch, sys_tools, conn3)
    assert sys_tools.system_info()["version"] == "TrueNAS-SCALE-24.04"


@pytest.mark.unit
def test_alert_and_overview_read(gov_home, monkeypatch):
    conn = MagicMock(name="conn")
    conn.post.return_value = [{"id": "a1", "level": "CRITICAL", "formatted": "disk bad"}]
    _patch_conn(monkeypatch, alert_tools, conn)
    assert alert_tools.alert_list()[0]["level"] == "CRITICAL"

    conn2 = MagicMock(name="conn2")
    conn2.get.return_value = []
    conn2.post.return_value = []
    _patch_conn(monkeypatch, ov_tools, conn2)
    data = ov_tools.overview()
    assert data["nearFullThresholdPercent"] == 80.0


# --------------------------------------------------------------------------- #
# write tools — API call fires AND an audit row is written on the governed path
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_pool_scrub_start_audited(gov_home, monkeypatch):
    conn = MagicMock(name="conn")
    conn.get.return_value = [{"name": "tank", "scan": {"state": "FINISHED"}}]
    _patch_conn(monkeypatch, pool_tools, conn)
    result = pool_tools.pool_scrub_start(pool_name="tank")
    assert result["action"] == "scrub_start"
    conn.post.assert_called_once_with("/pool/scrub/run", json={"name": "tank"})
    assert "pool_scrub_start" in _audit_tools(gov_home / "audit.db")


@pytest.mark.unit
def test_dataset_create_audited(gov_home, monkeypatch):
    conn = MagicMock(name="conn")
    conn.post.return_value = {"id": "tank/new"}
    _patch_conn(monkeypatch, ds_tools, conn)
    result = ds_tools.dataset_create(name="tank/new")
    assert result["action"] == "create_dataset"
    conn.post.assert_called_once_with(
        "/pool/dataset", json={"name": "tank/new", "type": "FILESYSTEM"}
    )
    assert "dataset_create" in _audit_tools(gov_home / "audit.db")


@pytest.mark.unit
def test_service_restart_audited_and_captures_prior(gov_home, monkeypatch):
    conn = MagicMock(name="conn")
    conn.get.return_value = [{"id": 1, "service": "smb", "state": "RUNNING", "enable": True}]
    _patch_conn(monkeypatch, svc_tools, conn)
    result = svc_tools.service_restart(service="smb")
    assert result["priorState"]["state"] == "RUNNING"
    conn.post.assert_called_once_with("/service/restart", json={"service": "smb"})
    assert "service_restart" in _audit_tools(gov_home / "audit.db")


@pytest.mark.unit
def test_read_tool_error_is_sanitized_into_list_shape(gov_home, monkeypatch):
    """A raising ops call is caught by @tool_errors and returned, not propagated."""
    conn = MagicMock(name="conn")
    conn.get.side_effect = ValueError("boom detail")
    _patch_conn(monkeypatch, pool_tools, conn)
    out = pool_tools.pool_list()
    assert isinstance(out, list)
    assert "error" in out[0]
    assert "hint" in out[0]
