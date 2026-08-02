"""JSON-RPC 2.0 over WebSocket transport for TrueNAS (the REST replacement).

iXsystems is retiring the REST API v2.0: deprecated in 25.04, and **removed in
TrueNAS 26** in favour of JSON-RPC 2.0 over a persistent WebSocket at
``/api/current``. This module is that transport.

It deliberately presents the **same surface as**
:class:`~truenas_aiops.connection.TrueNASConnection` — ``get`` / ``post`` /
``delete`` taking REST-shaped paths — so the thirteen ops modules and their
forty-odd call sites do not change at all. `TrueNASConnection.request` was
already the single chokepoint every operation funnelled through; this swaps what
sits behind it, not what calls it.

The translation is **per-endpoint and deliberately explicit** (see
:data:`_ROUTES`). It is not a mechanical rewrite: ``GET /disk?extra.pools=true``
becomes ``disk.query`` with a ``{"extra": {"pools": True}}`` options object, and
fetching one record by id becomes a ``query`` with a filter and ``{"get": True}``
rather than a path segment. Every method name in the table was checked against a
live appliance's ``core.get_methods`` (TrueNAS SCALE 25.04.2.1, 2026-08-02, 771
methods) rather than taken from documentation — the line has been bitten before
by endpoints that existed only in prose.

**This transport is testable today.** 25.04 already serves ``/api/current``, so
every method here can be cross-checked against the REST result on the same
appliance; TrueNAS 26 is not required to develop or verify it.
"""

from __future__ import annotations

import itertools
import json
import logging
import ssl
import threading
from typing import Any
from urllib.parse import unquote

from truenas_aiops.config import TargetConfig
from truenas_aiops.connection import TrueNASApiError

_log = logging.getLogger("truenas-aiops.ws")

#: JSON-RPC endpoint TrueNAS 26 mandates; 25.04 already serves it.
WS_PATH = "/api/current"

_OPEN_TIMEOUT = 20.0
_CALL_TIMEOUT = 60.0

#: Frame-size ceiling. ``websockets`` defaults to 1 MiB and closes the
#: connection with ``1009 message too big`` when a reply exceeds it — which is
#: not hypothetical: ``core.get_methods`` alone blew past it on a stock
#: appliance, and a NAS with thousands of snapshots or datasets would do the
#: same on an ordinary listing. A truncated *connection* is far worse than a
#: large frame, so the ceiling is raised and made explicit rather than left at a
#: default that fails only on big installations.
MAX_FRAME_BYTES = 64 * 1024 * 1024


class TrueNASWsError(TrueNASApiError):  # noqa: N818 — teaching error, reads as a statement
    """A JSON-RPC call failed, or the WebSocket transport itself did.

    Subclasses :class:`TrueNASApiError` so every existing ``except
    TrueNASApiError`` handler and the CLI's error translator keep working
    unchanged when a target moves from REST to WebSocket.
    """


class UnmappedEndpoint(TrueNASWsError):  # noqa: N818 — teaching error, reads as a statement
    """A REST path this transport has no middleware method for.

    Raised loudly on purpose. The alternative — guessing a method name from the
    path — is how a tool ends up calling endpoints that do not exist, and a
    wrong guess would surface as a confusing middleware error rather than as
    "this transport does not implement that yet".
    """


def _route_pool_by_id(pool_id: str, _params: dict) -> tuple[str, list]:
    """One pool by id **or** name, mirroring the REST reader's tolerance."""
    ident = unquote(pool_id)
    field = "id" if ident.isdigit() else "name"
    value: Any = int(ident) if ident.isdigit() else ident
    return "pool.query", [[[field, "=", value]], {"get": True}]


def _route_dataset_by_id(dataset_id: str, _params: dict) -> tuple[str, list]:
    """One dataset by its ZFS name (``tank/data``)."""
    return "pool.dataset.query", [[["id", "=", unquote(dataset_id)]], {"get": True}]


def _route_snapshot_delete(snapshot_id: str, _params: dict) -> tuple[str, list]:
    """Delete one snapshot by its ``dataset@name`` id."""
    return "zfs.snapshot.delete", [unquote(snapshot_id)]


def _route_disks(_params: dict) -> tuple[str, list]:
    """Disk listing, carrying the pool membership the REST reader asks for.

    ``extra.pools`` is a REST query parameter; over JSON-RPC the same request is
    an options object. Without it TrueNAS reports ``pool: null`` for every disk
    — including ones in a pool — so this is not cosmetic (it was a live bug on
    the REST side too).
    """
    return "disk.query", [[], {"extra": {"pools": True}}]


