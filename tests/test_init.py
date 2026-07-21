"""Tests for the ``truenas-aiops init`` onboarding wizard.

The wizard is driven end-to-end through Typer's CliRunner with every path
(config.yaml, secrets.enc) isolated under tmp_path. The master
password comes from TRUENAS_AIOPS_MASTER_PASSWORD (the non-interactive path)
and the hidden API-key prompt is patched at the getpass boundary.
"""

from __future__ import annotations

import getpass as getpass_mod

import pytest
import yaml
from typer.testing import CliRunner

import truenas_aiops.cli.init as init_mod
import truenas_aiops.config as config_mod
import truenas_aiops.doctor as doctor_mod
import truenas_aiops.secretstore as ss

pytestmark = pytest.mark.unit

MASTER_PW = "init-master-pw"
API_KEY = "1-truenas-api-key-uuid"

# Wizard answers: name, host, accept the port default (443), accept the TLS
# confirm default (True), no second target, decline the trailing doctor run.
WIZARD_INPUT = "nas1\n192.0.2.10\n\n\nn\nn\n"


@pytest.fixture
def init_home(tmp_path, monkeypatch):
    """Isolate config + secret store + governance home under tmp_path.

    Module-level path constants are import-time snapshots of ``ops_home()``,
    so the env var alone is not enough — patch every module that captured them.
    """
    config_file = tmp_path / "config.yaml"
    secrets_file = tmp_path / "secrets.enc"
    monkeypatch.setenv("TRUENAS_AIOPS_HOME", str(tmp_path))
    monkeypatch.setenv(ss.MASTER_PASSWORD_ENV, MASTER_PW)
    monkeypatch.setattr(init_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(init_mod, "CONFIG_FILE", config_file)
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", config_file)
    monkeypatch.setattr(ss, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(ss, "SECRETS_FILE", secrets_file)
    monkeypatch.setattr(ss, "LEGACY_ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(ss, "_cached", None)
    # The hidden per-target API-key prompt bypasses CliRunner stdin.
    monkeypatch.setattr(getpass_mod, "getpass", lambda prompt="": API_KEY)
    return tmp_path


def _run_init(input_text: str = WIZARD_INPUT):
    from truenas_aiops.cli import app

    return CliRunner().invoke(app, ["init"], input=input_text)


def test_init_writes_config_with_entered_values(init_home):
    result = _run_init()
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load((init_home / "config.yaml").read_text("utf-8"))
    assert raw["targets"] == [
        {
            "name": "nas1",
            "host": "192.0.2.10",
            "port": 443,  # accepted default must land in config
            "verify_ssl": True,  # TLS confirm default=True respected
            "api_path": "/api/v2.0",
        }
    ]


def test_init_tls_decline_writes_verify_ssl_false(init_home):
    # Explicit "n" on the TLS confirm (self-signed lab certs).
    result = _run_init("nas1\n192.0.2.10\n\nn\nn\nn\n")
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load((init_home / "config.yaml").read_text("utf-8"))
    assert raw["targets"][0]["verify_ssl"] is False


def test_init_stores_secret_encrypted_not_in_config(init_home):
    result = _run_init()
    assert result.exit_code == 0, result.output
    # API key is readable back through the secret store API...
    assert ss.SecretStore.unlock(MASTER_PW).get("nas1") == API_KEY
    # ...and never lands in plaintext in config.yaml or secrets.enc.
    assert API_KEY not in (init_home / "config.yaml").read_text("utf-8")
    assert API_KEY not in (init_home / "secrets.enc").read_text("utf-8")


def test_init_writes_no_policy_rules(init_home):
    """The skill no longer authorizes, so init seeds no rules.yaml — a fresh
    install delivers full functionality and leaves permission to the account."""
    result = _run_init()
    assert result.exit_code == 0, result.output
    assert not (init_home / "rules.yaml").exists()


def test_init_declining_doctor_confirm_skips_doctor(init_home, monkeypatch):
    calls: list[bool] = []
    monkeypatch.setattr(doctor_mod, "run_doctor", lambda: calls.append(True) or 0)
    result = _run_init()  # WIZARD_INPUT ends with an explicit "n"
    assert result.exit_code == 0, result.output
    assert calls == []


def test_init_accepting_doctor_confirm_runs_doctor(init_home, monkeypatch):
    calls: list[bool] = []
    monkeypatch.setattr(doctor_mod, "run_doctor", lambda: calls.append(True) or 0)
    # Empty last answer accepts the confirm's default=True.
    result = _run_init("nas1\n192.0.2.10\n\n\nn\n\n")
    assert result.exit_code == 0, result.output
    assert calls == [True]


def test_init_overwrite_existing_target(init_home):
    result = _run_init()
    assert result.exit_code == 0, result.output
    # Same name again: confirm overwrite, new host, accept defaults.
    result = _run_init("nas1\ny\n192.0.2.20\n\n\nn\nn\n")
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load((init_home / "config.yaml").read_text("utf-8"))
    assert [t["host"] for t in raw["targets"]] == ["192.0.2.20"]
