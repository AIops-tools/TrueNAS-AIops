# Changelog

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
