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
def service_restart(service: str, target: Optional[str] = None) -> dict:
    """[WRITE] Restart a system service (e.g. 'smb', 'nfs', 'ssh').

    Captures the prior service state for the audit record; declares no undo
    (a restart is not cleanly reversible).

    Args:
        service: TrueNAS service name (see service_list).
        target: TrueNAS target name from config.
    """
    return ops.restart_service(_get_connection(target), service)