#: ``(verb, path)`` → middleware method. Static routes map to a method name and
#: fixed params; ``{id}`` routes map to a builder that receives the raw (still
#: percent-encoded) segment and the REST query params.
_ROUTES: dict[tuple[str, str], tuple[str, list]] = {
    ("GET", "/system/info"): ("system.info", []),
    ("GET", "/pool"): ("pool.query", []),
    ("GET", "/pool/dataset"): ("pool.dataset.query", []),
    ("GET", "/zfs/snapshot"): ("zfs.snapshot.query", []),
    ("GET", "/service"): ("service.query", []),
    ("GET", "/replication"): ("replication.query", []),
    ("GET", "/cloudsync"): ("cloudsync.query", []),
    ("GET", "/smart/test/results"): ("smart.test.results", []),
    # /alert/list is a GET in REST v2.0 (POSTing it 405s — a real live bug once).
    ("GET", "/alert/list"): ("alert.list", []),
}

#: Routes whose path carries an id, matched by prefix. Ordered longest-first so
#: ``/pool/dataset/id/`` never loses to ``/pool/id/``.
_ID_ROUTES: list[tuple[str, str, Any]] = [
    ("GET", "/pool/dataset/id/", _route_dataset_by_id),
    ("GET", "/pool/id/", _route_pool_by_id),
    ("DELETE", "/zfs/snapshot/id/", _route_snapshot_delete),
]

#: Writes. Each takes the REST body the ops layer sends and returns the JSON-RPC
#: params.
#:
#: The body keys here are NOT a guess — they are the keys
#: :mod:`truenas_aiops.ops` actually posts, and a mismatch is invisible over
#: REST (which forwards the body verbatim) while breaking the operation over
#: WebSocket. That is not hypothetical: this table first read ``body["pool"]``
#: for a scrub while ops sends ``{"name": ...}``, so every scrub reached the
#: middleware as ``pool.scrub.run(None, 35)`` and was rejected. Positional
#: arities were read from the appliance's own ``core.get_methods`` schema
#: (``pool.scrub.run(name, threshold)``, ``service.restart(service,
#: service-control)``), not inferred from the REST shape.
_SCRUB_DEFAULT_THRESHOLD = 35


def _require(body: Any, key: str, method: str) -> Any:
    """Read a body key the ops layer is contracted to send, or say so loudly.

    Silently passing ``None`` to the middleware produces a validation error that
    names the middleware's parameter, not the mismatch that caused it — which is
    exactly how the scrub bug read when it happened.
    """
    value = (body or {}).get(key)
    if value is None:
        raise UnmappedEndpoint(
            f"The WebSocket route for '{method}' expected '{key}' in the request "
            f"body but it was absent. This is a translation-table bug, not a "
            f"caller error: fix the key in truenas_aiops/wsconnection.py to match "
            f"what truenas_aiops.ops actually posts."
        )
    return value


_WRITE_ROUTES: dict[tuple[str, str], Any] = {
    ("POST", "/pool/dataset"): lambda body: ("pool.dataset.create", [body or {}]),
    ("POST", "/zfs/snapshot"): lambda body: ("zfs.snapshot.create", [body or {}]),
    ("POST", "/pool/scrub/run"): lambda body: ("pool.scrub.run", [
        _require(body, "name", "pool.scrub.run"),
        (body or {}).get("threshold", _SCRUB_DEFAULT_THRESHOLD)]),
    ("POST", "/service/restart"): lambda body: ("service.restart", [
        _require(body, "service", "service.restart")]),
}


def _resolve(method: str, path: str, params: dict, body: Any) -> tuple[str, list]:
    """Translate one REST call into ``(middleware_method, params)``."""
    verb = method.upper()
    clean = path.split("?", 1)[0].rstrip("/") or "/"

    if verb == "GET" and clean == "/disk":
        return _route_disks(params)

    static = _ROUTES.get((verb, clean))
    if static is not None:
        return static[0], list(static[1])

    for route_verb, prefix, builder in _ID_ROUTES:
        if verb == route_verb and clean.startswith(prefix):
            return builder(clean[len(prefix):], params)

    writer = _WRITE_ROUTES.get((verb, clean))
    if writer is not None:
        return writer(body)

    raise UnmappedEndpoint(
        f"The WebSocket transport has no middleware method for {verb} {clean}. "
        f"TrueNAS 26 removed the REST API, so this operation cannot fall back to "
        f"it. Map the endpoint in truenas_aiops/wsconnection.py (_ROUTES) — do "
        f"not guess a method name; list them with 'core.get_methods' on the "
        f"appliance first.",
        path=path,
    )


