"""System info MCP tool (read-only)."""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from truenas_aiops.governance import governed_tool
from truenas_aiops.ops import system as ops


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def system_info(target: Optional[str] = None) -> dict:
    """[READ] TrueNAS system summary: version, hostname, memory, cores, uptime.

    Args:
        target: TrueNAS target name from config; omit to use the default.
    """
    return ops.system_info(_get_connection(target))
