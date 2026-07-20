"""REST-retirement version gating: parsing real TrueNAS version strings and
classifying them against the deprecation/removal timeline (deprecated 25.04,
alerts from 25.10.1, REMOVED in TrueNAS 26).

These are pure functions — no HTTP, no config — so they are cheap to pin
exactly, including the "we could not tell" path, which must degrade to UNKNOWN
rather than to an optimistic OK.
"""

from __future__ import annotations

import pytest

from truenas_aiops.version_support import (
    DEPRECATED,
    REMOVED,
    SUPPORTED,
    UNKNOWN,
    check_rest_support,
    parse_version,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("25.10.4", (25, 10, 4)),
        ("26.0-BETA.2", (26, 0, 0)),
        ("TrueNAS-SCALE-24.04.2", (24, 4, 2)),
        ("TrueNAS-SCALE-ElectricEel-24.10.2.1", (24, 10, 2)),
        ("TrueNAS-13.0-U6.1", (13, 0, 0)),
        ("25.04", (25, 4, 0)),
    ],
)
def test_parse_version_handles_real_truenas_shapes(raw, expected):
    assert parse_version(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "nightly", "TrueNAS-SCALE", 26, 25.10])
def test_parse_version_returns_none_for_unparseable(raw):
    assert parse_version(raw) is None


def test_version_25_10_4_is_deprecated_with_a_warning():
    support = check_rest_support("25.10.4")
    assert support.status == DEPRECATED
    assert support.is_fatal is False
    assert support.is_ok is False
    msg = support.message.lower()
    assert "deprecat" in msg
    assert "deprecation alert" in msg
    assert "removed in truenas 26" in msg
    assert "stop working" in msg


def test_version_25_10_1_is_the_deprecation_alert_boundary():
    assert check_rest_support("25.10.0").status == SUPPORTED
    assert check_rest_support("25.10.1").status == DEPRECATED


@pytest.mark.parametrize("raw", ["26.0-BETA.2", "26.0.0", "26.4.1", "27.0.0"])
def test_version_26_and_newer_is_a_hard_error(raw):
    support = check_rest_support(raw)
    assert support.status == REMOVED
    assert support.is_fatal is True
    msg = support.message.lower()
    assert "removed" in msg
    assert "/api/current" in msg  # points at the replacement transport
    assert "cannot manage this server" in msg


@pytest.mark.parametrize("raw", ["24.04.2", "TrueNAS-SCALE-24.04.2", "25.04.1", "22.12.4"])
def test_older_versions_are_clean(raw):
    support = check_rest_support(raw)
    assert support.status == SUPPORTED
    assert support.is_ok is True
    assert support.is_fatal is False
    # Even the clean verdict states the deadline; it never reads as "forever".
    assert "removed in TrueNAS 26" in support.message


@pytest.mark.parametrize("raw", [None, "", "   ", "who-knows", 12345])
def test_missing_or_garbage_version_degrades_to_unknown_not_ok(raw):
    support = check_rest_support(raw if isinstance(raw, str) or raw is None else None)
    assert support.status == UNKNOWN
    assert support.parsed is None
    assert support.is_ok is False
    assert support.is_fatal is False  # unknown must not be reported as removed
    assert "UNKNOWN" in support.message


def test_unknown_message_distinguishes_absent_from_unparseable():
    assert "no version field" in check_rest_support(None).message
    assert "'who-knows'" in check_rest_support("who-knows").message


def test_support_verdict_is_immutable():
    support = check_rest_support("25.10.4")
    with pytest.raises(AttributeError):
        support.status = REMOVED  # type: ignore[misc]
