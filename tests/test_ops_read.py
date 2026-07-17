"""Ops-layer coverage for the worst-covered read/write modules.

Every ops function takes a REST ``conn`` (a MagicMock here). These tests assert
the three things that matter at this layer: the endpoint path + params sent to
the connection, the normalization of canned TrueNAS payloads, and the
prior-state capture on the write ops. No real TrueNAS, no governance harness.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from truenas_aiops.ops import disks as disk_ops
from truenas_aiops.ops import overview as ov_ops
from truenas_aiops.ops import pools as pool_ops
from truenas_aiops.ops import replication as repl_ops
from truenas_aiops.ops import services as svc_ops
from truenas_aiops.ops import snapshots as snap_ops
from truenas_aiops.ops import system as sys_ops


# --------------------------------------------------------------------------- #
# replication.py
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_list_replication_endpoint_and_state_extraction():
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {
            "id": 3,
            "name": "nightly-repl",
            "direction": "PUSH",
            "transport": "SSH",
            "enabled": True,
            "job": {"state": "FINISHED", "progress": {"percent": 100}},
        }
    ]
    rows = repl_ops.list_replication(conn)
    conn.get.assert_called_once_with("/replication")
    assert rows == [
        {
            "id": 3,
            "name": "nightly-repl",
            "direction": "PUSH",
            "transport": "SSH",
            "enabled": True,
            "state": "FINISHED",
        }
    ]


@pytest.mark.unit
def test_list_replication_handles_missing_and_nondict_job():
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"id": 1, "name": "no-job"},  # no embedded job at all
        {"id": 2, "name": "bad-job", "job": "not-a-dict"},  # job wrong type
    ]
    rows = repl_ops.list_replication(conn)
    assert rows[0]["state"] == ""  # missing job -> empty state
    assert rows[1]["state"] == ""  # non-dict job -> _job_state returns {}


@pytest.mark.unit
def test_list_cloudsync_endpoint_and_fields():
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {
            "id": 7,
            "description": "backup to s3",
            "direction": "PUSH",
            "path": "/mnt/tank/data",
            "enabled": False,
            "job": {"state": "RUNNING"},
        }
    ]
    rows = repl_ops.list_cloudsync(conn)
    conn.get.assert_called_once_with("/cloudsync")
    assert rows[0]["description"] == "backup to s3"
    assert rows[0]["path"] == "/mnt/tank/data"
    assert rows[0]["enabled"] is False
    assert rows[0]["state"] == "RUNNING"


@pytest.mark.unit
def test_replication_normalizes_data_wrapped_payload():
    """TrueNAS may wrap list endpoints in {"data": [...]}; as_list unwraps it."""
    conn = MagicMock(name="conn")
    conn.get.return_value = {"data": [{"id": 1, "name": "wrapped"}]}
    rows = repl_ops.list_replication(conn)
    assert len(rows) == 1
    assert rows[0]["name"] == "wrapped"


# --------------------------------------------------------------------------- #
# disks.py
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_list_disks_endpoint_and_summary():
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {
            "name": "sda",
            "serial": "ABC123",
            "model": "WD-RED-4TB",
            "size": 4000787030016,
            "type": "HDD",
            "pool": "tank",
            "extra": "dropped",
        }
    ]
    rows = disk_ops.list_disks(conn)
    conn.get.assert_called_once_with("/disk")
    assert rows[0] == {
        "name": "sda",
        "serial": "ABC123",
        "model": "WD-RED-4TB",
        "size": 4000787030016,
        "type": "HDD",
        "pool": "tank",
    }
    assert "extra" not in rows[0]


@pytest.mark.unit
def test_smart_test_results_takes_latest_test():
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {
            "disk": "sda",
            "tests": [
                {"status": "SUCCESS", "description": "Short offline", "remaining": 0.0},
                {"status": "SUCCESS", "description": "older", "remaining": 0.0},
            ],
        }
    ]
    rows = disk_ops.smart_test_results(conn)
    conn.get.assert_called_once_with("/smart/test/results")
    assert rows[0]["disk"] == "sda"
    assert rows[0]["latestStatus"] == "SUCCESS"
    assert rows[0]["description"] == "Short offline"
    assert rows[0]["remaining"] == 0.0


@pytest.mark.unit
def test_smart_test_results_handles_empty_and_nonlist_tests():
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"disk": "sdb", "tests": []},  # no tests recorded
        {"disk": "sdc", "tests": "corrupt"},  # tests not a list
        {"disk": "sdd", "tests": ["not-a-dict"]},  # first entry not a dict
    ]
    rows = disk_ops.smart_test_results(conn)
    assert rows[0]["latestStatus"] == ""
    assert rows[1]["latestStatus"] == ""
    assert rows[2]["latestStatus"] == ""
    assert [r["disk"] for r in rows] == ["sdb", "sdc", "sdd"]


# --------------------------------------------------------------------------- #
# services.py
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_list_services_endpoint_and_summary():
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"id": 1, "service": "smb", "state": "RUNNING", "enable": True, "pids": [1, 2]},
    ]
    rows = svc_ops.list_services(conn)
    conn.get.assert_called_once_with("/service")
    assert rows[0] == {"id": 1, "service": "smb", "state": "RUNNING", "enable": True}


@pytest.mark.unit
def test_restart_service_posts_and_captures_prior_state():
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"id": 1, "service": "nfs", "state": "STOPPED", "enable": False},
        {"id": 2, "service": "smb", "state": "RUNNING", "enable": True},
    ]
    result = svc_ops.restart_service(conn, "nfs")
    conn.post.assert_called_once_with("/service/restart", json={"service": "nfs"})
    assert result["service"] == "nfs"
    assert result["action"] == "restart"
    assert result["priorState"]["state"] == "STOPPED"
    assert result["priorState"]["service"] == "nfs"


@pytest.mark.unit
def test_restart_service_prior_state_empty_when_not_found():
    conn = MagicMock(name="conn")
    conn.get.return_value = [{"id": 2, "service": "smb", "state": "RUNNING"}]
    result = svc_ops.restart_service(conn, "ssh")
    assert result["priorState"] == {}
    conn.post.assert_called_once_with("/service/restart", json={"service": "ssh"})


@pytest.mark.unit
def test_restart_service_swallows_lookup_error_but_still_restarts():
    """A failed prior-state lookup must not block the restart (advisory only)."""
    conn = MagicMock(name="conn")
    conn.get.side_effect = RuntimeError("service list boom")
    result = svc_ops.restart_service(conn, "smb")
    assert result["priorState"] == {}
    conn.post.assert_called_once_with("/service/restart", json={"service": "smb"})


# --------------------------------------------------------------------------- #
# system.py
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_system_info_endpoint_and_fields():
    conn = MagicMock(name="conn")
    conn.get.return_value = {
        "version": "TrueNAS-SCALE-24.04.0",
        "hostname": "nas1",
        "system_product": "PowerEdge",
        "physmem": 34359738368,
        "cores": 8,
        "uptime": "3 days",
        "loadavg": [0.1, 0.2, 0.3],
        "extra_secret": "dropped",
    }
    info = sys_ops.system_info(conn)
    conn.get.assert_called_once_with("/system/info")
    assert info["version"] == "TrueNAS-SCALE-24.04.0"
    assert info["systemProduct"] == "PowerEdge"
    assert info["cores"] == 8
    assert info["loadavg"] == [0.1, 0.2, 0.3]
    assert "extra_secret" not in info


@pytest.mark.unit
def test_system_info_returns_empty_on_nondict():
    conn = MagicMock(name="conn")
    conn.get.return_value = ["unexpected", "list"]
    assert sys_ops.system_info(conn) == {}


# --------------------------------------------------------------------------- #
# pools.py — the read details + scrub write
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_get_pool_encodes_id_and_adds_detail_fields():
    conn = MagicMock(name="conn")
    conn.get.return_value = {
        "id": "tank",
        "name": "tank",
        "status": "ONLINE",
        "healthy": True,
        "size": 1000,
        "allocated": 400,
        "free": 600,
        "path": "/mnt/tank",
        "encrypt": 0,
    }
    result = pool_ops.get_pool(conn, "tank")
    conn.get.assert_called_once_with("/pool/id/tank")
    assert result["path"] == "/mnt/tank"
    assert result["encrypt"] == 0
    assert result["status"] == "ONLINE"


@pytest.mark.unit
def test_get_pool_nondict_yields_empty_summary_without_detail():
    conn = MagicMock(name="conn")
    conn.get.return_value = None
    result = pool_ops.get_pool(conn, "tank")
    # summary of {} -> path/encrypt not added
    assert "path" not in result
    assert result["name"] == ""


@pytest.mark.unit
def test_pool_status_scan_and_vdev_count():
    conn = MagicMock(name="conn")
    conn.get.return_value = {
        "id": "tank",
        "name": "tank",
        "status": "ONLINE",
        "healthy": True,
        "scan": {"function": "SCRUB", "state": "FINISHED", "percentage": 100},
        "topology": {"data": [{"type": "RAIDZ2"}, {"type": "RAIDZ2"}]},
    }
    result = pool_ops.pool_status(conn, "tank")
    conn.get.assert_called_once_with("/pool/id/tank")
    assert result["scan"]["function"] == "SCRUB"
    assert result["scan"]["state"] == "FINISHED"
    assert result["scan"]["percentage"] == 100
    assert result["dataVdevs"] == 2


@pytest.mark.unit
def test_pool_status_nondict_returns_empty():
    conn = MagicMock(name="conn")
    conn.get.return_value = "boom"
    assert pool_ops.pool_status(conn, "tank") == {}


@pytest.mark.unit
def test_pool_status_tolerates_nondict_scan_and_topology():
    conn = MagicMock(name="conn")
    conn.get.return_value = {"id": "tank", "name": "tank", "scan": "x", "topology": "y"}
    result = pool_ops.pool_status(conn, "tank")
    assert result["scan"] == {"function": "", "state": "", "percentage": None}
    assert result["dataVdevs"] is None


@pytest.mark.unit
def test_scrub_status_fields():
    conn = MagicMock(name="conn")
    conn.get.return_value = {
        "id": "tank",
        "scan": {
            "function": "SCRUB",
            "state": "SCANNING",
            "percentage": 42.5,
            "errors": 0,
            "start_time": "2026-07-13T00:00:00",
            "end_time": "",
        },
    }
    result = pool_ops.scrub_status(conn, "tank")
    conn.get.assert_called_once_with("/pool/id/tank")
    assert result["state"] == "SCANNING"
    assert result["percentage"] == 42.5
    assert result["errors"] == 0
    assert result["startTime"] == "2026-07-13T00:00:00"


@pytest.mark.unit
def test_scrub_status_nondict_pool_and_scan():
    conn = MagicMock(name="conn")
    conn.get.return_value = None
    result = pool_ops.scrub_status(conn, "tank")
    assert result["id"] is None
    assert result["function"] == ""


@pytest.mark.unit
def test_scrub_start_posts_and_captures_prior_scan():
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"name": "tank", "scan": {"state": "FINISHED"}},
        {"name": "backup", "scan": {"state": "SCANNING"}},
    ]
    result = pool_ops.scrub_start(conn, "tank")
    conn.post.assert_called_once_with("/pool/scrub/run", json={"name": "tank"})
    assert result["pool"] == "tank"
    assert result["action"] == "scrub_start"
    assert result["priorScan"] == {"state": "FINISHED"}


@pytest.mark.unit
def test_scrub_start_prior_scan_empty_when_lookup_fails():
    conn = MagicMock(name="conn")
    conn.get.side_effect = RuntimeError("pool list boom")
    result = pool_ops.scrub_start(conn, "tank")
    assert result["priorScan"] == {}
    conn.post.assert_called_once_with("/pool/scrub/run", json={"name": "tank"})


@pytest.mark.unit
def test_pool_capacity_zero_size_leaves_percent_none():
    """Guard against div-by-zero: a 0-byte pool must not raise."""
    conn = MagicMock(name="conn")
    conn.get.return_value = [{"name": "empty", "size": 0, "allocated": 0}]
    rows = pool_ops.pool_capacity(conn)
    assert rows[0]["usedPercent"] is None


# --------------------------------------------------------------------------- #
# overview.py — thresholds + aggregation
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_health_overview_flags_near_full_and_unhealthy():
    conn = MagicMock(name="conn")

    def _get(path, **kw):
        if path == "/pool":
            return [
                {"name": "tank", "healthy": True, "size": 100, "allocated": 90},  # 90% near-full
                {"name": "cold", "healthy": False, "size": 100, "allocated": 10},  # unhealthy
                {"name": "spare", "healthy": True, "size": 100, "allocated": 50},  # fine
            ]
        if path == "/service":
            return [
                {"service": "smb", "state": "RUNNING"},
                {"service": "nfs", "state": "STOPPED"},
            ]
        return []

    def _post(path, **kw):
        if path == "/alert/list":
            return [
                {"id": "a", "level": "CRITICAL"},
                {"id": "b", "level": "WARNING"},
                {"id": "c", "level": "CRITICAL"},
            ]
        return []

    conn.get.side_effect = _get
    conn.post.side_effect = _post

    data = ov_ops.health_overview(conn)

    assert data["nearFullThresholdPercent"] == 80.0
    assert data["pools"]["total"] == 3
    assert data["pools"]["unhealthy"] == ["cold"]
    near_full_names = [p["name"] for p in data["pools"]["nearFull"]]
    assert near_full_names == ["tank"]
    assert data["pools"]["nearFull"][0]["usedPercent"] == 90.0

    assert data["alerts"]["total"] == 3
    assert data["alerts"]["byLevel"] == {"CRITICAL": 2, "WARNING": 1}

    assert data["services"]["total"] == 2
    assert data["services"]["running"] == ["smb"]


# --------------------------------------------------------------------------- #
# snapshots.py — list filter + create/find edge paths
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_list_snapshots_filters_by_dataset():
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"id": "tank/a@s1", "name": "tank/a@s1", "dataset": "tank/a", "snapshot_name": "s1"},
        {"id": "tank/b@s1", "name": "tank/b@s1", "dataset": "tank/b", "snapshot_name": "s1"},
    ]
    rows = snap_ops.list_snapshots(conn, dataset="tank/a")
    conn.get.assert_called_once_with("/zfs/snapshot")
    assert [r["dataset"] for r in rows] == ["tank/a"]
    # unfiltered returns both
    conn.get.reset_mock()
    assert len(snap_ops.list_snapshots(conn)) == 2


@pytest.mark.unit
def test_create_snapshot_posts_and_falls_back_to_composed_id():
    conn = MagicMock(name="conn")
    conn.post.return_value = {}  # server returns no id -> compose dataset@name
    result = snap_ops.create_snapshot(conn, "tank/data", "snap1")
    conn.post.assert_called_once_with(
        "/zfs/snapshot", json={"dataset": "tank/data", "name": "snap1"}
    )
    assert result["id"] == "tank/data@snap1"
    assert result["action"] == "create_snapshot"


@pytest.mark.unit
def test_delete_snapshot_find_swallows_lookup_error():
    conn = MagicMock(name="conn")
    conn.get.side_effect = RuntimeError("snapshot list boom")
    conn.delete.return_value = True
    result = snap_ops.delete_snapshot(conn, "tank/data@snap1")
    assert result["priorState"] == {}
    conn.delete.assert_called_once_with("/zfs/snapshot/id/tank%2Fdata%40snap1")


@pytest.mark.unit
def test_health_overview_alerts_partial_failure_isolated():
    conn = MagicMock(name="conn")
    conn.get.return_value = []

    def _post(path, **kw):
        raise RuntimeError("alert boom")

    conn.post.side_effect = _post
    data = ov_ops.health_overview(conn)
    assert "error" in data["alerts"]
    assert data["pools"]["total"] == 0
    assert data["services"]["total"] == 0
