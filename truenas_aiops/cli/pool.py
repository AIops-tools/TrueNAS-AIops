"""``truenas-aiops pool ...`` sub-commands."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from truenas_aiops.cli._common import (
    TargetOption,
    cli_errors,
    console,
    get_connection,
)
from truenas_aiops.ops import pools

pool_app = typer.Typer(help="ZFS pool operations.", no_args_is_help=True)
_console = Console()


@pool_app.command("list")
@cli_errors
def pool_list(target: TargetOption = None) -> None:
    """List ZFS pools (id, name, status, healthy, free)."""
    conn, _ = get_connection(target)
    rows = pools.list_pools(conn)
    table = Table(title="TrueNAS ZFS Pools")
    for col in ("id", "name", "status", "healthy", "free"):
        table.add_column(col)
    for r in rows:
        table.add_row(str(r["id"]), r["name"], r["status"], str(r["healthy"]), str(r["free"]))
    _console.print(table)


@pool_app.command("get")
@cli_errors
def pool_get(pool_id: str, target: TargetOption = None) -> None:
    """Show detail for one pool."""
    conn, _ = get_connection(target)
    for k, v in pools.get_pool(conn, pool_id).items():
        console.print(f"  [cyan]{k}:[/] {v}")


@pool_app.command("status")
@cli_errors
def pool_status(pool_id: str, target: TargetOption = None) -> None:
    """Show health and scan/topology status for one pool."""
    conn, _ = get_connection(target)
    console.print_json(json.dumps(pools.pool_status(conn, pool_id)))


@pool_app.command("scrub-status")
@cli_errors
def pool_scrub_status(pool_id: str, target: TargetOption = None) -> None:
    """Show the current scrub scan state for a pool."""
    conn, _ = get_connection(target)
    console.print_json(json.dumps(pools.scrub_status(conn, pool_id)))


@pool_app.command("capacity")
@cli_errors
def pool_capacity(target: TargetOption = None) -> None:
    """Capacity summary per pool (size/allocated/free/used%)."""
    conn, _ = get_connection(target)
    console.print_json(json.dumps(pools.pool_capacity(conn)))


@pool_app.command("scrub-start")
@cli_errors
def pool_scrub_start(pool_name: str, target: TargetOption = None) -> None:
    """Start a scrub (integrity check) on a pool."""
    conn, _ = get_connection(target)
    pools.scrub_start(conn, pool_name)
    console.print(f"[green]Started scrub on pool '{pool_name}'[/] (poll with 'pool scrub-status')")
