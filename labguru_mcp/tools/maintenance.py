"""Instrument maintenance event tools."""

from __future__ import annotations

from typing import Any, Dict, List

from ..app import client, tool
from ..errors import LabguruError

API = "/api/v1"


@tool()
async def list_maintenance_events(limit: int = 50) -> List[Dict[str, Any]]:
    """List instrument maintenance events.

    Returns an empty list if the endpoint is unavailable on this instance.

    Args:
        limit: Maximum number of events to return (default 50).
    """
    try:
        return await client.paginate(f"{API}/maintenance_events.json", limit=limit)
    except LabguruError:
        return []
