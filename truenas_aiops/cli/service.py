"""``truenas-aiops service ...`` sub-commands."""

from __future__ import annotations

import json

import typer

from mcp_server.tools import services as gov
from truenas_aiops.cli._common import (
    DryRunOption,
    TargetOption,
    cli_errors,
    console,
    double_confirm,
    dry_run_print,
    get_connection,
)
from truenas_aiops.ops import services

service_app = typer.Typer(help="System service operations.", no_args_is_help=True)


@service_app.command("list")
@cli_errors
def service_list(target: TargetOption = None) -> None:
    """List system services (name, state, enable)."""
    conn, _ = get_connection(target)
    console.print_json(json.dumps(services.list_services(conn)))


@service_app.command("restart")
@cli_errors
def service_restart(
    service: str, target: TargetOption = None, dry_run: DryRunOption = False
) -> None:
    """Restart a system service (e.g. 'smb', 'nfs', 'ssh') — double confirm."""
    if dry_run:
        dry_run_print(
            operation="restart_service",
            api_call="POST /service/restart",
            parameters={"service": service},
        )
        return
    double_confirm("restart", f"service {service}")
    gov.service_restart(service=service, target=target)
    console.print(f"[green]Restarted service '{service}'[/]")
