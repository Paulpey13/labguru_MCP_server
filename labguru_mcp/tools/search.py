"""Cross-resource convenience search."""

from __future__ import annotations

from typing import Any, Dict, List

from ..app import client, settings, tool
from ..errors import LabguruError
from ..formatting import slim_experiment, slim_inventory

API = "/api/v1"


@tool()
async def global_search(query: str, limit_per_type: int = 10) -> Dict[str, Any]:
    """Search experiments, protocols, and inventory for a keyword in one call.

    Runs the per-resource scans in parallel and returns grouped results. Intended
    for "where does X appear?" questions. Matching is case-insensitive substring
    on names/titles.

    Args:
        query: Keyword to search for.
        limit_per_type: Maximum matches returned per resource type (default 10).
    """
    q = query.lower()

    async def _experiments() -> List[Dict[str, Any]]:
        raw = await client.paginate(f"{API}/experiments.json", per_page=200, limit=2000)
        hits = [
            slim_experiment(e)
            for e in raw
            if q in (e.get("title") or e.get("name") or "").lower()
        ]
        return hits[:limit_per_type]

    async def _protocols() -> List[Dict[str, Any]]:
        raw = await client.paginate(f"{API}/protocols.json", per_page=200)
        hits = [
            {"id": p.get("id"), "name": p.get("name")}
            for p in raw
            if q in (p.get("name") or "").lower()
        ]
        return hits[:limit_per_type]

    async def _inventory() -> List[Dict[str, Any]]:
        async def _scan(col: str) -> List[Dict[str, Any]]:
            try:
                raw = await client.cached_paginate(settings.inventory_path(col), per_page=1000)
            except LabguruError:
                return []
            return [
                slim_inventory(i, col)
                for i in raw
                if q in (i.get("name") or "").lower()
            ]

        results = await client.gather([_scan(c) for c in settings.all_collections])
        out: List[Dict[str, Any]] = []
        for r in results:
            if isinstance(r, list):
                out.extend(r)
        return out[:limit_per_type]

    experiments, protocols, inventory = await client.gather(
        [_experiments(), _protocols(), _inventory()], concurrency=3
    )
    return {
        "query": query,
        "experiments": experiments if isinstance(experiments, list) else [],
        "protocols": protocols if isinstance(protocols, list) else [],
        "inventory": inventory if isinstance(inventory, list) else [],
    }
