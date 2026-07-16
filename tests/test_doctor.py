"""Tests for ``truenas_aiops.doctor.run_doctor``.

All filesystem paths are redirected to a tmp dir and the connection layer is
mocked at the ConnectionManager boundary — no test ever touches a real
TrueNAS host or the real ``~/.truenas-aiops``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import yaml

import truenas_aiops.config as config_mod
import truenas_aiops.doctor as doctor_mod
import truenas_aiops.secretstore as ss
from truenas_aiops.doctor import run_doctor

pytestmark = pytest.mark.unit

MASTER_PW = "test-master-pw"


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Redirect every config/secret path constant at a throwaway directory."""
    config_file = tmp_path / "config.yaml"
    env_file = tmp_path / ".env"
    secrets_file = tmp_path / "secrets.enc"

    monkeypatch.setenv("TRUENAS_AIOPS_HOME", str(tmp_path))
    monkeypatch.setenv(ss.MASTER_PASSWORD_ENV, MASTER_PW)

    # config module reads its globals at call time.
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", config_file)
    monkeypatch.setattr(config_mod, "ENV_FILE", env_file)
    # doctor imported the names directly; patch its namespace too.
    monkeypatch.setattr(doctor_mod, "CONFIG_FILE", config_file)
    monkeypatch.setattr(doctor_mod, "ENV_FILE", env_file)
    monkeypatch.setattr(doctor_mod, "SECRETS_FILE", secrets_file)
    # secret store paths + cache.
    monkeypatch.setattr(ss, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(ss, "SECRETS_FILE", secrets_file)
    monkeypatch.setattr(ss, "LEGACY_ENV_FILE", env_file)
    monkeypatch.setattr(ss, "_cached", None)
    return tmp_path


def _write_config(home, targets: list[dict]) -> None:
    (home / "config.yaml").write_text(yaml.safe_dump({"targets": targets}), "utf-8")


def _target(name: str = "nas1") -> dict:
    return {"name": name, "host": "192.0.2.10"}


def _store_secret(name: str = "nas1", value: str = "api-key-uuid") -> None:
    ss.SecretStore.unlock(MASTER_PW).set(name, value)


@pytest.fixture
def ok_connection(monkeypatch):
    """A ConnectionManager whose connect() answers /system/info happily."""
    mgr = MagicMock(name="ConnectionManager")
    mgr.return_value.connect.return_value.get.return_value = {"version": "24.10.1"}
    monkeypatch.setattr("truenas_aiops.connection.ConnectionManager", mgr)
    return mgr


def test_missing_config_file(isolated_home, capsys):
    assert run_doctor() == 1
    out = capsys.readouterr().out
    assert "Config file missing" in out


def test_config_load_failure_reported_not_raised(isolated_home, capsys):
    # A target without required keys makes load_config raise; doctor must
    # report the failure as a check, never a traceback.
    _write_config(isolated_home, [{"host": "192.0.2.10"}])
    assert run_doctor() == 1
    assert "Config load failed" in capsys.readouterr().out


def test_no_targets_configured(isolated_home, capsys):
    _write_config(isolated_home, [])
    assert run_doctor() == 1
    assert "No targets configured" in capsys.readouterr().out


def test_all_healthy_exits_zero(isolated_home, ok_connection, capsys):
    _write_config(isolated_home, [_target()])
    _store_secret()
    assert run_doctor() == 0
    # Rich wraps long lines; normalize whitespace before matching.
    out = " ".join(capsys.readouterr().out.split())
    assert "Config file present" in out
    assert "1 target(s) configured" in out
    assert "Encrypted secret store present" in out
    assert "API key present for 'nas1'" in out
    assert "Connected to 'nas1' (192.0.2.10) — TrueNAS 24.10.1" in out
    ok_connection.return_value.connect.assert_called_once_with("nas1")


def test_skip_auth_never_touches_connection_layer(isolated_home, monkeypatch, capsys):
    _write_config(isolated_home, [_target()])
    _store_secret()

    def _boom(*a, **k):  # pragma: no cover — must not be reached
        raise AssertionError("ConnectionManager must not be constructed with --skip-auth")

    monkeypatch.setattr("truenas_aiops.connection.ConnectionManager", _boom)
    assert run_doctor(skip_auth=True) == 0
    assert "Skipping connectivity check" in capsys.readouterr().out


def test_missing_secret_is_a_problem(isolated_home, capsys):
    _write_config(isolated_home, [_target()])
    _store_secret("other-target")  # store exists, but not for this target
    assert run_doctor(skip_auth=True) == 1
    out = " ".join(capsys.readouterr().out.split())
    assert "No API key for target 'nas1'" in out


def test_no_secret_store_yet_warns_and_fails(isolated_home, capsys):
    _write_config(isolated_home, [_target()])
    assert run_doctor(skip_auth=True) == 1
    out = capsys.readouterr().out
    assert "No secret store yet" in out


def test_legacy_env_file_warns_but_env_secret_passes(isolated_home, monkeypatch, capsys):
    _write_config(isolated_home, [_target()])
    (isolated_home / ".env").write_text("TRUENAS_NAS1_APIKEY=legacy\n")
    monkeypatch.setenv("TRUENAS_NAS1_APIKEY", "legacy")
    assert run_doctor(skip_auth=True) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "legacy plaintext .env" in out
    assert "API key present for 'nas1'" in out


def test_connect_failure_reported_per_target(isolated_home, ok_connection, capsys):
    _write_config(isolated_home, [_target("nas-a"), _target("nas-b")])
    _store_secret("nas-a")
    _store_secret("nas-b")

    def _connect(name):
        if name == "nas-b":
            raise ConnectionError("connection refused")
        conn = MagicMock()
        conn.get.return_value = {"version": "24.10.1"}
        return conn

    ok_connection.return_value.connect.side_effect = _connect
    assert run_doctor() == 1
    out = " ".join(capsys.readouterr().out.split())
    assert "Connected to 'nas-a'" in out
    assert "Connect to 'nas-b' failed: connection refused" in out


def test_permission_warning_surfaced(isolated_home, capsys):
    _write_config(isolated_home, [_target()])
    _store_secret()
    (isolated_home / "secrets.enc").chmod(0o644)
    assert run_doctor(skip_auth=True) == 0
    # Rich wraps long lines; normalize whitespace before matching.
    out = " ".join(capsys.readouterr().out.split())
    assert "should be 600" in out
