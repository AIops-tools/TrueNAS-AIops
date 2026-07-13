"""Shared fixtures for the truenas-aiops test suite (no live TrueNAS).

The REST connection is always a MagicMock/fake; these fixtures only shape the
governance environment the tools run under.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_approver(monkeypatch):
    """The policy layer is secure-by-default: with no rules.yaml, high/critical
    governed calls require a named approver. Tests exercising tool behavior
    are not about that gate, so record a synthetic approver globally; the
    governance-persistence tests remove it to test the gate itself."""
    monkeypatch.setenv("TRUENAS_AUDIT_APPROVED_BY", "pytest")
