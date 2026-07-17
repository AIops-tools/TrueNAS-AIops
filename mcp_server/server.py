"""MCP server wrapping TrueNAS AIops operations (stdio transport).

Thin adapter layer: each ``@mcp.tool()`` function (in ``mcp_server/tools/``)
delegates to the ``truenas_aiops`` ops package and is wrapped with the
truenas-aiops ``@governed_tool`` harness (audit / budget / undo / risk-tier).

Standalone, self-governed TrueNAS SCALE operations (preview).
For TrueNAS SCALE only.

Source: https://github.com/AIops-tools/TrueNAS-AIops
License: MIT
"""

import logging

from mcp_server._shared import _safe_error, mcp, tool_errors

# Importing the tool modules registers every @mcp.tool() onto the shared
# `mcp` instance. Order does not matter; each module is self-contained.
from mcp_server.tools import (  # noqa: F401 — side effects
    alerts,
    datasets,
    disks,
    overview,
    pools,
    replication,
    services,
    snapshots,
    system,
    undo,
)

__all__ = ["mcp", "main", "_safe_error", "tool_errors"]


def main() -> None:
    """Run the MCP server over stdio."""
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="stdio")
