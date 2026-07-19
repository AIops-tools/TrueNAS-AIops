"""Diagnostics / RCA MCP tools: pool health and alert-and-capacity.

Read-only signature analyses (``risk_level="low"``). Each tool collects the
telemetry once and hands the already-fetched records to a pure analysis function
in ``truenas_aiops.ops.diagnostics`` — so the heuristics stay unit-testable
without a live NAS, and the collection stays here where the connection is.
"""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from truenas_aiops.governance import governed_tool
from truenas_aiops.ops import alerts as alert_ops
from truenas_aiops.ops import diagnostics as diag
from truenas_aiops.ops._util import as_list


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def pool_health_rca(target: Optional[str] = None) -> dict:
    """[READ] Flag ZFS pools by state, error counters, and capacity.

    Pulls the /pool listing (with topology + scan) and flags pools that are
    DEGRADED/FAULTED/OFFLINE, pools with non-zero read/write/checksum/scan error
    counters, and pools over the 80%/90% capacity thresholds — worst-first, each
    finding citing the measured status/counts/percent and a concrete action.

    Args:
        target: TrueNAS target name from config; omit to use the default.
    """
    conn = _get_connection(target)
    pools = as_list(conn.get("/pool"))
    return diag.pool_health_findings(pools)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def alert_and_capacity_rca(target: Optional[str] = None) -> dict:
    """[READ] Surface active TrueNAS alerts by level and datasets near full.

    Collects the active alert list and the /pool/dataset listing, then reports
    worst-first findings: one per active (non-dismissed) alert at WARNING+ and one
    per dataset whose usage is near its quota/available ceiling (80%/90%), each
    citing the measured level/percent.

    Args:
        target: TrueNAS target name from config; omit to use the default.
    """
    conn = _get_connection(target)
    alerts = alert_ops.list_alerts(conn)
    datasets = as_list(conn.get("/pool/dataset"))
    return diag.alert_capacity_findings(alerts, datasets)
