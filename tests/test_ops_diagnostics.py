"""Tests for the read-only diagnostics / RCA layer.

Two halves:
  * pure heuristics (``truenas_aiops.ops.diagnostics``) — each threshold trip, a
    healthy fleet stays clean, worst-first ordering, and missing-field robustness.
  * the two governed MCP tools driven with a mocked connection — assert they carry
    the harness marker and collect the right telemetry before delegating.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import truenas_aiops.governance.audit as audit_mod
import truenas_aiops.governance.policy as policy_mod
import truenas_aiops.governance.undo as undo_mod
from mcp_server.tools import diagnostics as diag_tools
from truenas_aiops.ops import diagnostics as diag


# --------------------------------------------------------------------------- #
# pool_health_findings
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_pool_degraded_status_is_critical():
    pools = [{"name": "tank", "status": "DEGRADED", "healthy": False, "size": 100, "allocated": 10}]
    findings = diag.pool_health_findings(pools)["findings"]
    top = findings[0]
    assert top["severity"] == "critical"
    assert "DEGRADED" in top["detail"]
    assert top["resource"] == "tank"


@pytest.mark.unit
def test_pool_error_counters_are_flagged_with_measured_counts():
    pools = [
        {
            "name": "tank",
            "status": "ONLINE",
            "healthy": True,
            "size": 100,
            "allocated": 10,
            "topology": {
                "data": [
                    {
                        "stats": {"read_errors": 2, "write_errors": 0, "checksum_errors": 5},
                        "children": [
                            {"stats": {"read_errors": 1, "write_errors": 0, "checksum_errors": 0}}
                        ],
                    },
                ]
            },
            "scan": {"errors": 3},
        }
    ]
    findings = diag.pool_health_findings(pools)["findings"]
    errs = [f for f in findings if f["signal"] == "pool I/O errors"]
    assert len(errs) == 1
    # read = 2 (vdev) + 1 (child) = 3; checksum = 5; scan = 3
    assert "read=3" in errs[0]["detail"]
    assert "checksum=5" in errs[0]["detail"]
    assert "scan=3" in errs[0]["detail"]


@pytest.mark.unit
def test_pool_capacity_warning_and_critical_thresholds():
    warn = diag.pool_health_findings(
        [{"name": "w", "status": "ONLINE", "healthy": True, "size": 100, "allocated": 85}]
    )["findings"]
    assert warn[0]["severity"] == "warning"
    assert "85.0%" in warn[0]["detail"]

    crit = diag.pool_health_findings(
        [{"name": "c", "status": "ONLINE", "healthy": True, "size": 100, "allocated": 95}]
    )["findings"]
    assert crit[0]["severity"] == "critical"
    assert "95.0%" in crit[0]["detail"]


@pytest.mark.unit
def test_pool_healthy_fleet_is_clean():
    pools = [
        {
            "name": "tank",
            "status": "ONLINE",
            "healthy": True,
            "size": 100,
            "allocated": 40,
            "topology": {"data": [{"stats": {"read_errors": 0}}]},
            "scan": {"errors": 0},
        }
    ]
    result = diag.pool_health_findings(pools)
    assert result["findings"] == []
    assert result["poolsAnalyzed"] == 1
    assert result["summary"][0]["usedPercent"] == 40.0


@pytest.mark.unit
def test_pool_findings_ranked_worst_first():
    pools = [
        {"name": "warn", "status": "ONLINE", "healthy": True, "size": 100, "allocated": 82},
        {"name": "crit", "status": "FAULTED", "healthy": False, "size": 100, "allocated": 5},
    ]
    findings = diag.pool_health_findings(pools)["findings"]
    assert findings[0]["severity"] == "critical"
    assert findings[-1]["severity"] == "warning"


@pytest.mark.unit
def test_pool_missing_fields_do_not_crash():
    # No size/topology/scan/status — must degrade gracefully, not raise.
    result = diag.pool_health_findings([{}, {"name": "x"}])
    assert result["poolsAnalyzed"] == 2
    assert result["summary"][0]["usedPercent"] is None
    assert result["summary"][0]["errors"] == {"read": 0, "write": 0, "checksum": 0, "scan": 0}


# --------------------------------------------------------------------------- #
# alert_capacity_findings
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_active_critical_alert_is_flagged_and_counted():
    alerts = [
        {"level": "CRITICAL", "formatted": "pool tank degraded", "dismissed": False},
        {"level": "WARNING", "formatted": "smart warning", "dismissed": False},
        {"level": "CRITICAL", "formatted": "already handled", "dismissed": True},
    ]
    result = diag.alert_capacity_findings(alerts, [])
    findings = result["findings"]
    assert findings[0]["severity"] == "critical"
    assert "pool tank degraded" in findings[0]["detail"]
    # dismissed alert is skipped from findings AND from level counts
    assert result["alertLevels"] == {"CRITICAL": 1, "WARNING": 1}
    assert findings[-1]["severity"] == "warning"


@pytest.mark.unit
def test_dataset_capacity_uses_quota_then_available():
    datasets = [
        # quota set: 95 of 100 bytes -> 95% critical
        {
            "name": "tank/q",
            "used": {"parsed": 95},
            "quota": {"parsed": 100},
            "available": {"parsed": 5},
        },
        # no quota: used 82 / (82+18) -> 82% warning
        {
            "name": "tank/a",
            "used": {"parsed": 82},
            "quota": {"parsed": 0},
            "available": {"parsed": 18},
        },
        # roomy: 10 / (10+90) -> 10% clean
        {
            "name": "tank/ok",
            "used": {"parsed": 10},
            "quota": {"parsed": 0},
            "available": {"parsed": 90},
        },
    ]
    findings = diag.alert_capacity_findings([], datasets)["findings"]
    sigs = {f["resource"]: f["severity"] for f in findings}
    assert sigs["tank/q"] == "critical"
    assert sigs["tank/a"] == "warning"
    assert "tank/ok" not in sigs


@pytest.mark.unit
def test_alert_capacity_clean_and_robust_to_missing_fields():
    result = diag.alert_capacity_findings([], [{}, {"name": "tank/x"}])
    assert result["findings"] == []
    assert result["datasetsAnalyzed"] == 2
    assert result["alertLevels"] == {}


# --------------------------------------------------------------------------- #
# governed MCP tools (mocked connection)
# --------------------------------------------------------------------------- #
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


@pytest.mark.unit
def test_pool_health_rca_is_governed_and_collects_pool_listing(gov_home, monkeypatch):
    assert diag_tools.pool_health_rca._is_governed_tool is True
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"name": "tank", "status": "FAULTED", "healthy": False, "size": 100, "allocated": 5},
    ]
    monkeypatch.setattr(diag_tools, "_get_connection", lambda target=None: conn)

    result = diag_tools.pool_health_rca()
    conn.get.assert_called_once_with("/pool")
    assert result["poolsAnalyzed"] == 1
    assert result["findings"][0]["severity"] == "critical"


@pytest.mark.unit
def test_alert_and_capacity_rca_is_governed_and_collects_both(gov_home, monkeypatch):
    assert diag_tools.alert_and_capacity_rca._is_governed_tool is True
    conn = MagicMock(name="conn")
    conn.post.return_value = [
        {"id": "a1", "level": "CRITICAL", "formatted": "disk failed", "dismissed": False},
    ]
    conn.get.return_value = [
        {
            "name": "tank/data",
            "used": {"parsed": 95},
            "quota": {"parsed": 100},
            "available": {"parsed": 5},
        },
    ]
    monkeypatch.setattr(diag_tools, "_get_connection", lambda target=None: conn)

    result = diag_tools.alert_and_capacity_rca()
    conn.post.assert_called_once_with("/alert/list")
    conn.get.assert_called_once_with("/pool/dataset")
    assert result["alertsAnalyzed"] == 1
    assert result["datasetsAnalyzed"] == 1
    # one critical alert + one critical dataset, both surfaced
    assert all(f["severity"] == "critical" for f in result["findings"])
    assert len(result["findings"]) == 2


@pytest.mark.unit
def test_rank_assigns_explicit_worst_first_rank():
    """Findings state their priority explicitly, not implicitly by list order.

    A consumer — notably a smaller local model summarising the result — must not
    have to infer urgency from a finding's position in the list.
    """
    from truenas_aiops.ops import diagnostics as _diag

    ranked = _diag._rank([{"severity": "info"}, {"severity": "critical"}, {"severity": "warning"}])
    assert [f["severity"] for f in ranked] == ["critical", "warning", "info"]
    assert [f["rank"] for f in ranked] == [1, 2, 3]
