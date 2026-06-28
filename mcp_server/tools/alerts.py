"""Alert MCP tool (read-only)."""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from truenas_aiops.governance import governed_tool
from truenas_aiops.ops import alerts as ops


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def alert_list(target: Optional[str] = None) -> list:
    """[READ] List active TrueNAS alerts with level, message, class, dismissed.

    Args:
        target: TrueNAS target name from config; omit to use the default.
    """
    return ops.list_alerts(_get_connection(target))