class TrueNASWsConnection:
    """A JSON-RPC-over-WebSocket session presenting the REST call surface.

    Connects lazily and keeps the socket open across calls (the middleware
    authenticates the *connection*, not each request). Calls are serialised by a
    lock: one socket cannot interleave two request/response exchanges, and
    silently sharing one would let a caller read another's reply.
    """

    def __init__(self, target: TargetConfig, client: Any | None = None) -> None:
        self._target = target
        self._client = client
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        # NOT `client is not None`: an injected socket still has to log in.
        # Treating injection as pre-authenticated would mean a real caller
        # that supplies its own connection silently never authenticates.
        self._authenticated = False

    # ── connection ───────────────────────────────────────────────────────

    @property
    def target(self) -> TargetConfig:
        return self._target

    def _url(self) -> str:
        scheme = "wss" if getattr(self._target, "scheme", "https") == "https" else "ws"
        return f"{scheme}://{self._target.host}:{self._target.port}{WS_PATH}"

    def _ssl_context(self) -> Any:
        if getattr(self._target, "scheme", "https") != "https":
            return None
        ctx = ssl.create_default_context()
        if not self._target.verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _connect(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from websockets.sync.client import connect
        except ImportError as exc:  # pragma: no cover — declared dependency
            raise TrueNASWsError(
                "The 'websockets' package is required for the TrueNAS WebSocket "
                "transport but is not installed. Reinstall truenas-aiops so its "
                "declared dependencies are present.",
            ) from exc
        try:
            self._client = connect(
                self._url(), ssl=self._ssl_context(),
                open_timeout=_OPEN_TIMEOUT, max_size=MAX_FRAME_BYTES,
            )
        except Exception as exc:  # noqa: BLE001 — translated into a teaching error
            raise TrueNASWsError(
                f"Could not open the TrueNAS WebSocket at {self._url()}: {exc}. "
                f"Check the host/port and that the appliance serves {WS_PATH} "
                f"(TrueNAS 25.04 and later do).",
            ) from exc
        self._authenticated = False
        return self._client

    def _authenticate(self) -> None:
        """Log the connection in, preferring the mechanism TrueNAS 26 keeps.

        26 deprecates ``auth.login_with_api_key`` in favour of ``auth.login_ex``,
        while 25.04 serves the older one — so try the newer first and fall back.
        Note that **upgrading an appliance to 26 revokes existing API keys**; a
        transport error here is far more likely to be a revoked key than a
        protocol problem.
        """
        if self._authenticated:
            return
        key = self._target.api_key
        attempts = [
            ("auth.login_ex", [{"mechanism": "API_KEY_PLAIN",
                                "username": getattr(self._target, "username", "") or "",
                                "api_key": key}]),
            ("auth.login_with_api_key", [key]),
        ]
        last = ""
        for method, params in attempts:
            try:
                result = self._rpc(method, params)
            except TrueNASWsError as exc:
                last = str(exc)
                continue
            if result is True or (isinstance(result, dict)
                                  and result.get("response_type") == "SUCCESS"):
                self._authenticated = True
                return
            last = f"{method} returned {result!r}"
        raise TrueNASWsError(
            f"TrueNAS rejected the API key over the WebSocket transport. {last}. "
            f"Create a new key (Credentials → API Keys); note that upgrading an "
            f"appliance to TrueNAS 26 REVOKES existing keys.",
        )

    # ── JSON-RPC ─────────────────────────────────────────────────────────

    def _rpc(self, method: str, params: list) -> Any:
        """Issue one JSON-RPC call and return its result, or raise."""
        ws = self._connect()
        call_id = next(self._ids)
        payload = json.dumps({"jsonrpc": "2.0", "id": call_id,
                              "method": method, "params": params})
        try:
            ws.send(payload)
            while True:
                raw = ws.recv(timeout=_CALL_TIMEOUT)
                message = json.loads(raw)
                # The middleware also pushes unsolicited events down the same
                # socket; anything that is not this call's reply is not ours.
                if message.get("id") == call_id:
                    break
        except Exception as exc:  # noqa: BLE001 — translated into a teaching error
            self.close()
            raise TrueNASWsError(
                f"TrueNAS WebSocket call '{method}' failed: {exc}. The connection "
                f"was dropped and will be reopened on the next call.",
            ) from exc

        if "error" in message:
            error = message["error"] or {}
            detail = error.get("message") or json.dumps(error)[:300]
            data = error.get("data")
            if isinstance(data, dict) and data.get("reason"):
                detail = f"{detail}: {data['reason']}"
            raise TrueNASWsError(
                f"TrueNAS rejected '{method}': {detail}",
                status_code=error.get("code"),
                path=method,
            )
        return message.get("result")

    # ── the REST-shaped surface the ops layer already speaks ─────────────

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Translate a REST call to JSON-RPC and return the parsed result."""
        params = kwargs.get("params") or {}
        body = kwargs.get("json")
        rpc_method, rpc_params = _resolve(method, path, params, body)
        with self._lock:
            self._authenticate()
            result = self._rpc(rpc_method, rpc_params)
        # REST answers a bodyless success with {}; keep that contract so callers
        # that check for a dict do not have to special-case this transport.
        return {} if result is None else result

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        client, self._client = self._client, None
        self._authenticated = False
        if client is None:
            return
        try:
            client.close()
        except Exception:  # noqa: BLE001 — teardown must never raise
            _log.debug("closing the TrueNAS WebSocket raised", exc_info=True)
