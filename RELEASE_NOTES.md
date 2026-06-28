# TrueNAS AIops v0.1.0 — preview

Governed **TrueNAS SCALE** storage operations for AI agents, with a built-in
governance harness (audit, policy, token/runaway budget, undo-token recording,
graduated risk tiers) and an encrypted credential store. Standalone — no
external skill-family dependency.

> **Preview / mock-only.** All behaviour is validated against mocked REST
> responses; it has not been run against a live TrueNAS SCALE appliance. The
> fastest live check is `truenas-aiops doctor`.

## Highlights

- **21 MCP tools** (16 read, 5 write), every one wrapped with `@governed_tool`.
  - Read: health `overview`, `system_info`; ZFS pools (`pool_list/get/status`,
    `scrub_status`, `pool_capacity`); datasets (`dataset_list/get`); snapshots
    (`snapshot_list`); disks (`disk_list`, `smart_test_results`); `alert_list`;
    `service_list`; `replication_list`, `cloudsync_list`.
  - Write: `pool_scrub_start` (medium), `dataset_create` (medium),
    `snapshot_create` (medium, records inverse undo), `snapshot_delete` (high,
    irreversible, captures BEFORE state), `service_restart` (medium).
- **Encrypted API key store** (`~/.truenas-aiops/secrets.enc`, Fernet + scrypt)
  — never plaintext on disk; legacy `TRUENAS_<TARGET>_APIKEY` env fallback.
- **CLI** with an `init` onboarding wizard, `secret` management, and `doctor`.
- **Bearer-auth REST connection layer** over the TrueNAS SCALE REST API v2.0
  with teaching error translation (`TrueNASApiError`).

## Install

```bash
uv tool install truenas-aiops
truenas-aiops init
truenas-aiops doctor
```

## Caveats

- Endpoint paths are modelled against the documented TrueNAS SCALE REST v2.0 API
  and need live verification.
- Out of scope by design: pool/dataset deletion, share/user/app management, and
  any bulk-data-destroying operation beyond `snapshot_delete`.
