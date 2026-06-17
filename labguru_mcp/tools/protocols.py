"""Protocol tools: list, read, search by name, find by referenced sys_id."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..app import client, tool
from ..errors import LabguruError
from ..formatting import kendo_sort

API = "/api/v1"


@tool()
async def list_protocols(limit: int = 20, oldest_first: bool = False) -> List[Dict[str, Any]]:
    """List protocols, most recent first by default.

    Args:
        limit: Maximum number of protocols to return (default 20).
        oldest_first: Return oldest first instead of most recent.
    """
    direction = "asc" if oldest_first else "desc"
    try:
        raw = await client.paginate(
            f"{API}/protocols.json", limit=limit, params=kendo_sort("id", direction)
        )
    except LabguruError:
        raw = await client.paginate(f"{API}/protocols.json", limit=limit)
    return [{"id": p.get("id"), "name": p.get("name"), "uuid": p.get("uuid")} for p in raw]


@tool()
async def get_protocol(protocol_id: int) -> Dict[str, Any]:
    """Get a single protocol by ID (full JSON).

    Args:
        protocol_id: Numeric Labguru protocol ID.
    """
    return await client.get(f"{API}/protocols/{protocol_id}.json")


@tool()
async def search_protocols(query: str) -> List[Dict[str, Any]]:
    """Find protocols whose name contains the query (case-insensitive).

    Args:
        query: Substring to match against protocol names, e.g. "western blot".
    """
    q = query.lower()
    raw = await client.paginate(f"{API}/protocols.json", per_page=200)
    return [
        {"id": p.get("id"), "name": p.get("name")}
        for p in raw
        if q in (p.get("name") or "").lower()
    ]


@tool()
async def find_protocols_with_sysid(sysid: str) -> List[Dict[str, Any]]:
    """Find protocols that reference an inventory sys_id anywhere in their content.

    Scans the full JSON of every protocol (parallel) for the sys_id string.
    Heavy on large instances.

    Args:
        sysid: Inventory system ID, e.g. "CU-23.0042".
    """
    target = sysid.lower()
    listing = await client.paginate(f"{API}/protocols.json", per_page=200)
    ids = [p.get("id") for p in listing if p.get("id")]

    async def _scan(pid: int) -> Optional[Dict[str, Any]]:
        try:
            data = await client.get(f"{API}/protocols/{pid}.json")
        except LabguruError:
            return None
        text = json.dumps(data, ensure_ascii=False).lower()
        if target in text:
            return {"id": data.get("id"), "name": data.get("name")}
        return None

    results = await client.gather([_scan(pid) for pid in ids], concurrency=10)
    return [r for r in results if isinstance(r, dict)]
