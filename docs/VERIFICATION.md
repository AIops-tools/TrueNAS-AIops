# Live verification status

This document records what has and has not been validated against a real
TrueNAS SCALE appliance, so the maturity claim is auditable.

## Current status ⚠️ mock-only — endpoint paths are modelled, not confirmed

`truenas-aiops` has **not** been validated against a live TrueNAS SCALE
appliance. Beyond the usual mock-only caveat there is a specific, substantive
risk worth stating plainly:

> The REST endpoint paths are **modelled against the documented TrueNAS SCALE
> REST v2.0 API**, not confirmed against a running appliance. A path or field
> name that differs on your build will surface as an error, not as silent
> wrong data — but it will surface.

This is the single highest-value thing a community tester can fix, and it is
cheap to test: TrueNAS SCALE runs fine as a VM.

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

### 4. Governance actually gates
- [ ] With no `rules.yaml`, a `high`-risk op is refused unless
      `TRUENAS_AUDIT_APPROVED_BY` names an approver (secure-by-default).

### 5. Cleanup
- [ ] Destroy the throwaway dataset/pool; confirm the destroy is audited.

## Criteria to claim live verification

Every box ticked against a recorded TrueNAS SCALE version, **every modelled
endpoint path confirmed or corrected** and covered by a test, and the result
written up with the date and version. Until the endpoint paths are confirmed,
the "modelled, not confirmed" caveat must stay in the README and SKILL.
