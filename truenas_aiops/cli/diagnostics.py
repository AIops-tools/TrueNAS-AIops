"""``truenas-aiops diagnose ...`` sub-commands — read-only RCA over the NAS."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from truenas_aiops.cli._common import TargetOption, cli_errors, get_connection
from truenas_aiops.ops import alerts as alert_ops
from truenas_aiops.ops import diagnostics as diag
from truenas_aiops.ops._util import as_list

diagnose_app = typer.Typer(
    help="Read-only diagnostics / RCA over the TrueNAS appliance.",
    no_args_is_help=True,
)
console = Console()

_SEVERITY_STYLE = {"critical": "red", "warning": "yellow", "info": "cyan"}


def _print_findings(findings: list[dict]) -> None:
    """Render worst-first findings as a table, or a green all-clear line."""
    if not findings:
        console.print(
            "[green]No findings — all measured values under threshold.[/]"
        )
        return
    table = Table(title="Findings (worst first)")
    for col in ("severity", "resource", "signal", "detail", "action"):
        table.add_column(col, overflow="fold")
    for f in findings:
        style = _SEVERITY_STYLE.get(f["severity"], "white")
        table.add_row(
            f"[{style}]{f['severity']}[/]", f.get("resource", ""),
            f["signal"], f["detail"], f["action"],
        )
    console.print(table)


@diagnose_app.command("pool-health")
@cli_errors
def diagnose_pool_health(target: TargetOption = None) -> None:
    """Flag pools by ZFS state, error counters, and capacity (worst first)."""
    conn, _ = get_connection(target)
    pools = as_list(conn.get("/pool"))
    result = diag.pool_health_findings(pools)
    console.print(f"[bold]Analyzed {result['poolsAnalyzed']} pool(s).[/]")
    _print_findings(result["findings"])


@diagnose_app.command("alerts")
@cli_errors
def diagnose_alerts(target: TargetOption = None) -> None:
    """Surface active alerts by level and datasets near their capacity ceiling."""
    conn, _ = get_connection(target)
    alerts = alert_ops.list_alerts(conn)
    datasets = as_list(conn.get("/pool/dataset"))
    result = diag.alert_capacity_findings(alerts, datasets)
    console.print(
        f"[bold]Analyzed {result['alertsAnalyzed']} alert(s), "
        f"{result['datasetsAnalyzed']} dataset(s).[/]"
    )
    if result["alertLevels"]:
        levels = ", ".join(f"{k}={v}" for k, v in result["alertLevels"].items())
        console.print(f"[dim]Alert levels: {levels}[/]")
    _print_findings(result["findings"])
