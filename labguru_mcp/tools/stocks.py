"""Stock tools: physical vials/tubes linked to inventory items."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from ..app import client, tool
from ..errors import LabguruError
from ..formatting import kendo_sort, slim_stock

API = "/api/v1"


def _parse_date(value: Any) -> Optional[date]:
    """Parse a Labguru date string ('YYYY-MM-DD' optionally with time)."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _location_name(stock: Dict[str, Any]) -> Optional[str]:
    loc = stock.get("storage_location") or stock.get("location")
    if isinstance(loc, dict):
        return loc.get("name")
    return loc


@tool()
async def list_stocks(
    limit: int = 25, inventory_item_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """List stock entries, most recent first, optionally for one inventory item.

    Args:
        limit: Maximum number of stocks to return (default 25).
        inventory_item_id: Restrict to stocks of this inventory item.
    """
    if inventory_item_id is not None:
        raw = await client.paginate(
            f"{API}/stocks.json", limit=limit, inventory_item_id=inventory_item_id
        )
    else:
        try:
            raw = await client.paginate(
                f"{API}/stocks.json", limit=limit, params=kendo_sort("id", "desc")
            )
        except LabguruError:
            raw = await client.paginate(f"{API}/stocks.json", limit=limit)
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


@tool()
async def expiring_stocks(
    within_days: int = 30, include_expired: bool = False, limit: int = 100
) -> Dict[str, Any]:
    """List stocks whose expiration date is near (or past).

    Scans the full stock list (cached) and filters by expiration_date. On large
    instances the first scan is slow; subsequent calls hit the cache.

    Args:
        within_days: Flag stocks expiring within this many days from today
            (default 30).
        include_expired: Also include stocks that already expired.
        limit: Maximum stocks to return (default 100), soonest first.

    Returns a summary with today, within_days, scanned, expired_count,
    expiring_count, and stocks (stock_id, name, lot, expiration_date, days_left,
    location).
    """
    raw = await client.cached_paginate(f"{API}/stocks.json", per_page=1000)
    today = date.today()
    found: List[Dict[str, Any]] = []
    expired_count = 0
    for s in raw:
        exp = _parse_date(s.get("expiration_date"))
        if exp is None:
            continue
        days_left = (exp - today).days
        if days_left < 0:
            expired_count += 1
            if not include_expired:
                continue
        elif days_left > within_days:
            continue
        found.append(
            {
                "stock_id": s.get("id"),
                "name": s.get("name") or s.get("content_name"),
                "lot": s.get("lot"),
                "expiration_date": s.get("expiration_date"),
                "days_left": days_left,
                "location": _location_name(s),
            }
        )
    found.sort(key=lambda r: r["days_left"])
    return {
        "today": today.isoformat(),
        "within_days": within_days,
        "scanned": len(raw),
        "expired_count": expired_count,
        "expiring_count": len(found),
        "stocks": found[:limit],
    }


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
