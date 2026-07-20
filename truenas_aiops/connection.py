"""Connection management for the TrueNAS SCALE REST API v2.0.

Thin httpx wrapper with per-target session reuse and static Bearer auth:

  * TrueNAS issues a long-lived **API key** (created in the web UI under
    Credentials → API Keys). Every request carries
    ``Authorization: Bearer <api_key>`` — there is no token-exchange handshake
    (unlike OAuth2 systems), so the key is sent directly.
  * ``base_url`` already includes the API base path (``/api/v2.0``), so callers
    pass resource paths like ``/pool`` or ``/system/info``.

All non-2xx responses are translated centrally into ``TrueNASApiError`` with a
teaching message — REST-wrapper skills translate HTTP errors at the connection
layer from the first version rather than leaking raw tracebacks. One case gets
its own class: a 404 on an endpoint that exists on every REST-capable TrueNAS
means the REST base path is not being served at all (TrueNAS 26 removed REST),
which raises :class:`UnsupportedServerVersion` rather than a misleading
"resource not found — the id may be stale". See :mod:`truenas_aiops.version_support`.

The httpx client is injectable for tests: pass ``client=`` to
``TrueNASConnection`` to substitute a mock that implements ``request`` / ``close``.
"""

from __future__ import annotations

import atexit
import weakref
from typing import Any
from urllib.parse import quote

import httpx

from truenas_aiops.config import AppConfig, TargetConfig, load_config
from truenas_aiops.version_support import REST_REMOVED_MAJOR, WEBSOCKET_API_PATH

_TIMEOUT = 30.0

# Endpoints that exist on *every* REST-capable TrueNAS build — collection roots
# and singletons, no caller-supplied id in the path. A 404 on one of these is
# not a stale id; it means the REST base path itself is not being served, which
# is exactly how a TrueNAS 26 appliance (REST removed) answers.
_ALWAYS_PRESENT_PATHS = frozenset(
    {
        "/system/info",
        "/pool",
        "/pool/dataset",
        "/zfs/snapshot",
        "/disk",
        "/service",
        "/alert/list",
        "/replication",
        "/cloudsync",
        "/smart/test/results",
    }
)


def _seg(value: Any) -> str:
    """URL-encode one path segment (agent-supplied id) for safe interpolation.

    TrueNAS ids (datasets like ``tank/data``, snapshots like ``tank/data@snap1``)
    must be percent-encoded when placed in a URL path — this also prevents an
    id containing ``../`` or ``?`` from rewriting the request path.
    """
    return quote(str(value), safe="")


class TrueNASApiError(Exception):
    """A TrueNAS REST API call failed; carries a teaching message + status code."""

    def __init__(self, message: str, *, status_code: int | None = None, path: str = "") -> None:
        self.status_code = status_code
        self.path = path
        super().__init__(message)


class UnsupportedServerVersion(TrueNASApiError):  # noqa: N818 — teaching error, reads as a statement
    """This TrueNAS server cannot serve the REST API that truenas-aiops speaks.

    Subclasses :class:`TrueNASApiError` so every existing ``except
    TrueNASApiError`` handler (and the CLI's error translator) keeps working,
    while staying distinguishable — a bare 404 here was reported as "resource
    not found … the id may be stale", sending the operator to hunt a stale-id
    problem that does not exist when the real cause is that TrueNAS 26 removed
    the REST API wholesale.
    """


def _looks_like_rest_removed(path: str) -> bool:
    """True when a 404 on ``path`` means the REST base path is gone, not the id."""
    return path.split("?", 1)[0].rstrip("/") in _ALWAYS_PRESENT_PATHS


def _rest_removed_message(base_url: str, path: str) -> str:
    """Explain a 404 on an endpoint that exists on every REST-capable TrueNAS."""
    return (
        f"The REST API at {base_url} returned 404 for {path} — an endpoint that exists on "
        f"every TrueNAS build still serving REST. The likely cause is that this server is "
        f"TrueNAS {REST_REMOVED_MAJOR} or newer, which REMOVED the REST API in favour of "
        f"JSON-RPC 2.0 over a WebSocket at {WEBSOCKET_API_PATH}; truenas-aiops speaks REST "
        f"only and cannot manage such a server. Check the version in the TrueNAS UI (System "
        f"→ Update). If it is 25.10.x or older, then REST is still there and the base path is "
        f"wrong instead — check 'api_path' in ~/.truenas-aiops/config.yaml (expected "
        f"/api/v2.0)."
    )


