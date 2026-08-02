# Live verification status

This document records what has and has not been validated against a real
TrueNAS SCALE appliance, so the maturity claim is auditable.

## 🔴 Round 2 — degraded-pool RCA (2026-08-02): two real bugs

Closes the "multi-disk failure / degraded-pool RCA" gap named below. A **real
fault was seeded** rather than inspected: a mirror member was yanked from the
running appliance (`virsh detach-disk tn1 vdc --live`), which ZFS reported as
`tank DEGRADED` with a `REMOVED` child. Two defects surfaced.

### 1. Every pool read took the numeric id only — so the RCA's own advice failed

`/pool/id/{id}` wants TrueNAS's numeric id, but the **name** is the only
identifier a caller ever has. The pool-health finding reports `resource: tank`
and advises `Inspect 'pool status tank'` — running exactly that returned
`404 … the id may be stale`, sending the operator to hunt a staleness problem
that does not exist. An agent copying the remediation string verbatim (the
weak-model case this line designs for) could never succeed.

**Fixed**: `get_pool` / `pool_status` / `scrub_status` resolve a numeric id
*or* a name. An id that is neither is still percent-encoded on the fallback
path, so name resolution cannot become a way to smuggle a path segment.

### 2. A DEGRADED verdict could not say which disk failed

`pool status` returned only `dataVdevs: 1`, and the finding said just
`pool status is DEGRADED`. The operator's first question during a degradation is
always *which disk*, and only `topology` answers it — the tool never read it.

**Fixed**: `pool_status` now returns `members` (one row per leaf device: group,
vdev, device, guid, ZFS state, read/write/checksum counters) and
`unhealthyMembers`. The finding's detail names them. Verified live:

```
detail: pool status is DEGRADED; failed member(s): <device gone> (REMOVED)
unhealthyMembers: [{vdev: MIRROR, device: null, guid: 1849966443203080812,
                    status: REMOVED, readErrors: 0, ...}]
```

`device: null` is honest — a REMOVED member has no device name left, and the
`guid` is what ZFS actually needs to online/replace it. Absent stays absent
rather than being invented as `""`.

### Recovery verified too

Reattaching the disk and onlining it by guid returned `tank ONLINE`, both
members `ONLINE`, `unhealthyMembers: 0`, and the RCA went quiet — so the
analysis tracks recovery, not just failure.

### ⛔ S.M.A.R.T. remains unverifiable in this lab — and now for a checked reason

Not "untested": **impossible here**. `disk smart` returns `[]`, and so does the
appliance's own `/smart/test/results` — the empty result is real. Asking TrueNAS
to run a test proves why:

```
smartctl failed for disk vdb: /dev/vdb: Unable to detect device type
```

virtio block devices expose no SMART at all. A SATA disk cannot be hot-plugged
into this VM, and even cold-plugged, QEMU would emulate a *healthy* drive —
whereas the gap that matters is S.M.A.R.T. on **failing** media, which no
emulator can produce. Closing this needs real hardware with a real bad disk.

## ✅ Live-verified against real TrueNAS SCALE 25.04.2.1 (2026-08-01)

Verified end-to-end against a real TrueNAS SCALE 25.04.2.1 appliance (nested-KVM
lab, real ZFS mirror pool), driven through the real governed CLI + API-key path,
with every read cross-checked against the appliance's own API. **Two real bugs,
both of which broke the feature outright on any real appliance:**

1. **🔴 Alerts never loaded — `/alert/list` was called with POST.** It is a
   **GET** in the v2.0 REST API; POST returns `405 Method Not Allowed`. Because
   alerts are a read, the whole alerts section of `overview` degraded to an
   `error` envelope on every appliance. Fixed; `overview` now reports real
   alerts (verified: 1 INFO "system update available").
2. **🔴 Every disk reported `pool: null`.** TrueNAS only populates a disk's
   `pool` when `extra.pools` is requested; a plain `GET /disk` returns null for
   every disk, including ones in a pool — making an in-use disk
   indistinguishable from an unassigned spare, which is the exact question the
   read exists to answer. Fixed; now reports `sda→boot-pool`, `sdb/sdc→tank`.

