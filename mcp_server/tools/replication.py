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

    ``state`` is the replication task's own state — PENDING / RUNNING /
    FINISHED / ERROR / HOLD, matching what the appliance UI shows — and is
    never absent, PENDING being what a task reports before its first run. An
    ERROR row carries the appliance's ``error`` sentence naming what to fix.
    Also returns ``lastSnapshot`` and ``lastRun`` (epoch milliseconds).

    Args:
        target: TrueNAS target name from config; omit to use the default.
    """
    return ops.list_replication(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def cloudsync_list(target: Optional[str] = None) -> list:
    """[READ] List cloud-sync tasks with description, direction, path, state.

    ``state`` here is the last run's job state (SUCCESS / FAILED / RUNNING) and
    is null until the task has run — cloud-sync records, unlike replication
    ones, carry no state of their own.

    Args:
        target: TrueNAS target name from config.
    """
    return ops.list_cloudsync(_get_connection(target))
