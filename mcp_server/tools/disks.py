"""Disk and S.M.A.R.T. MCP tools (read-only)."""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from truenas_aiops.governance import governed_tool
from truenas_aiops.ops import disks as ops


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def disk_list(target: Optional[str] = None) -> list:
    """[READ] List physical disks with name, serial, model, size, pool.

    Args:
        target: TrueNAS target name from config; omit to use the default.
    """
    return ops.list_disks(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def smart_test_results(target: Optional[str] = None) -> list:
    """[READ] Recent S.M.A.R.T. self-test results per disk (status/description).

    Args:
        target: TrueNAS target name from config.
    """
    return ops.smart_test_results(_get_connection(target))
