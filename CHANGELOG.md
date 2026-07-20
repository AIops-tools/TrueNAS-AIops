# Changelog

## v0.5.0 — 2026-07-20

### Fixed
- **TrueNAS 26 removes the REST API this tool speaks.** REST was deprecated in 25.04 and is gone in 26 (in beta now), replaced by JSON-RPC over WebSocket.
- **`restart_service` validates the service name.** It previously forwarded any string, and the code that looks like a guard was only capturing prior state.
- **New `scheme:`** (default `https`) — the base URL was hardcoded..
- Harness: a write whose response is lost is audited `status=unknown`, not `error` — it may have taken effect. Undo tokens gain `effectVerified` (undo.db migrated in place).
- Harness: a dry-run no longer records an undo token, and no longer requires a named approver. Guards now run on the preview path.
- Truncated strings end in an ellipsis instead of being cut silently; error messages are capped at 800 chars, not 300.

See RELEASE_NOTES.md for the full detail.

## v0.3.0 — 2026-07-17

### Added
- **Undo executor**: `undo list` / `undo apply <id>` (CLI + MCP) — apply a recorded replayable inverse; the dispatched inverse is re-gated by its own risk tier; single-use, dry-run, double-confirm, both wrapper + inverse audited.

## v0.2.1 — 2026-07-16

### Fixed
- **`secrets.enc` now follows `TRUENAS_AIOPS_HOME`** (secretstore hardcoded the real
  home directory; config/audit/undo already relocated — found in live verification).
- **Audit fidelity**: failures sanitized into `{"error": ...}` results by the MCP error
  layer are now audited as `status=error` (they previously read as `ok`, hiding failed
  attempts from exception reports), and no undo is recorded for a call that failed.

### Tests
- `doctor` and the `init` wizard are now fully covered (previously ~10–20%); plus a
  regression test for the sanitized-failure audit status.

## v0.2.0 — 2026-07-13

Security-hardening release from a line-wide code review.

### Changed (behavior)
- **Secure by default**: with no `rules.yaml`, high/critical operations now require a
  named approver (`TRUENAS_AUDIT_APPROVED_BY`). A fresh install no longer allows
  destructive writes unattended; `init` seeds a starter `rules.yaml` you can edit,
  and an operator-authored rules file is honoured as-is.
- `__version__` is now single-sourced from package metadata (the previous release
  self-reported a stale version string).
- Sanitize docs no longer overstate scope: it strips control/format characters and
  truncates; semantic prompt-injection resistance must come from the consuming agent.

### Fixed
- Agent-supplied ids are percent-encoded in REST URL paths (path-traversal hardening).
- `init` TLS verification prompt now defaults to ON.
- Cached HTTP clients are closed at process exit.

### Tests
- Governance persistence is now tested against REAL `audit.db`/`undo.db` files
  (write → audit row + inverse undo row with captured prior state).
- The CLI confirmed-write path (dry-run / double-confirm / governed execution) is
  covered end-to-end.
- `pytest-cov` added to the dev dependencies.

## v0.1.1

- Fix: `TRUENAS_AIOPS_HOME` now also relocates `config.yaml` (was hardcoded to `~/.truenas-aiops`).
- Fix: **CLI writes are now audited + undo-recorded** via the governance path — previously only the MCP tools recorded audit/undo; CLI `manage`/`remediate`/etc. writes now go through the same `@governed_tool` layer (they keep their dry-run + double-confirm). CLI write output is now the governed JSON result. No API/tool changes.


All notable changes to truenas-aiops are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## [0.1.0] — preview

Initial preview release: governed TrueNAS SCALE storage operations with a
bundled governance harness. **Mock-validated only — not yet verified against a
live TrueNAS appliance.**

### Added

- **21 MCP tools** (16 read, 5 write), every one wrapped with the bundled
  `@governed_tool` harness (audit, policy, token/runaway budget, undo,
  risk-tiers):
  - **Overview / System** — `overview`, `system_info`.
  - **Pools** — `pool_list`, `pool_get`, `pool_status`, `scrub_status`,
    `pool_capacity` (read); `pool_scrub_start` (write, medium).
  - **Datasets** — `dataset_list`, `dataset_get` (read); `dataset_create`
    (write, medium).
  - **Snapshots** — `snapshot_list` (read); `snapshot_create` (write, medium,
    records inverse `snapshot_delete` undo); `snapshot_delete` (write, high,
    irreversible, captures BEFORE state).
  - **Disks** — `disk_list`, `smart_test_results` (read).
  - **Alerts** — `alert_list` (read).
  - **Services** — `service_list` (read); `service_restart` (write, medium).
  - **Replication** — `replication_list`, `cloudsync_list` (read).
- **Encrypted secret store** — the TrueNAS API key is stored encrypted in
  `~/.truenas-aiops/secrets.enc` (Fernet + scrypt); never plaintext on disk.
  Legacy `TRUENAS_<TARGET>_APIKEY` env var honoured as a fallback.
- **CLI** (`truenas-aiops`) — `init` wizard, `secret` management, `doctor`,
  `overview`, `system`, and per-domain sub-commands.
- **Bearer-auth REST connection layer** over the TrueNAS SCALE REST API v2.0
  with centralised teaching error translation (`TrueNASApiError`).

### Known limitations

- Preview / mock-only: endpoint paths (e.g. `/pool/scrub/run`,
  `/zfs/snapshot/id/{id}`, `/smart/test/results`, `/alert/list`) are modelled
  against the documented REST v2.0 API and need live verification.
- Out of scope by design: pool/dataset deletion, share/user/app management, and
  anything that destroys bulk data beyond `snapshot_delete`.
