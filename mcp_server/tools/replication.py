"""Replication and cloud-sync MCP tools (read-only)."""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from truenas_aiops.governance import governed_tool
from truenas_aiops.ops import replication as ops


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def replication_list(target: Optional[str] = None) -> list:
    """[READ] List replication tasks with name, direction, transport, state.

    Args:
        target: TrueNAS target name from config; omit to use the default.
    """
    return ops.list_replication(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def cloudsync_list(target: Optional[str] = None) -> list:
    """[READ] List cloud-sync tasks with description, direction, path, state.

    Args:
        target: TrueNAS target name from config.
    """
    return ops.list_cloudsync(_get_connection(target))
