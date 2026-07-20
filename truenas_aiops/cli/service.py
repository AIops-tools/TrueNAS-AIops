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
    dry_run_preview,
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
    # ``confirm=True`` on both branches: this command's confirmation gate is the
    # interactive double_confirm below, which the real path always runs. Previewing
    # with confirm=False would report an ssh refusal the real CLI call never hits —
    # the preview disagreeing with the call it previews.
    if dry_run:
        # Through the governed call: restart_service refuses unknown service
        # names, so a preview must report that refusal rather than a green banner.
        dry_run_preview(
            gov.service_restart(service=service, confirm=True, dry_run=True, target=target),
            operation="restart_service",
            api_call="POST /service/restart",
            parameters={"service": service},
        )
        return
    double_confirm("restart", f"service {service}")
    gov.service_restart(service=service, confirm=True, target=target)
    console.print(f"[green]Restarted service '{service}'[/]")
