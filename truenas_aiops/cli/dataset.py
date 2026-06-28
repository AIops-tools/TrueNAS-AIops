"""``truenas-aiops dataset ...`` sub-commands."""

from __future__ import annotations

import json

import typer
from rich.console import Console

from truenas_aiops.cli._common import (
    DryRunOption,
    TargetOption,
    cli_errors,
    console,
    dry_run_print,
    get_connection,
)
from truenas_aiops.ops import datasets

dataset_app = typer.Typer(help="ZFS dataset operations.", no_args_is_help=True)
_console = Console()


@dataset_app.command("list")
@cli_errors
def dataset_list(target: TargetOption = None) -> None:
    """List ZFS datasets (id, name, type, used/available)."""
    conn, _ = get_connection(target)
    console.print_json(json.dumps(datasets.list_datasets(conn)))


@dataset_app.command("get")
@cli_errors
def dataset_get(dataset_id: str, target: TargetOption = None) -> None:
    """Show detail for one dataset (e.g. 'tank/data')."""
    conn, _ = get_connection(target)
    for k, v in datasets.get_dataset(conn, dataset_id).items():
        console.print(f"  [cyan]{k}:[/] {v}")


@dataset_app.command("create")
@cli_errors
def dataset_create(
    name: str, target: TargetOption = None, dry_run: DryRunOption = False
) -> None:
    """Create a ZFS dataset (full path, e.g. 'tank/projects')."""
    if dry_run:
        dry_run_print(
            operation="create_dataset",
            api_call="POST /pool/dataset",
            parameters={"name": name},
        )
        return
    conn, _ = get_connection(target)
    datasets.create_dataset(conn, name)
    console.print(f"[green]Created dataset '{name}'[/]")