**Endpoint audit** — every path the tool calls was probed against the live
appliance. All reads (`/system/info`, `/pool`, `/pool/dataset`, `/zfs/snapshot`,
`/disk`, `/service`, `/replication`, `/cloudsync`, `/smart/test/results`,
`/alert/list`) return 200 with the modelled shapes; the only verb error was the
alert POST above.

**Live loop that passed:** `doctor` (connects, and correctly warns REST is
deprecated in 25.04 / removed in 26) · `system` · `pool list` (tank ONLINE,
free matches) · `dataset list` · `disk list` · `alert list` · `overview` · and a
full **write → audit → undo → verified restore**: `snapshot create tank@aiopssnap`
→ appliance snapshot count 7→8 → `undo apply` → `snapshot_delete`,
`effectVerified: true`, count back to 7 and the snapshot gone. Every governed
write landed an audit row.

Not covered: multi-disk failure/degraded-pool RCA, S.M.A.R.T. on real failing
media, replication/cloudsync against real targets, and the **WebSocket JSON-RPC
transport TrueNAS 26 requires** (this tool still speaks REST — see below).

> **Lab recipe:** TrueNAS ships no answerfile, so the ncurses installer must be
> driven. Two things were mandatory: **UEFI with Secure Boot OFF** (Ubuntu's
> default OVMF rejects TrueNAS's bootloader with `BdsDxe: ... Access Denied`,
> and on SeaBIOS the kernel emitted nothing at all), and a **grub.cfg patched in
> place on the ISO** to default to the serial entry (the ISO cannot be rebuilt —
> hybrid MBR/GPT — and GRUB's serial menu ignores the `--hotkey`). The password
> screen is one form with two fields, so the wizard needs `pw <Tab> pw <Enter>`.

---

## Historical status (superseded by the run above)

Beyond the usual mock-only caveat there was a specific, substantive
risk worth stating plainly:

> The REST endpoint paths are **modelled against the documented TrueNAS SCALE
> REST v2.0 API**, not confirmed against a running appliance. A path or field
> name that differs on your build will surface as an error, not as silent
> wrong data — but it will surface.

This is the single highest-value thing a community tester can fix, and it is
cheap to test: TrueNAS SCALE runs fine as a VM.

## The transport itself has an expiry date (TrueNAS 26)

Separate from "are the paths right", there is a **deadline on the whole
transport**. This tool speaks the REST API v2.0 only, and iXsystems is retiring
it:

| TrueNAS version | REST API v2.0 status |
|---|---|
| 25.04 | deprecated |
| 25.10.1 and later 25.10.x | deprecated; **every REST call raises a deprecation alert on the appliance**. Current stable (25.10.4) still serves REST. |
| **26** (26-BETA.2 shipped 17 Jun 2026) | **REMOVED** — replaced by JSON-RPC 2.0 over a persistent WebSocket at `/api/current` |

So on a TrueNAS 26 appliance this tool does not work at all, and nothing in
`config.yaml` can change that. Stating that plainly: **`truenas-aiops` has no
path to managing TrueNAS 26 until it grows a WebSocket/JSON-RPC backend.** That
is a real piece of work, not a flag — new dependency, a persistent connection,
JSON-RPC framing, and a different auth flow (26 deprecates
`auth.login_with_api_key` in favour of `auth.login_ex`, and upgrading revokes API
keys that carry a method allow-list). It is tracked as a separate decision and is
**not** implemented here.

What *is* implemented is that the tool tells you where you stand instead of
failing obscurely:

- **`truenas-aiops doctor` reads the version** from `/system/info` and classifies
  it: supported → ✓, 25.10.1+ → a warning naming the 26 deadline, 26+ → a hard
  error and exit code 1.
- **Unknown degrades to UNKNOWN, not to OK.** A missing, empty, or unparseable
  version field produces a warning that says REST support could not be
  determined. It never prints a clean bill of health it cannot justify. (Version
  strings are parsed defensively: `25.10.4`, `26.0-BETA.2`,
  `TrueNAS-SCALE-24.04.2` and `TrueNAS-13.0-U6.1` all parse; anything else is
  UNKNOWN.)
- **The connection layer recognises the TrueNAS 26 failure shape.** REST being
  gone means *every* path 404s, so a 404 on an endpoint present on every
  REST-capable TrueNAS (`/system/info`, `/pool`, `/pool/dataset`, `/zfs/snapshot`,
  `/disk`, `/service`, `/alert/list`, `/replication`, `/cloudsync`,
  `/smart/test/results`) raises a dedicated `UnsupportedServerVersion` (a subclass
  of `TrueNASApiError`, so existing handlers keep working) explaining REST removal
  — rather than the ordinary "the id may be stale" 404 message, which would send
  an operator hunting a stale id that was never the problem. A 404 on a path with
  an id in it still gets the ordinary stale-id message.

**This part is mock-verified only, like the rest.** It is a unit-tested reading of
the published deprecation timeline; nobody has yet pointed this tool at a real
26-BETA appliance and watched the error appear. That is a checklist item below.

## What the mock suite guarantees

Every module imports; the CLI builds; every MCP tool carries the
`@governed_tool` harness marker; write tools record the correct inverse undo
descriptor against a mocked HTTP client; the RCA heuristics
(`pool_health_rca`, `alert_and_capacity_rca`) are unit-tested against synthetic
pool/dataset/alert telemetry, including ZFS-aware capacity thresholds.

## Prerequisites for a live run

A TrueNAS SCALE VM (or a spare appliance) with an API key, and a **throwaway
pool/dataset** you may snapshot and delete. Never verify destructive paths
against a pool holding real data.

```bash
uv tool install truenas-aiops
truenas-aiops init      # encrypted secret store, TLS verify on by default
truenas-aiops doctor
```

## Checklist

### 1. Connectivity
- [ ] `truenas-aiops doctor` → authenticates against the live REST endpoint.
- [ ] **Record the appliance version** `doctor` reports and confirm the verdict
      matches it: ≤ 25.10.0 clean, 25.10.1+ warns about the TrueNAS 26 removal,
      26+ is a hard error with exit code 1.
- [ ] On a 25.10.1+ appliance, confirm the **deprecation alerts actually appear**
      in the TrueNAS UI after this tool makes calls — that is the appliance-side
      cost of running on a deprecated transport, and operators should see it.
- [ ] Against a **TrueNAS 26** appliance (26-BETA or later), confirm the real
      failure mode is what we predict: 404s on the REST base path, surfaced as
      the `UnsupportedServerVersion` explanation rather than a stale-id 404. If
      TrueNAS 26 answers differently (e.g. a connection reset, a redirect, or a
      410 instead of a 404), the detection needs correcting — record what it
      actually does.

### 2. Every read endpoint actually resolves (the main risk)
- [ ] Walk each read command once and confirm **none** returns a 404/405 from a
      wrong path. Record any endpoint that differs from the modelled path.
- [ ] Pool / dataset / snapshot / disk / alert listings match the TrueNAS UI.
- [ ] `truenas-aiops diagnose pool-health` → against a pool you deliberately
      degrade (offline a disk in a test mirror), confirm DEGRADED is flagged and
      the error counters match `zpool status`.
- [ ] `truenas-aiops diagnose alerts` → active alerts and their levels match the
      UI; dataset capacity percentages match `zfs list`.

### 3. A reversible write + its undo
- [ ] Create a snapshot on the throwaway dataset; confirm the result carries an
      `_undo_id` and an audit row lands in the audit DB.
- [ ] `truenas-aiops undo apply <id>` → the inverse executes as recorded.
- [ ] `snapshot delete ... --dry-run` → previews only; the real delete is
      IRREVERSIBLE, captures BEFORE state, and correctly declares no undo.

### 4. Governance records every write
- [ ] A `high`-risk op (`snapshot_delete`) runs without any approver set and
      still lands an audit row tagged `risk_tier=review`; setting
      `TRUENAS_AUDIT_APPROVED_BY` only annotates that row — it does not gate.

### 5. Cleanup
- [ ] Destroy the throwaway dataset/pool; confirm the destroy is audited.

## Criteria to claim live verification

Every box ticked against a recorded TrueNAS SCALE version, **every modelled
endpoint path confirmed or corrected** and covered by a test, and the result
written up with the date and version. Until the endpoint paths are confirmed,
the "modelled, not confirmed" caveat must stay in the README and SKILL.
