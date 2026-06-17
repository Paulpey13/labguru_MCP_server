"""Stock tools: physical vials/tubes linked to inventory items."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..app import client, tool
from ..formatting import slim_stock

API = "/api/v1"


@tool()
async def list_stocks(
    limit: int = 25, inventory_item_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """List stock entries, optionally for one inventory item.

    Args:
        limit: Maximum number of stocks to return (default 25).
        inventory_item_id: Restrict to stocks of this inventory item.
    """
    params: Dict[str, Any] = {}
    if inventory_item_id is not None:
        params["inventory_item_id"] = inventory_item_id
    raw = await client.paginate(f"{API}/stocks.json", limit=limit, **params)
    return [slim_stock(s) for s in raw]


@tool()
async def get_stock(stock_id: int) -> Dict[str, Any]:
    """Get a single stock entry by ID (full JSON).

    Args:
        stock_id: Numeric Labguru stock ID.
    """
    return await client.get(f"{API}/stocks/{stock_id}.json")


@tool()
async def get_stock_by_barcode(barcode: str) -> Optional[Dict[str, Any]]:
    """Look up a stock entry by the barcode printed on the tube/vial.

    Args:
        barcode: Barcode string.

    Returns the stock JSON, or null if not found.
    """
    data = await client.get(f"{API}/stocks/get_stocks_by_barcode.json", barcode=barcode)
    if not data:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return data


@tool(write=True)
async def create_stock(
    inventory_item_id: int,
    quantity: Optional[float] = None,
    barcode: Optional[str] = None,
    location: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new stock entry for an inventory item. (Write operation.)

    Args:
        inventory_item_id: Parent inventory item ID.
        quantity: Initial quantity.
        barcode: Optional barcode string.
        location: Optional storage location.
    """
    item: Dict[str, Any] = {"inventory_item_id": inventory_item_id}
    if quantity is not None:
        item["quantity"] = quantity
    if barcode is not None:
        item["barcode"] = barcode
    if location is not None:
        item["location"] = location
    return await client.post(f"{API}/stocks.json", {"item": item})


@tool(write=True)
async def update_stock(stock_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update fields on a stock (quantity, location, barcode, lot...). (Write operation.)

    Args:
        stock_id: Numeric stock ID.
        fields: Attributes to change.
    """
    return await client.put(f"{API}/stocks/{stock_id}.json", {"item": fields})
