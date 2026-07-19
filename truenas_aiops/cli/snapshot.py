"""``truenas-aiops snapshot ...`` sub-commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from mcp_server.tools import snapshots as gov
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


LimitOption = Annotated[
    int, typer.Option("--limit", help="Max snapshot rows to return")
]


@snapshot_app.command("list")
@cli_errors
def snapshot_list(
    dataset: DatasetOption = None,
    limit: LimitOption = snapshots.DEFAULT_SNAPSHOT_LIMIT,
    target: TargetOption = None,
) -> None:
    """List ZFS snapshots, optionally filtered to one dataset."""
    conn, _ = get_connection(target)
    result = snapshots.list_snapshots(conn, dataset, limit)
    console.print_json(json.dumps(result))
    if result["truncated"]:
        console.print(
            f"[yellow]Showing {result['returned']} of more — truncated, "
            f"re-run with a higher --limit.[/]"
        )


@snapshot_app.command("create")
@cli_errors
def snapshot_create(dataset: str, name: str, target: TargetOption = None) -> None:
    """Create a ZFS snapshot 'dataset@name'."""
    gov.snapshot_create(dataset=dataset, name=name, target=target)
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
    gov.snapshot_delete(snapshot_id=snapshot_id, target=target)
    console.print(f"[green]Deleted snapshot {snapshot_id}[/]")
