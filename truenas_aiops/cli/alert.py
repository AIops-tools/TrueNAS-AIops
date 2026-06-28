"""``truenas-aiops alert ...`` sub-commands."""

from __future__ import annotations

import json

import typer

from truenas_aiops.cli._common import TargetOption, cli_errors, console, get_connection
from truenas_aiops.ops import alerts

alert_app = typer.Typer(help="Alert operations.", no_args_is_help=True)


@alert_app.command("list")
@cli_errors
def alert_list(target: TargetOption = None) -> None:
    """List active TrueNAS alerts (level, message, class, dismissed)."""
    conn, _ = get_connection(target)
    console.print_json(json.dumps(alerts.list_alerts(conn)))
