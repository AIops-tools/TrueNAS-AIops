"""Environment and connectivity diagnostics for TrueNAS AIops."""

from __future__ import annotations

from rich.console import Console

from truenas_aiops.config import CONFIG_FILE, ENV_FILE, load_config
from truenas_aiops.secretstore import SECRETS_FILE, check_permissions, has_store
from truenas_aiops.version_support import DEPRECATED, REMOVED, UNKNOWN, check_rest_support

_console = Console()


def _report_rest_support(raw_version: object) -> int:
    """Print the REST-transport verdict for one target; return problems to add.

    ``removed`` is a hard failure (this tool cannot talk to the server at all).
    ``deprecated`` and ``unknown`` are warnings: the tool works today, but the
    operator needs to know it is on a clock — or that we could not tell.
    """
    support = check_rest_support(raw_version if isinstance(raw_version, str) else None)
    if support.status == REMOVED:
        _console.print(f"[red]✗ {support.message}[/]")
        return 1
    if support.status in (DEPRECATED, UNKNOWN):
        _console.print(f"[yellow]! {support.message}[/]")
        return 0
    _console.print(f"[green]✓ {support.message}[/]")
    return 0


def run_doctor(skip_auth: bool = False) -> int:
    """Check config, secrets, and (optionally) connectivity + REST support.

    Returns a process exit code: 0 healthy, 1 problems found. Connectivity
    failures are reported as status, never raised as tracebacks (a doctor must
    survive the thing it diagnoses being unhealthy). The connectivity step also
    reads the server version and reports whether this server still serves the
    REST API this tool is built on — see :mod:`truenas_aiops.version_support`.
    """
    problems = 0

    if not CONFIG_FILE.exists():
        _console.print(f"[red]✗ Config file missing: {CONFIG_FILE}[/]")
        _console.print("[yellow]  Run 'truenas-aiops init' to set up your first target.[/]")
        return 1
    _console.print(f"[green]✓ Config file present: {CONFIG_FILE}[/]")

    try:
        config = load_config()
    except Exception as exc:  # noqa: BLE001 — report, do not crash
        _console.print(f"[red]✗ Config load failed: {exc}[/]")
        return 1

    if not config.targets:
        _console.print("[red]✗ No targets configured[/]")
        return 1
    _console.print(f"[green]✓ {len(config.targets)} target(s) configured[/]")

    if has_store():
        _console.print(f"[green]✓ Encrypted secret store present: {SECRETS_FILE}[/]")
        perm_warning = check_permissions()
        if perm_warning:
            _console.print(f"[yellow]! {perm_warning}[/]")
    elif ENV_FILE.exists():
        _console.print(
            f"[yellow]! Using legacy plaintext .env ({ENV_FILE}). Migrate with "
            f"'truenas-aiops secret migrate'.[/]"
        )
    else:
        _console.print(
            "[yellow]! No secret store yet. Run 'truenas-aiops init' to set up "
            "credentials (stored encrypted).[/]"
        )
        problems += 1

    for target in config.targets:
        try:
            _ = target.api_key
            _console.print(f"[green]✓ API key present for '{target.name}'[/]")
        except OSError as exc:
            _console.print(f"[red]✗ {exc}[/]")
            problems += 1

    if skip_auth:
        _console.print("[dim]Skipping connectivity check (--skip-auth).[/]")
        return 1 if problems else 0

    from truenas_aiops.connection import ConnectionManager

    mgr = ConnectionManager(config)
    for target in config.targets:
        try:
            conn = mgr.connect(target.name)
            info = conn.get("/system/info")
            raw_version = info.get("version") if isinstance(info, dict) else None
            _console.print(
                f"[green]✓ Connected to '{target.name}' ({target.host}) "
                f"— TrueNAS {raw_version or '?'}[/]"
            )
            problems += _report_rest_support(raw_version)
        except Exception as exc:  # noqa: BLE001 — connectivity is a status, not a crash
            _console.print(f"[red]✗ Connect to '{target.name}' failed: {exc}[/]")
            problems += 1

    return 1 if problems else 0
