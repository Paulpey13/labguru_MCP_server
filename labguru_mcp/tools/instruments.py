"""Instrument / equipment tools (v2 endpoint preferred, v1 fallback)."""

from __future__ import annotations

from typing import Any, Dict, List

from ..app import client, tool
from ..errors import LabguruError

API = "/api/v1"


@tool()
async def list_instruments(limit: int = 50) -> List[Dict[str, Any]]:
    """List instruments / equipment (tries the v2 endpoint, falls back to v1).

    Args:
        limit: Maximum number of instruments to return (default 50).
    """
    for path in ("/api/v2/instruments", f"{API}/instruments.json"):
        try:
            raw = await client.paginate(path, limit=limit)
            if raw:
                return [
                    {
                        "id": i.get("id"),
                        "name": i.get("name") or i.get("title"),
                        "uuid": i.get("uuid"),
                    }
                    for i in raw
                ]
        except LabguruError:
            continue
    return []


@tool()
async def get_instrument(instrument_id: int) -> Dict[str, Any]:
    """Get a single instrument by ID (tries v2, falls back to v1).

    Args:
        instrument_id: Numeric Labguru instrument ID.
    """
    for path in (
        f"/api/v2/instruments/{instrument_id}",
        f"{API}/instruments/{instrument_id}.json",
    ):
        try:
            return await client.get(path)
        except LabguruError:
            continue
    raise LabguruError(f"Instrument {instrument_id} not found on v1 or v2.")


@tool(write=True)
async def post_measurement(
    instrument_id: int, value: Any, field_name: str = "Value"
) -> Dict[str, Any]:
    """Post a measurement reading from an instrument. (Write operation.)

    Args:
        instrument_id: Reporting instrument ID.
        value: Measurement value.
        field_name: Target field name in the experiment form (default "Value").
    """
    payload: Dict[str, Any] = {"instrument_id": instrument_id, field_name: value}
    return await client.post(f"{API}/measurements", payload)
