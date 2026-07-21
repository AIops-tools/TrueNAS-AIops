"""ZFS pool MCP tools: list/get/status/scrub-status/capacity + scrub start.

Every tool is wrapped with ``@governed_tool`` (the truenas-aiops harness):
budget/runaway guard, descriptive risk-tier tagging, audit logging to
~/.truenas-aiops/audit.db, and undo-token recording.
"""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from truenas_aiops.governance import governed_tool
from truenas_aiops.ops import pools as ops


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def pool_list(target: Optional[str] = None) -> list:
    """[READ] List ZFS pools with id, name, status, health, capacity.

    Args:
        target: TrueNAS target name from config; omit to use the default.
    """
    return ops.list_pools(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def pool_get(pool_id: str, target: Optional[str] = None) -> dict:
    """[READ] Return detail for a single pool by id.

    Args:
        pool_id: TrueNAS pool id (see pool_list).
        target: TrueNAS target name from config.
    """
    return ops.get_pool(_get_connection(target), pool_id)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def pool_status(pool_id: str, target: Optional[str] = None) -> dict:
    """[READ] Health and scan/topology status of a single pool.

    Args:
        pool_id: TrueNAS pool id.
        target: TrueNAS target name from config.
    """
    return ops.pool_status(_get_connection(target), pool_id)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def scrub_status(pool_id: str, target: Optional[str] = None) -> dict:
    """[READ] Current scrub scan state (function/state/percentage) for a pool.

    Args:
        pool_id: TrueNAS pool id.
        target: TrueNAS target name from config.
    """
    return ops.scrub_status(_get_connection(target), pool_id)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def pool_capacity(target: Optional[str] = None) -> list:
    """[READ] Capacity summary per pool: size/allocated/free and used percent.

    Args:
        target: TrueNAS target name from config.
    """
    return ops.pool_capacity(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="medium")
@tool_errors("dict")
def pool_scrub_start(
    pool_name: str,
    dry_run: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Start a scrub (integrity check) on a pool. Non-destructive.
    Pass dry_run=True to preview.

    No undo descriptor (a scrub has no clean inverse beyond cancellation). Poll
    progress with scrub_status; do not re-issue.

    Args:
        pool_name: ZFS pool name (e.g. 'tank').
        dry_run: If True, preview without starting the scrub.
        target: TrueNAS target name from config.
    """
    if dry_run:
        return {"dryRun": True, "wouldStartScrub": {"poolName": pool_name}}
    return ops.scrub_start(_get_connection(target), pool_name)
