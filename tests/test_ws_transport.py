"""The JSON-RPC/WebSocket transport — TrueNAS 26's replacement for REST.

Every middleware method asserted here was confirmed against a live appliance's
``core.get_methods`` (TrueNAS SCALE 25.04.2.1, 771 methods, 2026-08-02) and each
route was cross-checked against the REST result on that same appliance. The
mapping table IS the contract: a wrong method name is not a typo, it is an
endpoint that does not exist, and this line has shipped invented endpoints
before (inference's whole Ray Serve control plane, TrueNAS's own alert POST).

The transport is deliberately dumb about everything except translation: it
presents ``get``/``post``/``delete`` over REST-shaped paths so the thirteen ops
modules never learn which API they are speaking.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from truenas_aiops.config import TargetConfig
from truenas_aiops.connection import TrueNASApiError, _open
from truenas_aiops.wsconnection import (
    MAX_FRAME_BYTES,
    TrueNASWsConnection,
    TrueNASWsError,
    UnmappedEndpoint,
    _resolve,
)


def _target(**kw) -> TargetConfig:
    base = {"name": "tn", "host": "nas.example", "port": 443, "verify_ssl": False}
    return TargetConfig(**{**base, **kw})


# ─── the mapping table ──────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("verb", "path", "method"),
    [
        ("GET", "/system/info", "system.info"),
        ("GET", "/pool", "pool.query"),
        ("GET", "/pool/dataset", "pool.dataset.query"),
        ("GET", "/zfs/snapshot", "zfs.snapshot.query"),
        ("GET", "/disk", "disk.query"),
        ("GET", "/service", "service.query"),
        ("GET", "/alert/list", "alert.list"),
        ("GET", "/replication", "replication.query"),
        ("GET", "/cloudsync", "cloudsync.query"),
        ("GET", "/smart/test/results", "smart.test.results"),
        ("POST", "/pool/dataset", "pool.dataset.create"),
        ("POST", "/zfs/snapshot", "zfs.snapshot.create"),
    ],
)
def test_every_rest_path_maps_to_a_real_middleware_method(verb, path, method):
    assert _resolve(verb, path, {}, {})[0] == method


@pytest.mark.unit
def test_write_routes_read_the_body_keys_ops_actually_sends():
    """The body keys are the contract between ops and this table, and a
    mismatch is INVISIBLE over REST (which forwards the body verbatim) while
    breaking the operation over WebSocket. That happened: the scrub route read
    ``body["pool"]`` while ops sends ``{"name": ...}``, so every scrub reached
    the middleware as ``pool.scrub.run(None, 35)`` and was rejected.
    """
    method, params = _resolve("POST", "/pool/scrub/run",
                              {}, {"name": "tank", "threshold": 0})
    assert (method, params) == ("pool.scrub.run", ["tank", 0])

    method, params = _resolve("POST", "/service/restart", {}, {"service": "smartd"})
    assert (method, params) == ("service.restart", ["smartd"])


@pytest.mark.unit
def test_a_missing_body_key_names_the_translation_table_not_the_caller():
    """Passing None through to the middleware yields a validation error naming
    the middleware's parameter, which is exactly how the scrub bug read — it
    pointed away from the real cause."""
    with pytest.raises(UnmappedEndpoint, match="translation-table bug"):
        _resolve("POST", "/pool/scrub/run", {}, {})


@pytest.mark.unit
def test_disk_listing_asks_for_pool_membership():
    """Without extra.pools TrueNAS reports pool=null for EVERY disk, including
    ones in a pool — an in-use disk becomes indistinguishable from a spare.
    That was a real REST-side bug; the WebSocket route must not reintroduce it.
    """
    method, params = _resolve("GET", "/disk", {"extra.pools": "true"}, None)
    assert method == "disk.query"
    assert params[1] == {"extra": {"pools": True}}


@pytest.mark.unit
def test_a_single_pool_is_fetched_by_id_or_by_name():
    """Callers hold a name far more often than the numeric id (a finding reports
    `resource: tank`), so both must work — over REST this cost a live 404."""
    method, params = _resolve("GET", "/pool/id/1", {}, None)
    assert method == "pool.query"
    assert params == [[["id", "=", 1]], {"get": True}]

    _method, params = _resolve("GET", "/pool/id/tank", {}, None)
    assert params == [[["name", "=", "tank"]], {"get": True}]


@pytest.mark.unit
def test_ids_are_url_decoded_out_of_the_rest_path():
    """The REST layer percent-encodes ids into the path; JSON-RPC takes them as
    values. Forgetting to decode would send the literal '%40' to the middleware.
    """
    method, params = _resolve("DELETE", "/zfs/snapshot/id/tank%2Fdata%40snap1", {}, None)
    assert method == "zfs.snapshot.delete"
    assert params == ["tank/data@snap1"]

    _m, params = _resolve("GET", "/pool/dataset/id/tank%2Fdata", {}, None)
    assert params[0] == [["id", "=", "tank/data"]]


@pytest.mark.unit
def test_an_unmapped_endpoint_raises_instead_of_guessing_a_method_name():
    """Guessing `foo.bar` from `/foo/bar` is how a tool ends up calling
    endpoints that do not exist. TrueNAS 26 has no REST to fall back to, so the
    honest answer is a loud, specific refusal."""
    with pytest.raises(UnmappedEndpoint, match="no middleware method"):
        _resolve("GET", "/totally/unmapped", {}, None)


@pytest.mark.unit
def test_transport_errors_stay_catchable_as_the_existing_api_error():
    """Every `except TrueNASApiError` in the codebase must keep working when a
    target moves from REST to WebSocket."""
    assert issubclass(TrueNASWsError, TrueNASApiError)
    assert issubclass(UnmappedEndpoint, TrueNASApiError)


# ─── the JSON-RPC exchange ──────────────────────────────────────────────────


class _FakeWs:
    """A canned JSON-RPC peer: replies by method name, records what was sent."""

    def __init__(self, replies: dict, extra_noise: bool = False):
        self.replies = replies
        self.sent: list[dict] = []
        self._pending: list[str] = []
        self.closed = False
        self._noise = extra_noise

    def send(self, payload: str) -> None:
        msg = json.loads(payload)
        self.sent.append(msg)
        if self._noise:
            # The middleware pushes unsolicited events down the same socket.
            self._pending.append(json.dumps({"jsonrpc": "2.0", "method": "collection_update"}))
        reply = self.replies.get(msg["method"], {"result": None})
        self._pending.append(json.dumps({"jsonrpc": "2.0", "id": msg["id"], **reply}))

    def recv(self, timeout=None) -> str:
        return self._pending.pop(0)

    def close(self) -> None:
        self.closed = True


@pytest.mark.unit
def test_a_call_ignores_unsolicited_events_and_returns_its_own_reply(monkeypatch):
    monkeypatch.setenv("TRUENAS_TN_APIKEY", "k-123")
    ws = _FakeWs({"auth.login_with_api_key": {"result": True},
                  "pool.query": {"result": [{"name": "tank"}]}},
                 extra_noise=True)
    conn = TrueNASWsConnection(_target(), client=ws)
    assert conn.get("/pool") == [{"name": "tank"}]


@pytest.mark.unit
def test_a_jsonrpc_error_becomes_a_teaching_error_not_a_silent_empty(monkeypatch):
    monkeypatch.setenv("TRUENAS_TN_APIKEY", "k-123")
    ws = _FakeWs({
        "auth.login_with_api_key": {"result": True},
        "pool.query": {"error": {"code": 22, "message": "no such pool",
                                 "data": {"reason": "tank is not imported"}}},
    })
    conn = TrueNASWsConnection(_target(), client=ws)
    with pytest.raises(TrueNASWsError, match="tank is not imported"):
        conn.get("/pool")


@pytest.mark.unit
def test_a_null_result_becomes_an_empty_dict_matching_rest(monkeypatch):
    monkeypatch.setenv("TRUENAS_TN_APIKEY", "k-123")
    """REST answers a bodyless success with {}. Callers must not have to
    special-case the transport."""
    ws = _FakeWs({"auth.login_with_api_key": {"result": True},
                  "service.restart": {"result": None}})
    conn = TrueNASWsConnection(_target(), client=ws)
    assert conn.post("/service/restart", json={"service": "smb"}) == {}


@pytest.mark.unit
def test_auth_prefers_login_ex_and_falls_back_to_the_api_key_mechanism(monkeypatch):
    """TrueNAS 26 deprecates auth.login_with_api_key in favour of auth.login_ex;
    25.04 serves the older one. Try the survivor first, fall back."""
    monkeypatch.setenv("TRUENAS_TN_APIKEY", "k-123")
    ws = _FakeWs({
        "auth.login_ex": {"error": {"code": -32601, "message": "Method not found"}},
        "auth.login_with_api_key": {"result": True},
        "system.info": {"result": {"version": "25.04.2.1"}},
    })
    conn = TrueNASWsConnection(_target(), client=ws)
    assert conn.get("/system/info")["version"] == "25.04.2.1"
    assert [m["method"] for m in ws.sent][:2] == ["auth.login_ex", "auth.login_with_api_key"]


@pytest.mark.unit
def test_a_rejected_key_says_that_upgrading_to_26_revokes_keys(monkeypatch):
    monkeypatch.setenv("TRUENAS_TN_APIKEY", "k-123")
    ws = _FakeWs({
        "auth.login_ex": {"result": False},
        "auth.login_with_api_key": {"result": False},
    })
    conn = TrueNASWsConnection(_target(), client=ws)
    with pytest.raises(TrueNASWsError, match="REVOKES existing keys"):
        conn.get("/system/info")


@pytest.mark.unit
def test_the_frame_ceiling_is_raised_well_above_the_library_default():
    """websockets defaults to 1 MiB and closes the CONNECTION with 1009 when a
    reply exceeds it. core.get_methods alone blew past that on a stock
    appliance, and a NAS with thousands of snapshots would do it on an ordinary
    listing — a dropped connection is far worse than a large frame.
    """
    assert MAX_FRAME_BYTES >= 16 * 1024 * 1024


# ─── transport selection ────────────────────────────────────────────────────


@pytest.mark.unit
def test_transport_pinning_selects_the_requested_client(monkeypatch):
    from truenas_aiops import connection as conn_mod

    monkeypatch.setenv("TRUENAS_TN_APIKEY", "k-123")

    monkeypatch.setattr(conn_mod, "websocket_available", lambda *_a, **_k: True)
    assert type(_open(_target(transport="rest"))).__name__ == "TrueNASConnection"
    assert type(_open(_target(transport="websocket"))).__name__ == "TrueNASWsConnection"


@pytest.mark.unit
def test_auto_prefers_the_transport_that_survives_truenas_26(monkeypatch):
    from truenas_aiops import connection as conn_mod

    monkeypatch.setenv("TRUENAS_TN_APIKEY", "k-123")

    monkeypatch.setattr(conn_mod, "websocket_available", lambda *_a, **_k: True)
    assert type(_open(_target())).__name__ == "TrueNASWsConnection"

    monkeypatch.setattr(conn_mod, "websocket_available", lambda *_a, **_k: False)
    assert type(_open(_target())).__name__ == "TrueNASConnection"


@pytest.mark.unit
def test_a_failed_websocket_probe_means_use_rest_not_crash(monkeypatch):
    """The probe runs against appliances that may be old, firewalled, or down.
    Any failure must degrade to REST — which is still correct on 25.10 and
    older — rather than take the connection attempt with it."""
    from truenas_aiops import connection as conn_mod

    def _boom(*_a, **_k):
        raise OSError("connection refused")

    monkeypatch.setattr(conn_mod.socket, "create_connection", _boom, raising=False)
    assert conn_mod.websocket_available(_target()) is False


@pytest.mark.unit
def test_an_invalid_transport_is_rejected_at_config_load():
    with pytest.raises(ValueError, match="transport must be"):
        _target(transport="grpc")


@pytest.mark.unit
def test_closing_is_idempotent_and_never_raises():
    ws = MagicMock(name="ws")
    ws.close.side_effect = RuntimeError("already gone")
    conn = TrueNASWsConnection(_target(), client=ws)
    conn.close()
    conn.close()  # second close has nothing to do
    assert ws.close.call_count == 1
