"""Shopping list and purchase order tools."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from ..app import client, tool
from ..formatting import financial_summary, slim_shopping

API = "/api/v1"

OrderStatus = Literal["all", "pending", "approved", "submitted"]


async def _all_items() -> List[Dict[str, Any]]:
    return await client.cached_paginate(f"{API}/shopping_list.json", per_page=200)


@tool()
async def list_shopping_items(
    status: OrderStatus = "all", limit: int = 50
) -> List[Dict[str, Any]]:
    """List shopping list items, optionally filtered by status.

    Args:
        status: One of "all" (default), "pending" (requested, not approved),
            "approved" (approved, not submitted), "submitted".
        limit: Maximum items to return (default 50).
    """
    items = [slim_shopping(i) for i in await _all_items()]
    items.sort(key=lambda i: i.get("requested_at") or "", reverse=True)
    if status != "all":
        items = [i for i in items if i["status"] == status]
    return items[:limit]


@tool()
async def get_order(order_number: str) -> List[Dict[str, Any]]:
    """List all shopping list items belonging to a given order number.

    Args:
        order_number: The order_number string as stored in Labguru.
    """
    raw = await _all_items()
    return [
        slim_shopping(i)
        for i in raw
        if str(i.get("order_number")) == str(order_number)
    ]


@tool()
async def get_order_summary(order_number: str) -> Dict[str, Any]:
    """Compute a financial summary (subtotal, fees, grand total) for an order.

    Args:
        order_number: The Labguru order number.
    """
    raw = await _all_items()
    matching = [i for i in raw if str(i.get("order_number")) == str(order_number)]
    if not matching:
        return {"error": f"No items found for order {order_number}"}
    summary = financial_summary(matching)
    summary["order_number"] = order_number
    summary["item_count"] = len(matching)
    summary["items"] = [
        {"name": i.get("name"), "quantity": i.get("quantity"), "price": i.get("price")}
        for i in matching
    ]
    return summary


@tool()
async def get_last_order() -> Optional[Dict[str, Any]]:
    """Get the most recent order on the shopping list with its financial summary.

    Returns order_number, item_count, grand_total and items, or null if empty.
    """
    raw = await _all_items()
    if not raw:
        return None
    raw.sort(key=lambda i: i.get("requested_at") or "", reverse=True)
    order_number = raw[0].get("order_number")
    matching = [i for i in raw if str(i.get("order_number")) == str(order_number)]
    summary = financial_summary(matching)
    return {
        "order_number": order_number,
        "item_count": len(matching),
        "grand_total": summary["grand_total"],
        "items": [
            {"name": i.get("name"), "quantity": i.get("quantity"), "price": i.get("price")}
            for i in matching
        ],
    }


@tool(write=True)
async def add_shopping_item(
    material_id: str, quantity: float, price: Optional[float] = None
) -> Dict[str, Any]:
    """Add an item to the shopping list. (Write operation.)

    Args:
        material_id: Labguru material / catalog ID.
        quantity: Quantity to order.
        price: Optional unit price.
    """
    payload: Dict[str, Any] = {"material_id": material_id, "quantity": quantity}
    if price is not None:
        payload["price"] = price
    return await client.post(f"{API}/shopping_list/add_item", payload)
