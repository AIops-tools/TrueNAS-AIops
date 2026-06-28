"""Environment health overview MCP tool (read-only)."""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from truenas_aiops.governance import governed_tool
from truenas_aiops.ops import overview as ops


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def overview(target: Optional[str] = None) -> dict:
    """[READ] One-shot health summary: pools (capacity/health), alerts, services.

    Call this first to triage a TrueNAS system before drilling into a specific
    pool, dataset, or service.

    Args:
        target: TrueNAS target name from config; omit to use the default.
    """
    return ops.health_overview(_get_connection(target))
