"""Configuration management for TrueNAS AIops.

Loads connection targets and settings from a YAML config file. The secret (the
TrueNAS API key / Bearer token) is NEVER stored in the config file and never on
disk in plaintext: it lives in the encrypted store
``~/.truenas-aiops/secrets.enc`` (see :mod:`truenas_aiops.secretstore`). For
backward compatibility a legacy plaintext env var (``TRUENAS_<TARGET>_APIKEY``)
is still honoured as a fallback, with a warning nudging migration to the
encrypted store.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from truenas_aiops.governance.paths import ops_home
from truenas_aiops.secretstore import (
    MasterPasswordError,
    SecretStoreError,
    get_secret,
    has_store,
)

CONFIG_DIR = ops_home()
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ENV_FILE = CONFIG_DIR / ".env"

DEFAULT_API_PATH = "/api/v2.0"

# Legacy env-var prefix/suffix; also used by the migration helper.
SECRET_ENV_PREFIX = "TRUENAS_"  # nosec B105 — env-var name, not a secret
SECRET_ENV_SUFFIX = "_APIKEY"  # nosec B105 — env-var name, not a secret

_log = logging.getLogger("truenas-aiops.config")


def _secret_env_key(name: str) -> str:
    """Legacy per-target API-key env var name, e.g. TRUENAS_NAS1_APIKEY."""
    return f"{SECRET_ENV_PREFIX}{name.upper().replace('-', '_')}{SECRET_ENV_SUFFIX}"


def _resolve_secret(name: str) -> str:
    """Return a target's API key: encrypted store first, then legacy env var."""
    if has_store():
        try:
            return get_secret(name)
        except MasterPasswordError:
            # A wrong or missing master password is NOT "this target has no
            # secret". Falling through resurfaced it as "No API key for target
            # X", sending the operator to add a credential that is already
            # there. MasterPasswordError subclasses SecretStoreError, so the
            # broad catch below would swallow it — re-raise first.
            raise
        except SecretStoreError:
            pass  # no secret stored for this target — try the legacy env var
    legacy = os.environ.get(_secret_env_key(name))
    if legacy:
        _log.warning(
            "Using plaintext env var %s. Migrate to the encrypted store with "
            "'truenas-aiops secret migrate'.",
            _secret_env_key(name),
        )
        return legacy
    raise OSError(
        f"No API key for target '{name}'. Add one with "
        f"'truenas-aiops secret set {name}' (stored encrypted), or run "
        f"'truenas-aiops init'."
    )


@dataclass(frozen=True)
class TargetConfig:
    """A TrueNAS SCALE REST API v2.0 connection target.

    The API key is sourced from the encrypted secret store (see ``api_key``),
    never the config file. ``host`` is the TrueNAS server; ``port`` defaults to
    the HTTPS port 443; ``api_path`` is the REST base path (``/api/v2.0``).
    """

    name: str
    host: str
    port: int = 443
    verify_ssl: bool = True
    scheme: str = "https"
    """Transport scheme — ``https`` (default) or ``http``.

    Defaults to ``https``, so nothing changes for an existing config. It exists
    because the URL was previously hardcoded to ``https://`` with no way to
    override it, which made a plain-HTTP endpoint behind a reverse proxy simply
    unreachable — with a TLS record-layer error as the only clue. Sibling tools
    in this line take a free-form ``base_url``; the ones that CONSTRUCT their
    URL are the ones that needed this knob.
    """
    api_path: str = DEFAULT_API_PATH

    @property
    def api_key(self) -> str:
        return _resolve_secret(self.name)

    def __post_init__(self) -> None:
        if self.scheme not in ("https", "http"):
            raise ValueError(
                f"Target '{self.name}': scheme must be 'https' or 'http', "
                f"got '{self.scheme}'."
            )

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}{self.api_path}"


@dataclass(frozen=True)
class AppConfig:
    """Top-level application config."""

    targets: tuple[TargetConfig, ...] = ()

    def get_target(self, name: str) -> TargetConfig:
        for t in self.targets:
            if t.name == name:
                return t
        available = ", ".join(t.name for t in self.targets) or "(none)"
        raise KeyError(f"Target '{name}' not found. Available: {available}")

    @property
    def default_target(self) -> TargetConfig:
        if not self.targets:
            raise ValueError("No targets configured. Check config.yaml")
        return self.targets[0]


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load config from YAML; the API key comes from the encrypted store."""
    path = config_path or CONFIG_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"Run 'truenas-aiops init' to set up a target and store its API key "
            f"encrypted, or create {CONFIG_FILE} with a 'targets' list."
        )

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    targets = tuple(
        TargetConfig(
            name=t["name"],
            host=t["host"],
            port=t.get("port", 443),
            verify_ssl=t.get("verify_ssl", True),
            scheme=t.get("scheme", "https"),
            api_path=t.get("api_path", DEFAULT_API_PATH),
        )
        for t in raw.get("targets", [])
    )

    return AppConfig(targets=targets)
