"""``truenas-aiops snapshot ...`` sub-commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from truenas_aiops.cli._common import (
    DryRunOption,
    TargetOption,
    cli_errors,
    console,
    double_confirm,
    dry_run_print,
    get_connection,
)
from truenas_aiops.ops import snapshots

snapshot_app = typer.Typer(help="ZFS snapshot operations.", no_args_is_help=True)
_console = Console()

DatasetOption = Annotated[
    str | None, typer.Option("--dataset", "-d", help="Filter to one dataset")
]


@snapshot_app.command("list")
@cli_errors
def snapshot_list(dataset: DatasetOption = None, target: TargetOption = None) -> None:
    """List ZFS snapshots, optionally filtered to one dataset."""
    conn, _ = get_connection(target)
    console.print_json(json.dumps(snapshots.list_snapshots(conn, dataset)))


@snapshot_app.command("create")
@cli_errors
def snapshot_create(dataset: str, name: str, target: TargetOption = None) -> None:
    """Create a ZFS snapshot 'dataset@name'."""
    conn, _ = get_connection(target)
    snapshots.create_snapshot(conn, dataset, name)
    console.print(f"[green]Created snapshot {dataset}@{name}[/]")


@snapshot_app.command("delete")
@cli_errors
def snapshot_delete(
    snapshot_id: str, target: TargetOption = None, dry_run: DryRunOption = False
) -> None:
    """Delete a ZFS snapshot by id 'dataset@name' (IRREVERSIBLE — double confirm)."""
    if dry_run:
        dry_run_print(
            operation="delete_snapshot",
            api_call=f"DELETE /zfs/snapshot/id/{snapshot_id}",
        )
        return
    double_confirm("delete", f"snapshot {snapshot_id}")
    conn, _ = get_connection(target)
    snapshots.delete_snapshot(conn, snapshot_id)
    console.print(f"[green]Deleted snapshot {snapshot_id}[/]")
