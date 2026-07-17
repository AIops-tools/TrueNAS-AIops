"""Connection-layer coverage: central non-2xx→TrueNASApiError translation with
teaching messages, transport-error wrapping, body parsing, and the
per-target ConnectionManager session reuse.
"""

from __future__ import annotations

import httpx
import pytest

from truenas_aiops.config import AppConfig, TargetConfig
from truenas_aiops.connection import (
    ConnectionManager,
    TrueNASApiError,
    TrueNASConnection,
    _close_all_managers,
    _seg,
)


class _Resp:
    def __init__(self, status: int, *, payload=None, content: bytes = b"{}", text: str = "body"):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.content = content
        self.text = text

    def json(self):
        return self._payload


class _Client:
    """Injectable stand-in for httpx.Client: scripts one response, or raises."""

    def __init__(self, resp=None, raise_exc: Exception | None = None):
        self._resp = resp
        self._raise = raise_exc
        self.closed = False
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, path: str, **kw):
        self.calls.append((method, path))
        if self._raise is not None:
            raise self._raise
        return self._resp

    def close(self):
        self.closed = True


def _conn(resp=None, raise_exc=None) -> TrueNASConnection:
    target = TargetConfig(name="nas1", host="nas.local", verify_ssl=False)
    return TrueNASConnection(target, client=_Client(resp=resp, raise_exc=raise_exc))


@pytest.mark.unit
def test_seg_encodes_path_separators_and_at():
    assert _seg("tank/data@snap1") == "tank%2Fdata%40snap1"
    assert _seg("../etc") == "..%2Fetc"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "needle"),
    [
        (401, "authentication/authorization failed"),
        (403, "authentication/authorization failed"),
        (404, "resource not found"),
        (422, "validation error"),
        (500, "truenas server error"),
        (503, "truenas server error"),
        (418, "truenas api error"),  # generic fallback branch
    ],
)
def test_teaching_message_per_status(status, needle):
    conn = _conn(resp=_Resp(status, content=b"x", text="detail-snippet"))
    with pytest.raises(TrueNASApiError) as ei:
        conn.get("/anything")
    assert needle in str(ei.value).lower()
    assert ei.value.status_code == status
    assert ei.value.path == "/anything"


@pytest.mark.unit
def test_transport_error_is_wrapped_with_reachability_hint():
    conn = _conn(raise_exc=httpx.ConnectError("no route"))
    with pytest.raises(TrueNASApiError) as ei:
        conn.get("/system/info")
    msg = str(ei.value).lower()
    assert "could not reach truenas" in msg
    assert ei.value.status_code is None  # transport error carries no HTTP status


@pytest.mark.unit
def test_empty_content_returns_empty_dict():
    conn = _conn(resp=_Resp(200, content=b""))
    assert conn.get("/x") == {}


@pytest.mark.unit
def test_invalid_json_body_returns_empty_dict():
    class _BadJson(_Resp):
        def json(self):
            raise ValueError("not json")

    conn = _conn(resp=_BadJson(200, content=b"<html>"))
    assert conn.get("/x") == {}


@pytest.mark.unit
def test_post_and_delete_verbs_and_close():
    client = _Client(resp=_Resp(200, payload={"ok": True}, content=b"{}"))
    conn = TrueNASConnection(
        TargetConfig(name="nas1", host="h", verify_ssl=False), client=client
    )
    assert conn.post("/p", json={"a": 1}) == {"ok": True}
    assert conn.delete("/d") == {"ok": True}
    assert [m for m, _ in client.calls] == ["POST", "DELETE"]
    conn.close()
    assert client.closed is True
    assert conn.target.name == "nas1"


# --------------------------------------------------------------------------- #
# ConnectionManager
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_manager_connect_caches_and_reuses_session(monkeypatch):
    monkeypatch.setenv("TRUENAS_NAS1_APIKEY", "k")
    cfg = AppConfig(targets=(TargetConfig(name="nas1", host="h"),))
    mgr = ConnectionManager(cfg)
    c1 = mgr.connect()  # default target
    c2 = mgr.connect("nas1")  # by name -> same cached object
    assert c1 is c2
    assert mgr.list_connected() == ["nas1"]
    assert mgr.list_targets() == ["nas1"]


@pytest.mark.unit
def test_manager_disconnect_all_closes_and_clears(monkeypatch):
    monkeypatch.setenv("TRUENAS_NAS1_APIKEY", "k")
    cfg = AppConfig(targets=(TargetConfig(name="nas1", host="h"),))
    mgr = ConnectionManager(cfg)

    closed = {"n": 0}

    class _C:
        def close(self):
            closed["n"] += 1

    mgr._connections["nas1"] = _C()
    mgr.disconnect_all()
    assert closed["n"] == 1
    assert mgr.list_connected() == []


@pytest.mark.unit
def test_from_config_builds_manager():
    mgr = ConnectionManager.from_config(AppConfig(targets=()))
    assert mgr.list_targets() == []


@pytest.mark.unit
def test_close_all_managers_swallows_disconnect_errors():
    """Exit-time cleanup must never raise even if a manager blows up."""
    cfg = AppConfig(targets=())
    mgr = ConnectionManager(cfg)

    def _boom():
        raise RuntimeError("cleanup boom")

    mgr.disconnect_all = _boom  # type: ignore[method-assign]
    _close_all_managers()  # must not raise
