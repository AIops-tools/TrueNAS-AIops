"""ZFS dataset MCP tools: list/get + create."""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from truenas_aiops.governance import governed_tool
from truenas_aiops.ops import datasets as ops


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def dataset_list(target: Optional[str] = None) -> list:
    """[READ] List ZFS datasets with id, name, type, pool, used/available.

    Args:
        target: TrueNAS target name from config; omit to use the default.
    """
    return ops.list_datasets(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def dataset_get(dataset_id: str, target: Optional[str] = None) -> dict:
    """[READ] Return detail for a single dataset by id (e.g. 'tank/data').

    Args:
        dataset_id: TrueNAS dataset id (see dataset_list).
        target: TrueNAS target name from config.
    """
    return ops.get_dataset(_get_connection(target), dataset_id)


@mcp.tool()
@governed_tool(risk_level="medium")
@tool_errors("dict")
def dataset_create(
    name: str, pool: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[WRITE] Create a ZFS dataset. Non-destructive (creates new storage).

    No undo descriptor — dataset deletion is intentionally out of scope.

    Args:
        name: Full dataset path including the pool, e.g. 'tank/projects'.
        pool: Optional pool name for context/labelling.
        target: TrueNAS target name from config.
    """
    return ops.create_dataset(_get_connection(target), name, pool)
