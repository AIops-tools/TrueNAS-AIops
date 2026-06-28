"""``truenas-aiops replication ...`` sub-commands."""

from __future__ import annotations

import json

import typer

from truenas_aiops.cli._common import TargetOption, cli_errors, console, get_connection
from truenas_aiops.ops import replication

replication_app = typer.Typer(
    help="Replication and cloud-sync operations.", no_args_is_help=True
)


@replication_app.command("list")
@cli_errors
def replication_list(target: TargetOption = None) -> None:
    """List replication tasks (name, direction, transport, state)."""
    conn, _ = get_connection(target)
    console.print_json(json.dumps(replication.list_replication(conn)))


@replication_app.command("cloudsync")
@cli_errors
def cloudsync_list(target: TargetOption = None) -> None:
    """List cloud-sync tasks (description, direction, path, state)."""
    conn, _ = get_connection(target)
    console.print_json(json.dumps(replication.list_cloudsync(conn)))
