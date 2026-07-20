<!-- mcp-name: io.github.AIops-tools/truenas-aiops -->

# TrueNAS AIops

> **Disclaimer**: Community-maintained open-source project. **Not affiliated with, endorsed by, or sponsored by iXsystems or the TrueNAS project.** "TrueNAS" is a trademark of its owner. MIT licensed.

AI-powered **TrueNAS SCALE** storage operations with a **built-in governance
harness** — unified audit log, policy engine, token/runaway budget guard,
undo-token recording, and graduated-autonomy risk tiers. Self-contained: no
external dependencies beyond `httpx` and the MCP SDK. **Mock-validated
only, not yet verified against a live TrueNAS appliance.**

> **Verification status**: mock-validated only; REST endpoint paths are modelled from the
> documented API and not yet confirmed against a live appliance. See
> [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Supported TrueNAS versions — read this before upgrading

This tool talks to TrueNAS over the **REST API v2.0** (`/api/v2.0`), and iXsystems
is retiring that API on a published timeline:

| TrueNAS version | REST API v2.0 | What `truenas-aiops` does |
|---|---|---|
| ≤ 25.10.0 | supported | works normally |
| 25.10.1 – 25.10.x | deprecated; **every REST call raises a deprecation alert on the appliance** | works, and `doctor` warns you |
| **26 and newer** | **removed** | **does not work at all** — `doctor` fails with an explanation |

TrueNAS **26 removed REST entirely**, replacing it with JSON-RPC 2.0 over a
persistent WebSocket at `/api/current`. `truenas-aiops` does not speak that
transport yet, so **upgrading an appliance to TrueNAS 26 is a breaking change for
this tool** — not a routine upgrade. There is no configuration that works around
it; a WebSocket backend is a separate piece of work (new dependency, persistent
connection, and a different auth flow, since 26 also deprecates
`auth.login_with_api_key`).

Two things make this visible rather than mysterious:

- **`truenas-aiops doctor` reads the server version** from `/system/info` and says
  plainly whether REST is supported, deprecated, or gone. If the version cannot be
  read or parsed it reports **UNKNOWN** — never a clean bill of health it cannot
  justify.
- **The connection layer recognises the failure shape.** On a TrueNAS 26 box every
  REST path 404s; a 404 on an endpoint that exists on every REST-capable TrueNAS
  (e.g. `/system/info`, `/pool`) raises `UnsupportedServerVersion` with an
  explanation, instead of a pile of "resource not found — the id may be stale"
  errors that send you hunting a stale id that was never the problem.

If you are on 25.10.x today, this tool works — plan the 26 upgrade knowing it will
stop.

## What works

- **CLI** (`truenas-aiops ...`): `init`, `overview`, `system`, `pool list/get/status/scrub-status/capacity/scrub-start`, `dataset list/get/create`, `diagnose pool-health/alerts`, `snapshot list/create/delete`, `disk list/smart`, `alert list`, `service list/restart`, `replication list/cloudsync`, `secret set/list/rm/migrate/rotate-password`, `doctor`, `mcp`.
- **MCP server** (`truenas-aiops mcp` or `truenas-aiops-mcp`): **25 tools** (19 read, 6 write), every one wrapped with the bundled `@governed_tool` harness.
- **Encrypted credentials**: the TrueNAS API key lives in an encrypted store `~/.truenas-aiops/secrets.enc` (Fernet + scrypt) — **never plaintext on disk**. Unlock with a master password from `TRUENAS_AIOPS_MASTER_PASSWORD` (MCP/CI) or an interactive prompt (CLI).
- **Reversibility**: `snapshot_create` records an inverse `snapshot_delete` undo descriptor. The irreversible `snapshot_delete` (`high` risk) captures the snapshot's BEFORE state for the audit record and declares no undo.
- **Safety**: destructive CLI ops (`snapshot delete`, `service restart`) require double confirmation and support `--dry-run`.

## Security: read-only mode

This tool is meant to be handed to an AI agent, so its safety story is enforced
by the server rather than requested in a prompt:

```bash
export TRUENAS_READ_ONLY=1
```

With that set, the **6 write tools are never registered**. An MCP client
lists **19 tools instead of 25** — the writes are not hidden, not
gated behind a flag, and not merely refused when called. They are absent from
the session. A model cannot invoke a tool it was never offered, and cannot be
argued into one.

That distinction is the whole point. A tool that exists but refuses still invites
retry loops and "I'll describe the call instead" behaviour from smaller models,
and it leaves a reviewer trusting a promise. An absent tool is a fact you can
check: connect, list the tools, and see that the writes are not there.

Enforcement is two layers deep, so the switch cannot be sidestepped by changing
entry point:

| Layer | What it does | Covers |
|---|---|---|
| `@governed_tool` harness | refuses every non-read operation outright | MCP, CLI, and in-process callers |
| MCP registration | write tools are removed from `list_tools()` | anything speaking MCP |

Read operations are unaffected, and every call is still audited to
`~/.truenas-aiops/audit.db`.

> The read/write split is derived from each tool's declared `risk_level`, and a
> test asserts that this never disagrees with the `[READ]`/`[WRITE]` tag in the
> tool's own documentation — so a write can't quietly present itself as a read.

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

Versions: TrueNAS builds that still serve the **REST API v2.0** — i.e. **up to and
including 25.10.x**, with a deprecation warning from 25.10.1. **TrueNAS 26 and newer
are not supported** (REST removed); see
[Supported TrueNAS versions](#supported-truenas-versions--read-this-before-upgrading).

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

- **TrueNAS 26 is not supported**: REST v2.0 — the only transport this tool
  speaks — was removed in TrueNAS 26. See
  [Supported TrueNAS versions](#supported-truenas-versions--read-this-before-upgrading).
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
