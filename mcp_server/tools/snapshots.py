"""ZFS snapshot MCP tools: list + create (medium) + delete (high).

``snapshot_create`` passes an ``undo=`` lambda so the harness records an
inverse ``snapshot_delete`` descriptor. ``snapshot_delete`` is irreversible
(``risk_level=high``) and declares no undo.
"""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from truenas_aiops.governance import governed_tool
from truenas_aiops.ops import snapshots as ops


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def snapshot_list(dataset: Optional[str] = None, target: Optional[str] = None) -> list:
    """[READ] List ZFS snapshots, optionally filtered to one dataset.

    Args:
        dataset: Optional dataset path to filter (e.g. 'tank/data').
        target: TrueNAS target name from config.
    """
    return ops.list_snapshots(_get_connection(target), dataset)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "snapshot_delete",
        "params": {"snapshot_id": result.get("id")} if isinstance(result, dict) else {},
        "skill": "truenas-aiops",
        "note": "Inverse of snapshot_create: delete the just-created snapshot.",
    },
)
@tool_errors("dict")
def snapshot_create(dataset: str, name: str, target: Optional[str] = None) -> dict:
    """[WRITE] Create a ZFS snapshot 'dataset@name'. Inverse: snapshot_delete.

    Args:
        dataset: Dataset path to snapshot (e.g. 'tank/data').
        name: Snapshot name (e.g. 'manual-2026-06-28').
        target: TrueNAS target name from config.
    """
    return ops.create_snapshot(_get_connection(target), dataset, name)


@mcp.tool()
@governed_tool(risk_level="high")
@tool_errors("dict")
def snapshot_delete(snapshot_id: str, target: Optional[str] = None) -> dict:
    """[WRITE] Delete a ZFS snapshot by id ('dataset@name'). IRREVERSIBLE.

    Captures the snapshot's prior state for the audit record; declares no undo.

    Args:
        snapshot_id: Full snapshot id 'dataset@name' (see snapshot_list).
        target: TrueNAS target name from config.
    """
    return ops.delete_snapshot(_get_connection(target), snapshot_id)
