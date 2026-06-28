"""``truenas-aiops disk ...`` sub-commands."""

from __future__ import annotations

import json

import typer

from truenas_aiops.cli._common import TargetOption, cli_errors, console, get_connection
from truenas_aiops.ops import disks

disk_app = typer.Typer(help="Disk and S.M.A.R.T. operations.", no_args_is_help=True)


@disk_app.command("list")
@cli_errors
def disk_list(target: TargetOption = None) -> None:
    """List physical disks (name, serial, model, size, pool)."""
    conn, _ = get_connection(target)
    console.print_json(json.dumps(disks.list_disks(conn)))


@disk_app.command("smart")
@cli_errors
def disk_smart(target: TargetOption = None) -> None:
    """Show recent S.M.A.R.T. self-test results per disk."""
    conn, _ = get_connection(target)
    console.print_json(json.dumps(disks.smart_test_results(conn)))
