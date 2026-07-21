# Security Policy

## Disclaimer

Community-maintained open-source project. **Not affiliated with, endorsed by, or
sponsored by iXsystems or the TrueNAS project.** "TrueNAS" is a trademark of its
owner. Source is publicly auditable under the MIT license.

## Reporting Vulnerabilities

Report privately via a GitHub Security Advisory on
[github.com/AIops-tools/TrueNAS-AIops](https://github.com/AIops-tools/TrueNAS-AIops/security/advisories)
or email zhouwei008@gmail.com. Please do not open public issues for security
reports.

## Security Design

### Credential Management
- Per-target TrueNAS API keys live **encrypted** in
  `~/.truenas-aiops/secrets.enc` (Fernet/AES-128 + scrypt-derived key; chmod
  600), never in `config.yaml` and never in source. The master password is
  never stored — only a per-store random salt and the ciphertext are on disk.
- A legacy plaintext env var `TRUENAS_<TARGET_NAME_UPPER>_APIKEY` is still
  honoured as a fallback with a deprecation warning (migrate with
  `truenas-aiops secret migrate`).
- The API key is sent as an `Authorization: Bearer` header at request time and
  held only in memory. Keys are never logged or echoed; the config file holds
  only host, port, api_path, and TLS settings.

### Governed Operations
Every MCP tool runs through the bundled `@governed_tool` harness
(`truenas_aiops.governance`):
- **Audit** — every call logged to a local SQLite DB under `~/.truenas-aiops/`
  (relocatable via `TRUENAS_AIOPS_HOME`), agent-attributed, secret-redacted.
- **Token/runaway budget** — hard ceilings (`TRUENAS_MAX_TOOL_CALLS` /
  `TRUENAS_MAX_TOOL_SECONDS`) plus an on-by-default guard that trips a tight
  poll/retry loop, preventing unbounded API consumption (e.g. polling a slow
  session).
- **Risk tier** — a descriptive label on each audit row derived from
  `risk_level`; it gates nothing. `TRUENAS_AUDIT_APPROVED_BY` /
  `TRUENAS_AUDIT_RATIONALE` are optional annotations recorded on the row, never
  required and never blocking.
- **Undo-token recording** — `snapshot_create` records an inverse
  `snapshot_delete` descriptor so the change can be rolled back.

### Destructive Operations
`snapshot delete` and `service restart` require double confirmation at the CLI
layer and support `--dry-run`. The snapshot delete is irreversible (data loss),
tagged `risk_level=high`, captures the snapshot's BEFORE state for the audit
record, and records no undo token.

### SSL/TLS Verification
`verify_ssl` defaults to true; disable only for self-signed lab certificates.

### Prompt-Injection Protection
All TrueNAS-API-returned text (pool/dataset names, alert messages, descriptions)
is passed through a `sanitize()` truncate + control-character strip before
reaching the agent.

### Network Scope
No webhooks, no telemetry, no outbound calls beyond the configured TrueNAS SCALE
REST API endpoint. No post-install scripts or background services.

## Static Analysis

```bash
uvx bandit -r truenas_aiops/ mcp_server/
uv run ruff check .
```

## Supported Versions

The latest released version receives security fixes. This is a preview (0.x);
pin a version in production.
