<!-- mcp-name: io.github.AIops-tools/truenas-aiops -->

# TrueNAS AIops (preview)

> **Disclaimer**: Community-maintained open-source project. **Not affiliated with, endorsed by, or sponsored by iXsystems or the TrueNAS project.** "TrueNAS" is a trademark of its owner. MIT licensed.

AI-powered **TrueNAS SCALE** storage operations with a **built-in governance
harness** — unified audit log, policy engine, token/runaway budget guard,
undo-token recording, and graduated-autonomy risk tiers. Self-contained: no
external dependencies beyond `httpx` and the MCP SDK. **Preview — mock-validated
only, not yet verified against a live TrueNAS appliance.**

## What works

- **CLI** (`truenas-aiops ...`): `init`, `overview`, `system`, `pool list/get/status/scrub-status/capacity/scrub-start`, `dataset list/get/create`, `snapshot list/create/delete`, `disk list/smart`, `alert list`, `service list/restart`, `replication list/cloudsync`, `secret set/list/rm/migrate/rotate-password`, `doctor`, `mcp`.
- **MCP server** (`truenas-aiops mcp` or `truenas-aiops-mcp`): **21 tools** (16 read, 5 write), every one wrapped with the bundled `@governed_tool` harness.
- **Encrypted credentials**: the TrueNAS API key lives in an encrypted store `~/.truenas-aiops/secrets.enc` (Fernet + scrypt) — **never plaintext on disk**. Unlock with a master password from `TRUENAS_AIOPS_MASTER_PASSWORD` (MCP/CI) or an interactive prompt (CLI).
- **Reversibility**: `snapshot_create` records an inverse `snapshot_delete` undo descriptor. The irreversible `snapshot_delete` (`high` risk) captures the snapshot's BEFORE state for the audit record and declares no undo.
- **Safety**: destructive CLI ops (`snapshot delete`, `service restart`) require double confirmation and support `--dry-run`.

## Capability matrix (21 MCP tools)

| Category | Tools | Count | R/W |
|----------|-------|:-----:|:---:|
| **Overview / System** | `overview`, `system_info` | 2 | read |
| **Pools** | `pool_list`, `pool_get`, `pool_status`, `scrub_status`, `pool_capacity` | 5 | read |
| | `pool_scrub_start` | 1 | write (medium) |
| **Datasets** | `dataset_list`, `dataset_get` | 2 | read |
| | `dataset_create` | 1 | write (medium) |
| **Snapshots** | `snapshot_list` | 1 | read |
| | `snapshot_create` (medium), `snapshot_delete` (high) | 2 | write |
| **Disks** | `disk_list`, `smart_test_results` | 2 | read |
| **Alerts** | `alert_list` | 1 | read |
| **Services** | `service_list` | 1 | read |
| | `service_restart` | 1 | write (medium) |
| **Replication** | `replication_list`, `cloudsync_list` | 2 | read |

## Quick start

```bash
uv tool install truenas-aiops
truenas-aiops init        # interactive wizard: connection details + encrypted API key
truenas-aiops doctor      # verify config, encrypted store, connectivity (hits /system/info)
```

`init` writes `~/.truenas-aiops/config.yaml` (non-secret connection details) and
stores the API key **encrypted** in `~/.truenas-aiops/secrets.enc`. Example
config it produces:

```yaml
targets:
  - name: nas1
    host: 10.0.0.30
    port: 443
    verify_ssl: false          # self-signed lab certs only
    api_path: /api/v2.0
```

Create the API key in the TrueNAS UI under **Credentials → API Keys**. For
non-interactive use (MCP server, CI, cron) export the master password so the
store can be unlocked without a prompt:

```bash
export TRUENAS_AIOPS_MASTER_PASSWORD='your-master-password'
```

### Managing secrets

```bash
truenas-aiops secret set nas1             # prompts hidden for the API key
truenas-aiops secret list                 # names only, values never shown
truenas-aiops secret rm nas1
truenas-aiops secret rotate-password      # re-encrypt under a new master password
truenas-aiops secret migrate              # import a legacy plaintext .env, then deletes it
```

A legacy plaintext env var `TRUENAS_<TARGET_NAME_UPPER>_APIKEY` is still honoured
as a fallback with a deprecation warning (migrate with `truenas-aiops secret migrate`).

## 支持范围 / Supported scope

Read: system info, ZFS pools (list/get/status/scrub-status/capacity), datasets
(list/get), snapshots (list), disks + S.M.A.R.T. results, alerts, services,
replication & cloud-sync tasks, one-shot health overview. Mutating (governed,
dry-run + double-confirm where destructive): `pool_scrub_start`,
`dataset_create`, `snapshot_create`, `snapshot_delete`, `service_restart`.

**缺功能？(Missing something?)** This is a focused preview. Open an issue or PR at
[github.com/AIops-tools/TrueNAS-AIops](https://github.com/AIops-tools/TrueNAS-AIops/issues)
— feature requests, contributions, and comments are all welcome.

## Preview caveats

- **Mock-only**: all behaviour is validated against mocked REST responses; not
  yet run against a live TrueNAS SCALE appliance. `truenas-aiops doctor` is the
  fastest live check.
- Endpoint paths (e.g. `/pool/scrub/run`, `/zfs/snapshot/id/{id}`,
  `/smart/test/results`, `/alert/list`) are modelled against the documented
  TrueNAS SCALE REST v2.0 API and need live verification.
- Out of scope by design: anything that destroys bulk data (dataset/pool
  deletion, replication runs that overwrite) — only `snapshot_delete` removes
  data, and it is `high` risk + double-confirmed.

## Not for

Other NAS/storage or backup products, hypervisor VM lifecycle, container
clusters, or network devices — those are out of scope for this tool.

## License

MIT — [github.com/AIops-tools/TrueNAS-AIops](https://github.com/AIops-tools/TrueNAS-AIops)
