<!-- mcp-name: io.github.AIops-tools/truenas-aiops -->

# TrueNAS AIops

> **Disclaimer**: Community-maintained open-source project. **Not affiliated with, endorsed by, or sponsored by iXsystems or the TrueNAS project.** "TrueNAS" is a trademark of its owner. MIT licensed.

AI-powered **TrueNAS SCALE** storage operations with a **built-in governance
harness** — unified audit log, token/runaway budget guard, undo-token
recording, and descriptive risk tiers. Speaks **both** TrueNAS APIs: REST v2.0
and the JSON-RPC/WebSocket API that replaces it in TrueNAS 26.

> **Verification status**: live-verified against a real TrueNAS SCALE 25.04.2.1
> appliance over both transports, including a full write → audit → undo →
> verified-restore loop. Coverage is listed endpoint by endpoint — and so are
> the gaps — in [docs/VERIFICATION.md](docs/VERIFICATION.md). Read it rather
> than reading "verified" as "everything".

## Supported TrueNAS versions — and which API you are speaking

`truenas-aiops` speaks **both** TrueNAS APIs and picks the one that will still
exist:

| TrueNAS version | REST API v2.0 | JSON-RPC over WebSocket | what this tool does |
|---|---|---|---|
| ≤ 25.10.0 | supported | — | REST |
| 25.04 – 25.10.x | deprecated (every call raises an appliance alert) | **already served** at `/api/current` | **WebSocket** (auto) |
| **26 and newer** | **removed** | required | **WebSocket** |

Set `transport:` per target in `config.yaml`:

```yaml
targets:
  - name: nas1
    host: nas1.example.com
    transport: auto        # default — probe /api/current, prefer WebSocket
    # transport: websocket # pin the API that survives TrueNAS 26
    # transport: rest      # pin REST while migrating
```

`auto` probes `/api/current` with a cheap HTTP upgrade (no credential spent). If
the appliance offers it, the tool uses it; otherwise it falls back to REST,
which is still correct on 25.10 and older.

**iXsystems documents that upgrading to TrueNAS 26 revokes existing API keys** —
so expect to mint a new one after the upgrade. *We have not reproduced this
ourselves*; it is reported here from the upstream release notes, not from a
verified upgrade. Treat it as a caution, not a measurement.

`truenas-aiops doctor` tells you which transport the connection actually used,
reads the server version, and — on REST — says plainly whether REST is
supported, deprecated, or gone. If the version cannot be parsed it reports
**UNKNOWN**, never a clean bill of health it cannot justify.


## What works

- **CLI** (`truenas-aiops ...`): `init`, `overview`, `system`, `pool list/get/status/scrub-status/capacity/scrub-start`, `dataset list/get/create`, `diagnose pool-health/alerts`, `snapshot list/create/delete`, `disk list/smart`, `alert list`, `service list/restart`, `replication list/cloudsync`, `secret set/list/rm/migrate/rotate-password`, `doctor`, `mcp`.
- **MCP server** (`truenas-aiops mcp` or `truenas-aiops-mcp`): **25 tools** (19 read, 6 write), every one wrapped with the bundled `@governed_tool` harness.
- **Encrypted credentials**: the TrueNAS API key lives in an encrypted store `~/.truenas-aiops/secrets.enc` (Fernet + scrypt) — **never plaintext on disk**. Unlock with a master password from `TRUENAS_AIOPS_MASTER_PASSWORD` (MCP/CI) or an interactive prompt (CLI).
- **Reversibility**: `snapshot_create` records an inverse `snapshot_delete` undo descriptor. The irreversible `snapshot_delete` (`high` risk) captures the snapshot's BEFORE state for the audit record and declares no undo.
- **Safety**: destructive CLI ops (`snapshot delete`, `service restart`) require double confirmation and support `--dry-run`.

## What this tool does, and does not, decide

It delivers TrueNAS SCALE storage operations — reads and writes — accurately and
efficiently, and records every one of them. It does **not** decide whether a
write is allowed to happen. That is the agent's judgement, or the permission of
the account you connect it with: scope the TrueNAS API key to a limited-privilege
account and the writes fail at the appliance — the place that actually owns the
permission.

