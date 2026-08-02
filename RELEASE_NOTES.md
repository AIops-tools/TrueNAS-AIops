# Release notes — truenas-aiops 0.8.0

Previous release: 0.7.0.

## Replication state came from the wrong record

The replication surface had only ever been read on appliances with **zero
tasks** — an empty list, which proves nothing. This release follows a round
against real ones: a TrueNAS SCALE 25.04.2.1 → 26.0.0-BETA.2 replication over
SSH that actually transferred a snapshot, and a cloud-sync to a real MinIO S3
target that actually uploaded a file.

`list_replication` reported `job.state`. On a real appliance that is wrong twice
over:

| task | what the appliance reports | what the tool reported |
|---|---|---|
| ran successfully | `FINISHED` | `SUCCESS` |
| created, never run | `PENDING` | **`null`** |
| failed | `ERROR` + an `error` sentence | `FAILED`, sentence dropped |

`replication.query` injects a top-level `state` from the moment a task is
created. `job` is the generic job record: it does not exist until a run has been
triggered in the middleware's current lifetime, and when it does it speaks a
different vocabulary. So the common case — any task on a freshly booted
appliance — reported `null`, "unknown" for a state the appliance states plainly,
and **no value the tool ever produced matched what the appliance and its own UI
show**.

The `error` sentence is the diagnostic: *"Dataset 'tank/empty' does not have any
matching snapshots to replicate."* It was discarded entirely. Replication rows
now also carry `error`, `lastSnapshot` and `lastRun`.

## Cloud-sync is deliberately unchanged — it was already right

The obvious "fix both the same way" would have broken it. A `cloudsync` record
carries **no top-level state at all** — checked on the same appliance before and
after a run that reached `SUCCESS` — so its job record genuinely is the only
outcome signal. A regression test now pins the asymmetry, so a future "unify
these two" refactor fails loudly instead of silently reporting `null` for every
cloud-sync task.

Both `replication.query` and `cloudsync.query` keep their names on 25.04 **and**
26, checked against each appliance's own `core.get_methods` — unlike
`zfs.snapshot.*` → `pool.snapshot.*`, there is no rename to route around here.

## Upgrading

`replication_list`'s `state` values change from the job vocabulary
(`SUCCESS`/`FAILED`) to the replication one
(`PENDING`/`RUNNING`/`FINISHED`/`ERROR`/`HOLD`), and stop being `null` for tasks
that have not run. Anything matching on the old strings needs updating; anything
displaying them to a person now agrees with the appliance UI.
