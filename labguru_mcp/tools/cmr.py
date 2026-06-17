"""End-to-end CMR (Chemical Material Registry) reporting.

Reproduces the core CMR_dashboard workflow as a single tool: identify which
experiments in an ID range used CMR-flagged inventory products.

Sample tables are not embedded in the experiment detail JSON; each ``samples``
element must be fetched via /api/v1/elements/{id}.json, whose ``data`` field is
a JSON string holding the table. Sample sys_ids live in the ``auto_name``
attribute. This tool fans those fetches out with bounded concurrency.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Dict, List, Optional

from ..app import client, tool
from ..errors import LabguruError
from ..formatting import collect_values, slim_experiment
from .inventory import collect_cmr_items

API = "/api/v1"

_MAX_RANGE = 1000


async def _element_sysids(element_id: int) -> set:
    """Return the lowercased sample sys_ids referenced by a samples element."""
    try:
        el = await client.get(f"{API}/elements/{element_id}.json")
    except LabguruError:
        return set()
    data = el.get("data") if isinstance(el, dict) else None
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return set()
    if not isinstance(data, (dict, list)):
        return set()
    return {s.lower() for s in collect_values(data, "auto_name")}


def _samples_element_ids(exp: Dict[str, Any]) -> List[int]:
    ids: List[int] = []
    for wrapper in exp.get("experiment_procedures") or []:
        proc = wrapper.get("experiment_procedure", wrapper)
        for el in proc.get("elements") or []:
            if el.get("element_type") == "samples" and el.get("id"):
                ids.append(el["id"])
    return ids


@tool()
async def cmr_experiment_report(
    start_id: int, end_id: int, collections: Optional[str] = None
) -> Dict[str, Any]:
    """Find experiments in an ID range that used CMR-flagged products.

    Builds a CMR sys_id lookup from inventory, fetches the experiments and their
    sample tables in parallel, and reports which experiments used CMR products.
    This is the CMR_dashboard workflow in one call. Fetching sample tables makes
    wide ranges slow (one extra request per samples element), so keep the range
    focused (e.g. one month of experiment IDs).

    Args:
        start_id: First experiment ID (inclusive).
        end_id: Last experiment ID (inclusive). Max span 1000 IDs.
        collections: Comma-separated inventory slugs to source CMR products from.
            Defaults to the configured CMR map (biochemistry, culture, sp_bioch).

    Returns a summary with: scanned, with_cmr, cmr_products_known, and rows
    (experiment_id, title, date, owner, cmr_products with their type_of_risk).
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

    # Flatten (experiment_id -> samples element ids), keeping experiment summaries.
    exp_by_id: Dict[int, Dict[str, Any]] = {}
    pairs: List[tuple] = []  # (experiment_id, element_id)
    for exp in experiments:
        if not isinstance(exp, dict) or not exp.get("id"):
            continue
        exp_by_id[exp["id"]] = exp
        for element_id in _samples_element_ids(exp):
            pairs.append((exp["id"], element_id))

    # Fetch every samples element once, in parallel, then map sys_ids back.
    sysid_sets = await client.gather([_element_sysids(eid) for (_, eid) in pairs])

    used_by_exp: Dict[int, set] = defaultdict(set)
    for (exp_id, _), sids in zip(pairs, sysid_sets):
        if isinstance(sids, set):
            for sid in sids:
                if sid in lookup:
                    used_by_exp[exp_id].add(sid)

    rows: List[Dict[str, Any]] = []
    for exp_id, sids in used_by_exp.items():
        if not sids:
            continue
        summary = slim_experiment(exp_by_id[exp_id])
        rows.append(
            {
                "experiment_id": summary["id"],
                "title": summary["title"],
                "date": summary["start_date"],
                "owner": summary["owner"],
                "cmr_products": [
                    {
                        "name": lookup[sid]["name"],
                        "sys_id": lookup[sid]["sys_id"],
                        "type_of_risk": lookup[sid].get("type_of_risk", ""),
                    }
                    for sid in sorted(sids)
                ],
            }
        )

    rows.sort(key=lambda r: r["experiment_id"] or 0)
    return {
        "scanned": len(exp_by_id),
        "with_cmr": len(rows),
        "cmr_products_known": len(lookup),
        "rows": rows,
    }
