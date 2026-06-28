"""System service operations for TrueNAS SCALE.

Read over ``/service``; the one mutating op (``restart_service``) maps to
``POST /service/restart``. A restart has no clean inverse (the service was
already running or not); it captures the prior state for the audit record but
declares no undo.

PREVIEW: mock-validated only — verify endpoint paths against a live system.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.ops._util import as_list, s


def _service_summary(svc: dict) -> dict:
    """Reduce a service record to a high-signal summary."""
    return {
        "id": svc.get("id"),
        "service": s(svc.get("service"), 64),
        "state": s(svc.get("state"), 32),
        "enable": svc.get("enable"),
    }


def list_services(conn: Any) -> list[dict]:
    """[READ] List system services with name, state (RUNNING/STOPPED), enable."""
    return [_service_summary(x) for x in as_list(conn.get("/service"))]


def _find_service(conn: Any, service: str) -> dict:
    """Best-effort lookup of one service's current state, or {} (advisory)."""
    try:
        for x in as_list(conn.get("/service")):
            if x.get("service") == service:
                return _service_summary(x)
    except Exception:  # noqa: BLE001 — advisory context only
        return {}
    return {}


def restart_service(conn: Any, service: str) -> dict:
    """[WRITE] Restart a system service by name (medium). Captures prior state.

    ``service`` is the TrueNAS service name (e.g. ``smb``, ``nfs``, ``ssh``).
    Maps to ``POST /service/restart``. No undo descriptor — a restart is not
    cleanly reversible.
    """
    prior = _find_service(conn, service)
    conn.post("/service/restart", json={"service": service})
    return {"service": s(service, 64), "action": "restart", "priorState": prior}
