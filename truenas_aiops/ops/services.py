"""System service operations for TrueNAS SCALE.

Read over ``/service``; the one mutating op (``restart_service``) maps to
``POST /service/restart``. A restart has no clean inverse (the service was
already running or not); it captures the prior state for the audit record but
declares no undo.

``restart_service`` is guarded twice, because a restart of the wrong service
can take away the operator's own way back in:

  * the service name must be one this system actually exposes
    (:class:`UnknownService`) — an unrecognised name used to be forwarded to
    the middleware verbatim;
  * ``ssh`` additionally requires ``confirm=True``
    (:class:`RecoveryPathRestart`), because it is the out-of-band path an
    operator falls back to when the web UI or this tool stops answering.
    Bouncing it while working through it can strand them, and a restart has no
    undo to reach for.

Both guards are exact — only the named service is affected — and the first
**fails open**: if ``/service`` cannot be read at all, the call proceeds. A
lookup that failed says nothing about whether the service exists, and treating
"unknown" as "absent" would refuse every restart on a host that is already
having a bad day.

PREVIEW: mock-validated only — verify endpoint paths against a live system.
"""

from __future__ import annotations

from typing import Any

from truenas_aiops.governance import opt_str
from truenas_aiops.ops._util import as_list, s

#: Outcomes of a ``/service`` lookup. ``UNKNOWN`` is deliberately not ``ABSENT``:
#: the guard must fail open on it.
FOUND, ABSENT, UNKNOWN = "found", "absent", "unknown"

#: Services whose restart can cut the operator off from the box. ``ssh`` is the
#: out-of-band recovery path; restarting it needs an explicit ``confirm=True``.
RECOVERY_SERVICES = frozenset({"ssh"})


class UnknownService(ValueError):  # noqa: N818 — teaching error, reads as a statement
    """Refused: the named service is not one this TrueNAS system exposes."""


class RecoveryPathRestart(ValueError):  # noqa: N818 — teaching error, reads as a statement
    """Refused: restarting the out-of-band recovery path needs ``confirm=True``."""


def _service_summary(svc: dict) -> dict:
    """Reduce a service record to a high-signal summary."""
    return {
        "id": svc.get("id"),
        "service": opt_str(svc.get("service"), 64),
        "state": opt_str(svc.get("state"), 32),
        "enable": svc.get("enable"),
    }


def list_services(conn: Any) -> list[dict]:
    """[READ] List system services with name, state (RUNNING/STOPPED), enable."""
    return [_service_summary(x) for x in as_list(conn.get("/service"))]


def _lookup_service(conn: Any, service: str) -> tuple[str, dict]:
    """Look one service up in ``/service``, distinguishing absent from unreadable.

    Returns ``(FOUND, summary)``, ``(ABSENT, {})`` when the list was read and the
    name was not in it, or ``(UNKNOWN, {})`` when the list could not be read at
    all. That third case is the whole point of the split: this used to collapse
    both misses into a bare ``{}``, so any guard built on it would have refused
    every restart the moment ``/service`` stopped answering — failing closed, in
    exactly the situation where an operator most needs the restart to work.
    """
    try:
        rows = as_list(conn.get("/service"))
    except Exception:  # noqa: BLE001 — advisory context; unknown is never "absent"
        return UNKNOWN, {}
    for x in rows:
        if x.get("service") == service:
            return FOUND, _service_summary(x)
    return ABSENT, {}


def guard_restart_service(conn: Any, service: str, confirm: bool = False) -> dict:
    """Raise what ``restart_service`` would raise, without restarting anything.

    Called by ``restart_service`` itself *and* by the MCP wrapper ahead of its
    ``dry_run`` early return, so a preview of a refused restart reports the
    refusal instead of a green ``wouldRestart``. Both paths run this one
    function, so the preview and the real call can never disagree; the preview
    pays one ``GET /service`` for that guarantee, which a dry run is allowed to
    do (a preview may read; it must never write).

    Returns the service's prior-state summary so the caller does not have to
    fetch it again.

    Deliberately **not** guarded on "is this the service I am connected over":
    the TrueNAS middleware listener is not a ``/service`` member, so such a test
    would essentially never fire and would only manufacture confidence.
    """
    outcome, prior = _lookup_service(conn, service)
    if outcome == ABSENT:
        raise UnknownService(
            f"Refusing to restart '{service}': this TrueNAS system exposes no service by "
            f"that name, so the restart would either do nothing or act on something you "
            f"did not mean. Run service_list (CLI: 'truenas-aiops service list') and pass "
            f"one of the names it returns."
        )
    if service in RECOVERY_SERVICES and not confirm:
        raise RecoveryPathRestart(
            f"Refusing to restart '{service}' without confirm=True: SSH is the out-of-band "
            f"path you fall back to when the web UI or this tool stops answering, and a "
            f"restart has no undo. If you are working over SSH right now, restarting it can "
            f"drop you with no way back in. Make sure you hold a second console (IPMI, "
            f"physical, or the TrueNAS web shell), then re-run with confirm=True."
        )
    return prior


def restart_service(conn: Any, service: str, confirm: bool = False) -> dict:
    """[WRITE] Restart a system service by name (medium). Captures prior state.

    ``service`` is the TrueNAS service name (e.g. ``smb``, ``nfs``, ``ssh``).
    Maps to ``POST /service/restart``. No undo descriptor — a restart is not
    cleanly reversible.

    Refuses a name that is not present in ``/service``, and refuses ``ssh``
    unless ``confirm=True`` (see :func:`guard_restart_service`). If ``/service``
    cannot be read at all the restart proceeds — an unreadable list is not
    evidence the service is missing.
    """
    prior = guard_restart_service(conn, service, confirm=confirm)
    conn.post("/service/restart", json={"service": service})
    return {"service": s(service, 64), "action": "restart", "priorState": prior}
