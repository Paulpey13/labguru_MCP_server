"""End-to-end CMR (Chemical Material Registry) reporting.

Reproduces the core CMR_dashboard workflow as a single tool: identify which
experiments in an ID range used CMR-flagged inventory products, done server-side
with parallel fetching and caching rather than dozens of chained calls.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..app import client, tool
from ..errors import LabguruError
from ..formatting import iter_experiment_rows, slim_experiment
from .inventory import collect_cmr_items

API = "/api/v1"

_MAX_RANGE = 1000


@tool()
async def cmr_experiment_report(
    start_id: int, end_id: int, collections: Optional[str] = None
) -> Dict[str, Any]:
    """Find experiments in an ID range that used CMR-flagged products.

    Builds a CMR sys_id lookup from inventory, fetches the experiments in
    parallel, and cross-references each experiment's sample rows against the
    lookup. This is the CMR_dashboard workflow in one call.

    Args:
        start_id: First experiment ID (inclusive).
        end_id: Last experiment ID (inclusive). Keep the range under ~1000.
        collections: Comma-separated inventory slugs to source CMR products from.
            Defaults to the configured CMR map (biochemistry, culture, sp_bioch).

    Returns a summary with: scanned, with_cmr, and rows (experiment_id, title,
    date, owner, cmr_products with their type_of_risk).
    """
    if end_id < start_id:
        raise LabguruError("end_id must be >= start_id.")
    if end_id - start_id > _MAX_RANGE:
        raise LabguruError(f"Range too large (max {_MAX_RANGE} IDs). Narrow the range.")

    cmr_items = await collect_cmr_items(collections)
    lookup: Dict[str, Dict[str, Any]] = {}
    for it in cmr_items:
        sid = (it.get("sys_id") or "").strip().lower()
        if sid:
            lookup[sid] = it

    async def _one(eid: int) -> Optional[Dict[str, Any]]:
        try:
            return await client.get(f"{API}/experiments/{eid}.json")
        except LabguruError:
            return None

    experiments = await client.gather(
        [_one(eid) for eid in range(start_id, end_id + 1)]
    )

    rows: List[Dict[str, Any]] = []
    scanned = 0
    for exp in experiments:
        if not isinstance(exp, dict) or not exp.get("id"):
            continue
        scanned += 1
        used: Dict[str, Dict[str, Any]] = {}
        for item in iter_experiment_rows(exp):
            sid = (item.get("sys_id") or item.get("auto_name") or "").strip().lower()
            if sid in lookup:
                used[sid] = lookup[sid]
        if used:
            summary = slim_experiment(exp)
            rows.append(
                {
                    "experiment_id": summary["id"],
                    "title": summary["title"],
                    "date": summary["start_date"],
                    "owner": summary["owner"],
                    "cmr_products": [
                        {
                            "name": p["name"],
                            "sys_id": p["sys_id"],
                            "type_of_risk": p.get("type_of_risk", ""),
                        }
                        for p in used.values()
                    ],
                }
            )

    rows.sort(key=lambda r: r["experiment_id"] or 0)
    return {
        "scanned": scanned,
        "with_cmr": len(rows),
        "cmr_products_known": len(lookup),
        "rows": rows,
    }
