"""Does this TrueNAS server still speak the REST API this tool is built on?

``truenas-aiops`` talks to TrueNAS over the **REST API v2.0** (``/api/v2.0``).
iXsystems is retiring that transport, on a published timeline:

  * **25.04** — REST deprecated.
  * **25.10.1** — every REST call raises a deprecation alert on the appliance.
  * **26** — REST is **removed**. The replacement is JSON-RPC 2.0 over a
    persistent WebSocket at ``/api/current``; this tool does not speak it yet.

So the server's version, not the network, decides whether this tool can work at
all. Everything here is pure: parse a version string, classify it, and hand back
a message the caller can print. No I/O, no raising — a doctor must survive the
thing it diagnoses, and an unreadable version is a *finding*, not a crash.

The exception raised when a server genuinely cannot serve REST lives with the
rest of the API error hierarchy: :class:`truenas_aiops.connection.UnsupportedServerVersion`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ─── The timeline, in one place ────────────────────────────────────────────

REST_DEPRECATED_IN = "25.04"
REST_ALERTS_SINCE: tuple[int, int, int] = (25, 10, 1)
REST_REMOVED_MAJOR = 26
WEBSOCKET_API_PATH = "/api/current"

# ─── Verdicts ──────────────────────────────────────────────────────────────

SUPPORTED = "supported"
DEPRECATED = "deprecated"
REMOVED = "removed"
UNKNOWN = "unknown"

# TrueNAS reports versions in several shapes across products and releases:
#   "25.10.4"  "26.0-BETA.2"  "TrueNAS-SCALE-24.04.2"  "TrueNAS-13.0-U6.1"
# Take the first dotted-numeric run; the product/codename prefix carries no
# ordering information.
_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def parse_version(raw: str | None) -> tuple[int, int, int] | None:
    """Extract ``(major, minor, patch)`` from a TrueNAS version string.

    Returns ``None`` when there is nothing parseable — missing, empty, or a
    shape we have never seen. ``None`` means *unknown*, which is deliberately
    not the same as *old* or *fine*.
    """
    if not isinstance(raw, str):
        return None
    match = _VERSION_RE.search(raw)
    if match is None:
        return None
    major, minor, patch = match.group(1), match.group(2), match.group(3)
    return (int(major), int(minor), int(patch or 0))


@dataclass(frozen=True)
class RestSupport:
    """Verdict on one server's ability to serve the REST API v2.0."""

    status: str
    version: str | None
    parsed: tuple[int, int, int] | None
    message: str

    @property
    def is_fatal(self) -> bool:
        """True when this tool cannot manage the server at all."""
        return self.status == REMOVED

    @property
    def is_ok(self) -> bool:
        """True only when REST is known-good. UNKNOWN is never OK."""
        return self.status == SUPPORTED


def _removed_message(version: str) -> str:
    return (
        f"TrueNAS {version} has REMOVED the REST API v2.0 (removed in TrueNAS "
        f"{REST_REMOVED_MAJOR}). truenas-aiops speaks REST only, so it cannot manage this "
        f"server — no setting in config.yaml will change that. iXsystems replaced REST with "
        f"JSON-RPC 2.0 over a persistent WebSocket at {WEBSOCKET_API_PATH}, which this tool "
        f"does not implement yet. Until it does: manage this server from the TrueNAS UI or "
        f"the middleware CLI, or point truenas-aiops at an appliance still on 25.10.x."
    )


def _deprecated_message(version: str) -> str:
    return (
        f"TrueNAS {version} still serves the REST API v2.0, but it is deprecated: every call "
        f"this tool makes raises a deprecation alert on the appliance (expect them under "
        f"Alerts), and REST is REMOVED in TrueNAS {REST_REMOVED_MAJOR}. truenas-aiops will "
        f"stop working the moment this server is upgraded to {REST_REMOVED_MAJOR}. Treat that "
        f"upgrade as a breaking change for this tool, not a routine one."
    )


def _supported_message(version: str) -> str:
    return (
        f"REST API v2.0 available on TrueNAS {version}. Note it was deprecated in "
        f"{REST_DEPRECATED_IN} and is removed in TrueNAS {REST_REMOVED_MAJOR} — this tool "
        f"needs a WebSocket transport before you upgrade that far."
    )


def _unknown_message(raw: str | None) -> str:
    seen = "no version field" if raw is None else f"got {raw!r}"
    return (
        f"Could not read a TrueNAS version from /system/info ({seen}), so REST support is "
        f"UNKNOWN — which is not the same as fine. REST was deprecated in "
        f"{REST_DEPRECATED_IN} and is removed in TrueNAS {REST_REMOVED_MAJOR}; check the "
        f"version in the TrueNAS UI (System → Update) before trusting this tool here."
    )


def check_rest_support(raw: str | None) -> RestSupport:
    """Classify a server version string against the REST retirement timeline.

    Never raises and never guesses: an unparseable or absent version yields
    ``UNKNOWN`` with a message that says so, rather than an optimistic OK.
    """
    version = raw.strip() if isinstance(raw, str) else None
    parsed = parse_version(version)
    if parsed is None:
        return RestSupport(UNKNOWN, version or None, None, _unknown_message(version or None))

    shown = version or ".".join(str(p) for p in parsed)
    if parsed[0] >= REST_REMOVED_MAJOR:
        return RestSupport(REMOVED, shown, parsed, _removed_message(shown))
    if parsed >= REST_ALERTS_SINCE:
        return RestSupport(DEPRECATED, shown, parsed, _deprecated_message(shown))
    return RestSupport(SUPPORTED, shown, parsed, _supported_message(shown))