def _teaching_message(status: int, path: str, body: str) -> str:
    """Map a non-2xx status to an actionable, teaching error message."""
    snippet = body[:200].strip()
    if status in (401, 403):
        return (
            f"Authentication/authorization failed ({status}) on {path}. "
            f"Check the API key (Credentials → API Keys in the TrueNAS UI) and "
            f"that the account has permission for this resource. {snippet}"
        )
    if status == 404:
        return (
            f"Resource not found (404) on {path}. The id may be stale — list the "
            f"parent collection first to get a current id. {snippet}"
        )
    if status == 422:
        return (
            f"Validation error (422) on {path}. TrueNAS rejected the request body "
            f"— check required fields and value formats. {snippet}"
        )
    if status in (500, 502, 503, 504):
        return (
            f"TrueNAS server error ({status}) on {path}. The middleware may be "
            f"busy or restarting; retry shortly. {snippet}"
        )
    return f"TrueNAS API error ({status}) on {path}. {snippet}"


class TrueNASConnection:
    """A single authenticated session against one TrueNAS SCALE REST API target."""

    def __init__(self, target: TargetConfig, client: Any | None = None) -> None:
        self._target = target
        self._client = client or httpx.Client(
            base_url=target.base_url,
            verify=target.verify_ssl,
            timeout=_TIMEOUT,
            headers={
                "Authorization": f"Bearer {target.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    @property
    def target(self) -> TargetConfig:
        return self._target

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Issue a request and return parsed JSON, translating errors centrally."""
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise TrueNASApiError(
                f"Could not reach TrueNAS at {self._target.base_url} "
                f"({method} {path}): {exc}. Check the host/port and that the "
                f"TrueNAS REST API is reachable.",
                path=path,
            ) from exc
        if resp.status_code == 404 and _looks_like_rest_removed(path):
            raise UnsupportedServerVersion(
                _rest_removed_message(self._target.base_url, path),
                status_code=404,
                path=path,
            )
        if not (200 <= resp.status_code < 300):
            raise TrueNASApiError(
                _teaching_message(resp.status_code, path, resp.text),
                status_code=resp.status_code,
                path=path,
            )
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {}

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        self._client.close()


class ConnectionManager:
    """Manages connections to multiple TrueNAS targets with session reuse."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._connections: dict[str, TrueNASConnection] = {}
        _MANAGERS.add(self)

    @classmethod
    def from_config(cls, config: AppConfig | None = None) -> ConnectionManager:
        cfg = config or load_config()
        return cls(cfg)

    def connect(self, target_name: str | None = None) -> TrueNASConnection:
        """Connect to a target by name, or the default target."""
        target = (
            self._config.get_target(target_name)
            if target_name
            else self._config.default_target
        )
        cached = self._connections.get(target.name)
        if cached is not None:
            return cached
        conn = TrueNASConnection(target)
        self._connections[target.name] = conn
        return conn

    def disconnect(self, target_name: str) -> None:
        conn = self._connections.pop(target_name, None)
        if conn is not None:
            conn.close()

    def disconnect_all(self) -> None:
        for name in list(self._connections):
            self.disconnect(name)

    def list_targets(self) -> list[str]:
        return [t.name for t in self._config.targets]

    def list_connected(self) -> list[str]:
        return list(self._connections.keys())


# Managers hold cached httpx clients; close them all at interpreter exit so
# sockets are released deterministically (a WeakSet so short-lived CLI managers
# can still be garbage-collected normally).
_MANAGERS: weakref.WeakSet[ConnectionManager] = weakref.WeakSet()


def _close_all_managers() -> None:
    for mgr in list(_MANAGERS):
        try:
            mgr.disconnect_all()
        except Exception:  # noqa: BLE001 — exit-time cleanup must never raise
            pass


atexit.register(_close_all_managers)
