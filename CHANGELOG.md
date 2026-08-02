# Changelog

## Unreleased

### Changed (BREAKING)
- **Requires MCP SDK 2.0** (`mcp[cli]>=2.0,<3.0`). `mcp.server.fastmcp` no longer exists in 2.0; the server is now built with `MCPServer` and reports its package version in the stdio handshake.

### Fixed
- **Authentication could never use `auth.login_ex`.** It defaulted the username to empty, which TrueNAS answers with `AUTH_ERR`, and the fallback to the deprecated `auth.login_with_api_key` silently rescued every login — so the tool depended entirely on a deprecated method while appearing future-proof. `login_ex` is now used whenever `username` is configured (both 25.04 and 26 serve it) and its failures are **reported**, not masked: a wrong username used to be papered over. With no `username`, the deprecated call is used and warned about.
- **The method table was pinned to one release's names.** Snapshots are `zfs.snapshot.*` on 25.04 and `pool.snapshot.*` on TrueNAS 26 — each namespace absent from the other — and `service.restart` became `service.control`. Routes now carry candidates resolved against the appliance's own `core.get_methods`, so one build works on both. `smart_test_results` has **no equivalent on 26** and refuses with a teaching error rather than returning an empty list.
- **The CLI printed success for a failed write.** A governed twin returning `{"error": ...}` still produced a green line and exit 0 — live-caught on TrueNAS 26 where the middleware rejected the call outright. Every CLI write now goes through `checked()`: error → exit 1, undetermined → exit 2.
- **The pool RCA sanitised the pool name but not its status.** Unlike the sibling tools, whose RCAs are handed already-sanitized ops output, this one receives RAW `/pool` records — so appliance-controlled text reached a finding an agent reads without passing the control-character filter. `.upper()` is not a sanitiser. A line-wide sweep confirmed this repo was the only one affected; the other RCAs re-stringify values their ops layer already cleaned.
- **`undo apply` works from the CLI.** Every write tool is imported lazily inside its own CLI command, so a CLI-driven undo ran in a process where the inverse tool was never registered and failed with "inverse tool is not registered" — for every write tool. Only the MCP entry point, which imports the whole server, worked.

### Added
- **JSON-RPC 2.0 over WebSocket transport (`/api/current`)** — the API that survives TrueNAS 26, which removed REST v2.0. New `transport:` setting per target: `auto` (default; probes the appliance and prefers WebSocket), `websocket`, or `rest`. The transport presents the same `get`/`post`/`delete` surface over REST-shaped paths, so no ops module changed. Every middleware method was taken from a live appliance's `core.get_methods` and cross-checked against its REST result; the full write→audit→undo→verified-restore loop passes over WebSocket. `websockets` is now a **declared** dependency (it was only transitive via `mcp`), and the frame ceiling is raised well above the library's 1 MiB default, which closes the connection with `1009 message too big` on any large listing.
- `doctor` reports the transport in use, and no longer warns that "this tool needs a WebSocket transport" while using one.
- **Pool reads accept a pool name, not just the numeric id.** `/pool/id/{id}` takes TrueNAS's numeric id, so `get_pool` / `pool_status` / `scrub_status` returned `404 … the id may be stale` for a pool *name* — the only identifier a caller ever has. This tool's own pool-health finding reports `resource: tank` and advises `Inspect 'pool status tank'`, which therefore could not work. An id that is neither numeric nor a known name is still percent-encoded on the fallback path.
- **A DEGRADED pool now names the failed member.** `pool_status` returns `members` (group, vdev, device, guid, ZFS state, read/write/checksum counters) and `unhealthyMembers`, and the pool-health finding's detail lists them. Previously the tool reported only that the pool was DEGRADED, leaving "which disk?" — the first question during a degradation — unanswered. Live-verified by yanking a mirror member from a real TrueNAS SCALE 25.04.2.1 appliance, and again on recovery.

## v0.6.0 — 2026-07-21

### Changed (BREAKING)
- **Removed the authorization layer** — read-only mode, the approver gate, and rules.yaml deny are gone. The skill no longer decides read vs write; that is the agent's judgement or the connecting account's permissions. `<PREFIX>_READ_ONLY` now has no effect (a startup warning is logged); `<PREFIX>_AUDIT_APPROVED_BY`/`_RATIONALE` are optional audit annotations.
- The retained guarantee is **unbypassable audit over MCP and CLI alike** — no unaudited entry point. Harness = audit + runaway safety guard + undo + sanitize; `risk_level` is a descriptive audit label, not a gate.

See RELEASE_NOTES.md for tool-specific changes.


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