So there is no read-only switch, no policy file, no approval gate to configure.
The one thing the tool guarantees is that nothing is silent: **every call, over
MCP and over the CLI alike, lands an audit row** in `~/.truenas-aiops/audit.db`,
and reversible writes still capture their before-state and record an inverse.

> Each tool declares a `risk_level`, kept in agreement with its `[READ]`/`[WRITE]`
> documentation tag by a test, and carried into the audit row as a descriptive
> tier — so a reviewer can see at a glance that a row was a high-risk delete. It
> is a label, not a gate.

Running a smaller / local model? See
[agent-guardrails.md](skills/truenas-aiops/references/agent-guardrails.md) — it lists
the guardrails this tool now enforces for you (so you don't spend prompt budget
restating them) and gives a ready-made system prompt for what's left.

## Playbook: triage a degraded pool

```bash
truenas-aiops diagnose pool-health            # worst-first: bad state, error counters, capacity
# → e.g. CRITICAL tank "pool status is DEGRADED", and "read=4 checksum=2" on a vdev
truenas-aiops pool status tank                # inspect the topology / scan detail it cited
truenas-aiops pool scrub-start tank           # kick an integrity scrub (governed, medium risk)
truenas-aiops diagnose alerts                 # cross-check active alerts + any datasets near full
```

Each finding cites the measured number that tripped it (status string, error
counts, used-percent) so you see **why** it was flagged, then points at the exact
read/write command to act on it.

## Capability matrix (25 MCP tools)

| Category | Tools | Count | R/W |
|----------|-------|:-----:|:---:|
| **Overview / System** | `overview`, `system_info` | 2 | read |
| **Diagnostics / RCA** | `pool_health_rca`, `alert_and_capacity_rca` | 2 | read |
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
| **Undo (governance)** | `undo_list` | 1 | read |
| | `undo_apply` | 1 | write (medium) |

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

Versions: **TrueNAS SCALE 25.04 and newer over JSON-RPC/WebSocket, and any build
still serving REST v2.0 over REST** — the transport is selected automatically.
See [Supported TrueNAS versions](#supported-truenas-versions--and-which-api-you-are-speaking).
Note that iXsystems documents an upgrade to TrueNAS 26 as **revoking existing
API keys** (upstream claim, not reproduced here).

Read: system info, ZFS pools (list/get/status/scrub-status/capacity), datasets
(list/get), snapshots (list), disks + S.M.A.R.T. results, alerts, services,
replication & cloud-sync tasks, one-shot health overview, and read-only
diagnostics / RCA (`pool_health_rca`, `alert_and_capacity_rca`). Mutating (governed,
dry-run + double-confirm where destructive): `pool_scrub_start`,
`dataset_create`, `snapshot_create`, `snapshot_delete`, `service_restart`.

**缺功能？(Missing something?)** Coverage is intentionally focused. Open an issue or PR at
[github.com/AIops-tools/TrueNAS-AIops](https://github.com/AIops-tools/TrueNAS-AIops/issues)
— feature requests, contributions, and comments are all welcome.

## Caveats

- **Live-verified against TrueNAS SCALE 25.04.2.1** over both transports —
  reads cross-checked against the appliance's own API, and a full
  write → audit → undo → verified-restore loop. What is and is not covered is
  listed endpoint by endpoint in [docs/VERIFICATION.md](docs/VERIFICATION.md);
  read it rather than assuming "verified" means everything.
- **Still unverified**: S.M.A.R.T. against failing media (needs real hardware —
  virtio exposes no S.M.A.R.T. at all), replication/cloudsync against real
  targets, and TrueNAS 26's `auth.login_ex` (25.04 exercises only the fallback).
- **CLI exit codes**: `0` confirmed, `1` failed or refused, `2` outcome
  undetermined (the operation may still be in flight — poll before retrying).
- Out of scope by design: anything that destroys bulk data (dataset/pool
  deletion, replication runs that overwrite) — only `snapshot_delete` removes
  data, and it is `high` risk + double-confirmed.

## Not for

Other NAS/storage or backup products, hypervisor VM lifecycle, container
clusters, or network devices — those are out of scope for this tool.

## License

MIT — [github.com/AIops-tools/TrueNAS-AIops](https://github.com/AIops-tools/TrueNAS-AIops)
