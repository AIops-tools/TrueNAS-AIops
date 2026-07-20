"""System service MCP tools: list + restart (medium)."""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from truenas_aiops.governance import governed_tool
from truenas_aiops.ops import services as ops


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def service_list(target: Optional[str] = None) -> list:
    """[READ] List system services with name, state (RUNNING/STOPPED), enable.

    Args:
        target: TrueNAS target name from config; omit to use the default.
    """
    return ops.list_services(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="medium")
@tool_errors("dict")
def service_restart(
    service: str,
    confirm: bool = False,
    dry_run: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Restart a system service (e.g. 'smb', 'nfs'). Pass dry_run=True
    to preview.

    Captures the prior service state for the audit record; declares no undo
    (a restart is not cleanly reversible).

    Refuses a service name that is not present in service_list, and refuses
    'ssh' unless confirm=True — SSH is the out-of-band recovery path, and
    bouncing it can strand whoever is working over it. Both refusals apply
    under dry_run too, which must report a refusal rather than preview a call
    that will be refused.

    Args:
        service: TrueNAS service name (see service_list).
        confirm: Required (True) only to restart 'ssh'; ignored otherwise.
        dry_run: If True, preview without restarting.
        target: TrueNAS target name from config.
    """
    conn = _get_connection(target)
    # Ahead of the dry_run return: a preview whose real call would be refused
    # must say so, or the caller reads the refusal as transient and retries.
    ops.guard_restart_service(conn, service, confirm=confirm)
    if dry_run:
        return {"dryRun": True, "wouldRestart": {"service": service}}
    return ops.restart_service(conn, service, confirm=confirm)
