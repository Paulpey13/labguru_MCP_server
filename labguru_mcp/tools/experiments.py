"""Experiment tools: list, read, sample/stock extraction, range scan, write."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..app import client, tool
from ..errors import LabguruError
from ..formatting import (
    experiment_procedures,
    extract_list,
    kendo_sort,
    parse_sample_entries,
    slim_experiment,
)

API = "/api/v1"

# A project rarely holds more than this many experiments; cap the window we sort
# client-side when filtering by project (server-side sort + filter is unsupported).
_PROJECT_WINDOW = 1000

# Safety cap when walking back through history for a date filter (pages of 100).
_DATE_WALK_MAX_PAGES = 80


def _samples_element_ids(exp: Dict[str, Any]) -> List[int]:
    """Return the numeric IDs of every ``samples`` element in an experiment."""
    ids: List[int] = []
    for wrapper in exp.get("experiment_procedures") or []:
        proc = wrapper.get("experiment_procedure", wrapper)
        for el in proc.get("elements") or []:
            if el.get("element_type") == "samples" and el.get("id"):
                ids.append(el["id"])
    return ids


async def _element_data(element_id: int) -> Optional[Dict[str, Any]]:
    """Fetch an element and return its parsed ``data`` payload (JSON string)."""
    try:
        el = await client.cached_get(f"{API}/elements/{element_id}.json")
    except LabguruError:
        return None
    data = el.get("data") if isinstance(el, dict) else None
    if isinstance(data, str):
        try:
            return json.loads(data)
        except ValueError:
            return None
    return data if isinstance(data, dict) else None


async def experiment_samples(exp: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fetch and parse all sample rows for an already-fetched experiment dict.

    Sample tables are not embedded in the experiment JSON; each ``samples``
    element is fetched via /api/v1/elements/{id}.json and its ``data`` parsed.
    """
    element_ids = _samples_element_ids(exp)
    datasets = await client.gather([_element_data(eid) for eid in element_ids])
    samples: List[Dict[str, Any]] = []
    for data in datasets:
        if isinstance(data, dict):
            samples.extend(parse_sample_entries(data))
    return samples


def _in_date_range(value: Optional[str], since: Optional[str], until: Optional[str]) -> bool:
    """True if the date prefix of ``value`` falls within [since, until]."""
    day = (value or "")[:10]
    if not day:
        return False
    if since and day < since[:10]:
        return False
    if until and day > until[:10]:
        return False
    return True


async def _walk_dates(since: Optional[str], until: Optional[str]) -> List[Dict[str, Any]]:
    """Walk experiments newest-first (by id) collecting those in a date range.

    IDs increase with time, so we stop once a start_date drops below ``since``.
    Bounded by a page cap; very old ranges may be truncated (best-effort).
    """
    params = kendo_sort("id", "desc")
    per_page = 200
    out: List[Dict[str, Any]] = []
    page = 1
    while page <= _DATE_WALK_MAX_PAGES:
        raw = await client.request(
            "GET",
            f"{API}/experiments.json",
            params={**params, "page": page, "per_page": per_page},
        )
        batch = extract_list(raw)
        if not batch:
            break
        below = False
        for e in batch:
            day = (e.get("start_date") or "")[:10]
            if since and day and day < since[:10]:
                below = True
                break
            if _in_date_range(e.get("start_date"), since, until):
                out.append(slim_experiment(e))
        if below:
            break
        page += 1
    return out


@tool()
async def list_experiments(
    limit: int = 20,
    project_id: Optional[int] = None,
    oldest_first: bool = False,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List experiments, most recent first by default.

    Args:
        limit: Maximum number of experiments to return (default 20).
        project_id: Restrict to a single project when provided.
        oldest_first: Return oldest first instead of most recent.
        since: Keep only experiments whose start_date is on/after this date
            (YYYY-MM-DD).
        until: Keep only experiments whose start_date is on/before this date
            (YYYY-MM-DD).

    Returns slim records: id, title, start_date, project_id, uuid, owner.
    """
    has_date_filter = bool(since or until)

    # Date filter (no project): walk newest-first and stop past the range.
    if has_date_filter and project_id is None:
        rows = await _walk_dates(since, until)
        if oldest_first:
            rows.sort(key=lambda r: r.get("start_date") or "")
        return rows[:limit]

    if project_id is None:
        direction = "asc" if oldest_first else "desc"
        try:
            raw = await client.paginate(
                f"{API}/experiments.json", limit=limit, params=kendo_sort("id", direction)
            )
        except LabguruError:
            raw = await client.paginate(f"{API}/experiments.json", limit=limit)
        return [slim_experiment(e) for e in raw]

    # Project filter and server-side sort cannot be combined, so fetch a bounded
    # window for the project and sort/filter it client-side.
    raw = await client.paginate(
        f"{API}/experiments.json", limit=_PROJECT_WINDOW, project_id=project_id
    )
    raw.sort(key=lambda e: e.get("id") or 0, reverse=not oldest_first)
    rows = [slim_experiment(e) for e in raw]
    if has_date_filter:
        rows = [r for r in rows if _in_date_range(r.get("start_date"), since, until)]
    return rows[:limit]


@tool()
async def count_experiments(project_id: Optional[int] = None) -> Dict[str, Any]:
    """Return the total number of experiments (optionally within a project).

    Uses a single cheap metadata request, so it works even on instances with
    tens of thousands of experiments without fetching them all.

    Args:
        project_id: Restrict the count to a single project when provided.
    """
    extra: Dict[str, Any] = {}
    if project_id is not None:
        extra["project_id"] = project_id
    total = await client.count(f"{API}/experiments.json", **extra)
    return {"count": total, "project_id": project_id}


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

    Each row has: name, sys_id, collection, stock_ids, and stocks (per-vial
    stock_id, lot, expiration_date).

    Args:
        experiment_id: Numeric Labguru experiment ID.
        limit: Maximum number of sample rows to return (default 200).
    """
    exp = await client.get(f"{API}/experiments/{experiment_id}.json")
    return (await experiment_samples(exp))[:limit]


@tool()
async def get_experiment_stock_ids(experiment_id: int) -> List[int]:
    """Return the deduplicated, sorted stock IDs referenced in an experiment.

    Useful for experiment-duplication workflows that must preserve stock links.

    Args:
        experiment_id: Numeric Labguru experiment ID.
    """
    exp = await client.get(f"{API}/experiments/{experiment_id}.json")
    samples = await experiment_samples(exp)
    ids = {sid for s in samples for sid in s.get("stock_ids", [])}
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
