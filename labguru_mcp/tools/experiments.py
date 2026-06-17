"""Experiment tools: list, read, sample/stock extraction, range scan, write."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..app import client, tool
from ..errors import LabguruError
from ..formatting import (
    experiment_procedures,
    iter_experiment_rows,
    slim_experiment,
)

API = "/api/v1"


@tool()
async def list_experiments(
    limit: int = 20, project_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """List experiments, optionally filtered by project.

    Args:
        limit: Maximum number of experiments to return (default 20).
        project_id: Restrict to a single project when provided.

    Returns slim records: id, title, start_date, project_id, uuid, owner.
    """
    params: Dict[str, Any] = {}
    if project_id is not None:
        params["project_id"] = project_id
    raw = await client.paginate(f"{API}/experiments.json", limit=limit, **params)
    return [slim_experiment(e) for e in raw]


@tool()
async def get_experiment(experiment_id: int) -> Dict[str, Any]:
    """Get a single experiment with its procedure/section names.

    Args:
        experiment_id: Numeric Labguru experiment ID.
    """
    exp = await client.get(f"{API}/experiments/{experiment_id}.json")
    summary = slim_experiment(exp)
    summary["protocol_id"] = exp.get("protocol_id")
    summary["procedures"] = experiment_procedures(exp)
    return summary


@tool()
async def get_experiment_raw(experiment_id: int) -> Dict[str, Any]:
    """Get the full, untrimmed JSON for an experiment (all nested data).

    Args:
        experiment_id: Numeric Labguru experiment ID.
    """
    return await client.get(f"{API}/experiments/{experiment_id}.json")


@tool()
async def get_experiment_samples(
    experiment_id: int, limit: int = 200
) -> List[Dict[str, Any]]:
    """Extract all sample/reagent rows used across an experiment's procedures.

    Args:
        experiment_id: Numeric Labguru experiment ID.
        limit: Maximum number of sample rows to return (default 200).
    """
    exp = await client.get(f"{API}/experiments/{experiment_id}.json")
    return iter_experiment_rows(exp)[:limit]


@tool()
async def get_experiment_stock_ids(experiment_id: int) -> List[int]:
    """Return the deduplicated, sorted stock IDs referenced in an experiment.

    Useful for experiment-duplication workflows that must preserve stock links.

    Args:
        experiment_id: Numeric Labguru experiment ID.
    """
    exp = await client.get(f"{API}/experiments/{experiment_id}.json")
    ids: set[int] = set()
    for item in iter_experiment_rows(exp):
        if item.get("stock_id"):
            try:
                ids.add(int(item["stock_id"]))
            except (TypeError, ValueError):
                pass
    return sorted(ids)


@tool()
async def get_experiments_in_range(
    start_id: int, end_id: int
) -> List[Dict[str, Any]]:
    """Fetch every experiment whose ID is in [start_id, end_id] (parallel, 404s skipped).

    Args:
        start_id: First experiment ID (inclusive).
        end_id: Last experiment ID (inclusive). Keep the range under ~1000.
    """
    if end_id < start_id:
        raise LabguruError("end_id must be >= start_id.")
    if end_id - start_id > 1000:
        raise LabguruError("Range too large (max 1000 IDs). Narrow the range.")

    async def _one(eid: int) -> Optional[Dict[str, Any]]:
        try:
            return await client.get(f"{API}/experiments/{eid}.json")
        except LabguruError:
            return None

    results = await client.gather([_one(e) for e in range(start_id, end_id + 1)])
    out = [slim_experiment(r) for r in results if isinstance(r, dict) and r.get("id")]
    out.sort(key=lambda e: e.get("id") or 0)
    return out


@tool(write=True)
async def create_experiment(
    title: str, project_id: int, description: str = ""
) -> Dict[str, Any]:
    """Create a new experiment in a project. (Write operation.)

    Args:
        title: Experiment title.
        project_id: Target project ID.
        description: Optional description.
    """
    item = {"title": title, "project_id": project_id, "description": description}
    return await client.post(f"{API}/experiments.json", {"item": item})


@tool(write=True)
async def update_experiment(
    experiment_id: int, fields: Dict[str, Any]
) -> Dict[str, Any]:
    """Update fields on an experiment. (Write operation.)

    Args:
        experiment_id: Numeric experiment ID.
        fields: Attributes to change, e.g. {"title": "...", "description": "..."}.
    """
    return await client.put(f"{API}/experiments/{experiment_id}.json", {"item": fields})
