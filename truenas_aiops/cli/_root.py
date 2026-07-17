"""Top-level Typer app: assembles sub-apps and top-level commands."""

from __future__ import annotations

import typer

from truenas_aiops.cli._common import cli_errors
from truenas_aiops.cli.alert import alert_app
from truenas_aiops.cli.dataset import dataset_app
from truenas_aiops.cli.disk import disk_app
from truenas_aiops.cli.doctor import doctor_cmd
from truenas_aiops.cli.init import init_cmd
from truenas_aiops.cli.overview import overview_cmd
from truenas_aiops.cli.pool import pool_app
from truenas_aiops.cli.replication import replication_app
from truenas_aiops.cli.secret import secret_app
from truenas_aiops.cli.service import service_app
from truenas_aiops.cli.snapshot import snapshot_app
from truenas_aiops.cli.system import system_cmd
from truenas_aiops.cli.undo import undo_app

app = typer.Typer(
    name="truenas-aiops",
    help="TrueNAS SCALE AI-powered storage operations.",
    no_args_is_help=True,
)

app.add_typer(pool_app, name="pool")
app.add_typer(dataset_app, name="dataset")
app.add_typer(snapshot_app, name="snapshot")
app.add_typer(disk_app, name="disk")
app.add_typer(alert_app, name="alert")
app.add_typer(service_app, name="service")
app.add_typer(replication_app, name="replication")
app.add_typer(secret_app, name="secret")
app.add_typer(undo_app, name="undo")
app.command("init")(init_cmd)
app.command("overview")(overview_cmd)
app.command("system")(system_cmd)
app.command("doctor")(doctor_cmd)


@app.command("mcp")
@cli_errors
def mcp_cmd() -> None:
    """Start the MCP server (stdio transport).

    Single-command entry point for MCP clients (does not go through uvx/PyPI
    resolution at launch):
        truenas-aiops mcp
    """
    import sys

    if sys.version_info < (3, 11):
        typer.echo(
            f"ERROR: truenas-aiops requires Python >= 3.11 "
            f"(got {sys.version_info.major}.{sys.version_info.minor}).\n"
            f"Fix: uv python install 3.12 && "
            f"uv tool install --python 3.12 --force truenas-aiops",
            err=True,
        )
        raise typer.Exit(2)

    from mcp_server.server import main as _mcp_main

    _mcp_main()


if __name__ == "__main__":
    app()
