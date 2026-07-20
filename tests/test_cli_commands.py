"""CLI command coverage: read commands render mocked data, write commands drive
past dry-run/confirm through the governed twin, and the secret store commands
operate against an isolated encrypted store.

Read commands get their connection from ``_common.get_connection`` (re-imported
into each CLI module), so we monkeypatch the per-module reference to a
MagicMock. Write commands delegate to ``mcp_server.tools.*`` — those are covered
for audit elsewhere, so here we only assert the CLI branch/flow.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

import truenas_aiops.governance.audit as audit_mod
import truenas_aiops.governance.policy as policy_mod
import truenas_aiops.governance.undo as undo_mod
import truenas_aiops.secretstore as ss
from truenas_aiops.cli import app

runner = CliRunner()


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


def _mock_conn_for(monkeypatch, module_path: str, conn):
    """Patch the get_connection imported into a CLI module to return (conn, cfg)."""
    monkeypatch.setattr(module_path, lambda target=None: (conn, object()))


# --------------------------------------------------------------------------- #
# read commands
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_pool_list_and_capacity_render(monkeypatch):
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"id": "tank", "name": "tank", "status": "ONLINE", "healthy": True,
         "size": 100, "allocated": 40, "free": 60},
    ]
    _mock_conn_for(monkeypatch, "truenas_aiops.cli.pool.get_connection", conn)

    r = runner.invoke(app, ["pool", "list"])
    assert r.exit_code == 0, r.output
    assert "tank" in r.output

    r = runner.invoke(app, ["pool", "capacity"])
    assert r.exit_code == 0, r.output
    assert "usedPercent" in r.output


@pytest.mark.unit
def test_pool_get_status_scrubstatus_render(monkeypatch):
    conn = MagicMock(name="conn")
    conn.get.return_value = {
        "id": "tank", "name": "tank", "status": "ONLINE", "healthy": True,
        "path": "/mnt/tank", "encrypt": 0,
        "scan": {"function": "SCRUB", "state": "FINISHED", "percentage": 100},
        "topology": {"data": [{}]},
    }
    _mock_conn_for(monkeypatch, "truenas_aiops.cli.pool.get_connection", conn)

    assert runner.invoke(app, ["pool", "get", "tank"]).exit_code == 0
    assert runner.invoke(app, ["pool", "status", "tank"]).exit_code == 0
    assert runner.invoke(app, ["pool", "scrub-status", "tank"]).exit_code == 0


@pytest.mark.unit
def test_dataset_list_and_get_render(monkeypatch):
    conn = MagicMock(name="conn")
    conn.get.return_value = [
        {"id": "tank/data", "name": "tank/data", "type": "FILESYSTEM", "pool": "tank",
         "used": {"value": "1G"}, "available": {"value": "9G"}, "mountpoint": "/mnt/tank/data"},
    ]
    _mock_conn_for(monkeypatch, "truenas_aiops.cli.dataset.get_connection", conn)
    r = runner.invoke(app, ["dataset", "list"])
    assert r.exit_code == 0 and "tank/data" in r.output

    conn.get.return_value = {"id": "tank/data", "name": "tank/data", "type": "FILESYSTEM"}
    r = runner.invoke(app, ["dataset", "get", "tank/data"])
    assert r.exit_code == 0 and "tank/data" in r.output


@pytest.mark.unit
def test_disk_alert_replication_service_system_overview_read(monkeypatch):
    conn = MagicMock(name="conn")
    conn.get.return_value = [{"name": "sda", "serial": "S", "model": "M", "size": 1,
                              "type": "HDD", "pool": "tank"}]
    conn.post.return_value = []
    for module in (
        "truenas_aiops.cli.disk.get_connection",
        "truenas_aiops.cli.alert.get_connection",
        "truenas_aiops.cli.replication.get_connection",
        "truenas_aiops.cli.service.get_connection",
        "truenas_aiops.cli.system.get_connection",
        "truenas_aiops.cli.overview.get_connection",
    ):
        _mock_conn_for(monkeypatch, module, conn)

    assert runner.invoke(app, ["disk", "list"]).exit_code == 0
    assert runner.invoke(app, ["disk", "smart"]).exit_code == 0

    conn.post.return_value = [{"id": "a", "level": "INFO", "formatted": "hi"}]
    assert runner.invoke(app, ["alert", "list"]).exit_code == 0

    conn.get.return_value = [{"id": 1, "name": "r", "job": {"state": "FINISHED"}}]
    assert runner.invoke(app, ["replication", "list"]).exit_code == 0
    assert runner.invoke(app, ["replication", "cloudsync"]).exit_code == 0

    conn.get.return_value = [{"id": 1, "service": "smb", "state": "RUNNING", "enable": True}]
    assert runner.invoke(app, ["service", "list"]).exit_code == 0

    conn.get.return_value = {"version": "TrueNAS-SCALE-24.04", "hostname": "n"}
    assert runner.invoke(app, ["system"]).exit_code == 0

    conn.get.return_value = []
    conn.post.return_value = []
    assert runner.invoke(app, ["overview"]).exit_code == 0


@pytest.mark.unit
def test_read_command_translates_api_error_to_one_liner(monkeypatch):
    from truenas_aiops.connection import TrueNASApiError

    conn = MagicMock(name="conn")
    conn.get.side_effect = TrueNASApiError("boom on wire", status_code=500, path="/pool")
    _mock_conn_for(monkeypatch, "truenas_aiops.cli.pool.get_connection", conn)
    r = runner.invoke(app, ["pool", "list"])
    assert r.exit_code == 1
    assert "Error:" in r.output


# --------------------------------------------------------------------------- #
# write commands — dry-run and confirmed branches
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_dataset_create_dry_run_makes_no_call(monkeypatch):
    gov = MagicMock(name="gov_dataset_create")
    monkeypatch.setattr("truenas_aiops.cli.dataset.gov.dataset_create", gov)
    r = runner.invoke(app, ["dataset", "create", "tank/new", "--dry-run"])
    assert r.exit_code == 0
    assert "DRY-RUN" in r.output
    gov.assert_not_called()


@pytest.mark.unit
def test_dataset_create_confirmed_calls_governed_twin(monkeypatch):
    gov = MagicMock(name="gov_dataset_create", return_value={"id": "tank/new"})
    monkeypatch.setattr("truenas_aiops.cli.dataset.gov.dataset_create", gov)
    r = runner.invoke(app, ["dataset", "create", "tank/new"])
    assert r.exit_code == 0, r.output
    gov.assert_called_once()
    assert gov.call_args.kwargs["name"] == "tank/new"


@pytest.mark.unit
def test_service_restart_dry_run_and_confirm(monkeypatch):
    """--dry-run now routes THROUGH the governed tool so its guards run.

    It previously returned early with a printed banner, which meant the CLI
    preview could show green for a restart the real call would refuse.
    """
    gov = MagicMock(name="gov_service_restart", return_value={"dryRun": True})
    monkeypatch.setattr("truenas_aiops.cli.service.gov.service_restart", gov)

    r = runner.invoke(app, ["service", "restart", "smb", "--dry-run"])
    assert r.exit_code == 0 and "DRY-RUN" in r.output
    gov.assert_called_once()
    assert gov.call_args.kwargs["dry_run"] is True

    gov.reset_mock()
    gov.return_value = {}
    r = runner.invoke(app, ["service", "restart", "smb"], input="y\ny\n")
    assert r.exit_code == 0, r.output
    gov.assert_called_once()
    assert gov.call_args.kwargs.get("dry_run") is None


@pytest.mark.unit
def test_service_restart_dry_run_surfaces_a_guard_refusal(monkeypatch):
    """A refused preview must exit non-zero, not print a green banner."""
    gov = MagicMock(
        name="gov_service_restart",
        return_value={"error": "Refusing to restart 'nosuchsvc': ...", "hint": "..."},
    )
    monkeypatch.setattr("truenas_aiops.cli.service.gov.service_restart", gov)
    r = runner.invoke(app, ["service", "restart", "nosuchsvc", "--dry-run"])
    assert r.exit_code == 1
    assert "Refusing to restart" in r.output
    assert "DRY-RUN" not in r.output


@pytest.mark.unit
def test_service_restart_aborts_on_declined_confirm(monkeypatch):
    gov = MagicMock(name="gov_service_restart")
    monkeypatch.setattr("truenas_aiops.cli.service.gov.service_restart", gov)
    r = runner.invoke(app, ["service", "restart", "smb"], input="n\n")
    assert r.exit_code != 0
    gov.assert_not_called()


@pytest.mark.unit
def test_pool_scrub_start_command(monkeypatch):
    gov = MagicMock(name="gov_scrub", return_value={})
    monkeypatch.setattr("truenas_aiops.cli.pool.gov.pool_scrub_start", gov)
    r = runner.invoke(app, ["pool", "scrub-start", "tank"])
    assert r.exit_code == 0, r.output
    gov.assert_called_once()
    assert gov.call_args.kwargs["pool_name"] == "tank"


# --------------------------------------------------------------------------- #
# undo commands
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_undo_list_and_apply_flow(gov_home, monkeypatch):
    # record an inverse token pointing at a real governed read tool (pool_list)
    descriptor = {"tool": "pool_list", "params": {}}
    uid = undo_mod.get_undo_store().record(
        skill="probe", tool="orig", undo_descriptor=descriptor
    )

    r = runner.invoke(app, ["undo", "list"])
    assert r.exit_code == 0
    assert uid in r.output

    # dry-run preview does not consume the token
    r = runner.invoke(app, ["undo", "apply", uid, "--dry-run"])
    assert r.exit_code == 0 and "DRY-RUN" in r.output
    assert undo_mod.get_undo_store().get(uid)["status"] == "recorded"

    # confirmed apply dispatches the inverse (pool_list needs no live conn beyond
    # the mocked one) and consumes the token
    conn = MagicMock(name="conn")
    conn.get.return_value = []
    monkeypatch.setattr(
        "mcp_server.tools.pools._get_connection", lambda target=None: conn
    )
    monkeypatch.setenv("TRUENAS_AUDIT_APPROVED_BY", "pytest")
    r = runner.invoke(app, ["undo", "apply", uid], input="y\ny\n")
    assert r.exit_code == 0, r.output
    assert undo_mod.get_undo_store().get(uid)["status"] == "applied"


# --------------------------------------------------------------------------- #
# secret store commands
# --------------------------------------------------------------------------- #
@pytest.fixture
def secret_home(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(ss, "SECRETS_FILE", tmp_path / "secrets.enc")
    monkeypatch.setattr(ss, "LEGACY_ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(ss, "_cached", None)
    monkeypatch.setenv("TRUENAS_AIOPS_MASTER_PASSWORD", "master-pw")
    return tmp_path


@pytest.mark.unit
def test_secret_set_list_rm(secret_home):
    r = runner.invoke(app, ["secret", "set", "nas1", "--value", "api-key-xyz"])
    assert r.exit_code == 0, r.output
    assert "Stored encrypted API key" in r.output

    r = runner.invoke(app, ["secret", "list"])
    assert r.exit_code == 0
    assert "nas1" in r.output

    r = runner.invoke(app, ["secret", "rm", "nas1"])
    assert r.exit_code == 0

    r = runner.invoke(app, ["secret", "list"])
    assert r.exit_code == 0
    assert "No secrets stored yet" in r.output


@pytest.mark.unit
def test_secret_set_value_is_not_echoed(secret_home):
    r = runner.invoke(app, ["secret", "set", "nas1", "--value", "top-secret-key"])
    assert "top-secret-key" not in r.output


@pytest.mark.unit
def test_secret_migrate_nothing_to_migrate(secret_home):
    r = runner.invoke(app, ["secret", "migrate"])
    assert r.exit_code == 0
    assert "Nothing to migrate" in r.output


@pytest.mark.unit
def test_secret_rotate_password(secret_home, monkeypatch):
    # seed a secret to rotate
    runner.invoke(app, ["secret", "set", "nas1", "--value", "k"])

    pws = iter(["new-master-pw", "new-master-pw"])
    monkeypatch.setattr(
        "truenas_aiops.cli.secret.getpass.getpass", lambda *a, **k: next(pws)
    )
    r = runner.invoke(app, ["secret", "rotate-password"])
    assert r.exit_code == 0, r.output
    assert "rotated" in r.output.lower()


@pytest.mark.unit
def test_secret_rotate_password_mismatch_aborts(secret_home, monkeypatch):
    runner.invoke(app, ["secret", "set", "nas1", "--value", "k"])
    pws = iter(["new-pw", "different-pw"])
    monkeypatch.setattr(
        "truenas_aiops.cli.secret.getpass.getpass", lambda *a, **k: next(pws)
    )
    r = runner.invoke(app, ["secret", "rotate-password"])
    assert r.exit_code == 1
    assert "did not match" in r.output.lower()
