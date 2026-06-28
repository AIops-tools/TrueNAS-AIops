"""``truenas-aiops system`` — system information summary."""

from __future__ import annotations

import json

from truenas_aiops.cli._common import TargetOption, cli_errors, console, get_connection
from truenas_aiops.ops import system


@cli_errors
def system_cmd(target: TargetOption = None) -> None:
    """Show TrueNAS system info (version, hostname, memory, uptime)."""
    conn, _ = get_connection(target)
    console.print_json(json.dumps(system.system_info(conn)))
