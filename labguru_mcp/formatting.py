"""
labguru_mcp.formatting
----------------------
Pure helper functions for normalising Labguru API payloads. No I/O, no state,
so they are easy to unit test and reuse.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .config import WRAPPER_KEYS


def extract_list(response: Any) -> List[Dict[str, Any]]:
    """Return a list of dicts from a possibly wrapped API response."""
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        for key in WRAPPER_KEYS:
            value = response.get(key)
            if isinstance(value, list):
                return value
        list_values = [v for v in response.values() if isinstance(v, list)]
        if len(list_values) == 1:
            return list_values[0]
    return []


def kendo_sort(field: str = "id", direction: str = "desc") -> Dict[str, Any]:
    """Build Kendo-style sort query params accepted by Labguru list endpoints.

    Labguru rejects plain ``sort``/``direction`` params (HTTP 500) but honours
    the Kendo grid syntax. Higher IDs are more recent, so ``id`` desc yields the
    newest records first without scanning every page.
    """
    return {"kendo": "true", "sort[0][field]": field, "sort[0][dir]": direction}


def collect_values(obj: Any, key: str) -> set:
    """Recursively collect every non-empty string value stored under ``key``.

    Used to pull sample sys_ids (the ``auto_name`` attribute) out of the nested
    JSON of a Labguru samples element, independent of the exact table layout.
    """
    found: set = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key and isinstance(v, str) and v.strip():
                    found.add(v.strip())
                else:
                    _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(obj)
    return found


def safe_num(value: Any, default: float = 0.0) -> float:
    """Convert ``value`` to float, returning ``default`` on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def pick(data: Dict[str, Any], keys: Iterable[str]) -> Dict[str, Any]:
    """Return a shallow copy of ``data`` limited to ``keys`` that are present."""
    return {k: data.get(k) for k in keys}


def slim_experiment(exp: Dict[str, Any]) -> Dict[str, Any]:
    member = exp.get("member") or {}
    return {
        "id": exp.get("id"),
        "title": exp.get("title") or exp.get("name"),
        "start_date": exp.get("start_date"),
        "project_id": exp.get("project_id"),
        "uuid": exp.get("uuid"),
        "owner": member.get("name") if isinstance(member, dict) else member,
    }


def slim_inventory(item: Dict[str, Any], collection: str) -> Dict[str, Any]:
    web = item.get("web_page") or {}
    manufacturer = item.get("manufacturer") or item.get("manufacturer_name")
    manufacturer_url = None
    if isinstance(manufacturer, dict):
        manufacturer_url = manufacturer.get("url")
        manufacturer = manufacturer.get("name")
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "sys_id": item.get("auto_name") or item.get("sys_id"),
        "collection": collection,
        "catalog_number": item.get("catalog_number"),
        "manufacturer": manufacturer,
        "manufacturer_url": manufacturer_url,
        "url": web.get("url") if isinstance(web, dict) else web,
    }


def item_sys_id(item: Dict[str, Any]) -> str:
    return item.get("auto_name") or item.get("sys_id") or ""


def slim_stock(stock: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": stock.get("id"),
        "name": stock.get("name"),
        "barcode": stock.get("barcode"),
        "inventory_item_id": stock.get("inventory_item_id"),
        "quantity": stock.get("quantity") or stock.get("volume") or stock.get("weight"),
        "unit": stock.get("unit") or stock.get("volume_unit") or stock.get("weight_unit"),
        "lot": stock.get("lot"),
        "location": stock.get("location") or stock.get("storage_location"),
    }


def shopping_status(item: Dict[str, Any]) -> str:
    if item.get("submited_at") or item.get("submitted_at"):
        return "submitted"
    if item.get("approved_at"):
        return "approved"
    return "pending"


def slim_shopping(item: Dict[str, Any]) -> Dict[str, Any]:
    material = item.get("material") or {}
    manufacturer = material.get("manufacturer") or {}
    return {
        "order_number": item.get("order_number"),
        "name": item.get("name") or material.get("name"),
        "material_id": item.get("material_id"),
        "catalog_number": material.get("catalog_number"),
        "manufacturer": manufacturer.get("name") if isinstance(manufacturer, dict) else None,
        "quantity": item.get("quantity"),
        "price": item.get("price"),
        "currency": item.get("currency_symbol"),
        "requested_at": item.get("requested_at"),
        "approved_at": item.get("approved_at"),
        "submitted_at": item.get("submited_at") or item.get("submitted_at"),
        "status": shopping_status(item),
    }


def financial_summary(items: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute subtotal, fees, and grand total from raw shopping list items."""
    subtotal = sum(safe_num(i.get("price")) * safe_num(i.get("quantity"), 1) for i in items)
    delivery = sum(safe_num(i.get("Delivery fee (€)") or i.get("delivery_fee")) for i in items)
    dry_ice = sum(safe_num(i.get("Dry ice (€)") or i.get("dry_ice")) for i in items)
    extras = sum(
        safe_num(i.get("Additional expenses (€)") or i.get("additional_expenses"))
        for i in items
    )
    return {
        "subtotal": round(subtotal, 2),
        "delivery_fee": round(delivery, 2),
        "dry_ice": round(dry_ice, 2),
        "additional_expenses": round(extras, 2),
        "grand_total": round(subtotal + delivery + dry_ice + extras, 2),
    }


def parse_sample_entries(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse the ``data`` payload of a samples element into structured rows.

    A samples element stores its table as a JSON string under ``data``. Each
    entry in ``data["samples"]`` describes one inventory item used, with its
    sys_id under an ``auto_name`` field and the linked stock vials under the key
    named by ``itemsKey`` (and listed in ``saved_stocks_ids``).
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(data, dict):
        return out
    for entry in data.get("samples") or []:
        if not isinstance(entry, dict):
            continue
        items_key = entry.get("itemsKey")
        items = entry.get(items_key) if isinstance(entry.get(items_key), list) else []
        autos = sorted(collect_values(entry, "auto_name"))
        stock_ids = entry.get("saved_stocks_ids")
        if not isinstance(stock_ids, list) or not stock_ids:
            stock_ids = [it.get("id") for it in items if isinstance(it, dict) and it.get("id")]
        out.append(
            {
                "name": entry.get("name"),
                "sys_id": autos[0] if autos else None,
                "collection": entry.get("collection_name"),
                "stock_ids": [s for s in stock_ids if isinstance(s, int)],
                "stocks": [
                    {
                        "stock_id": it.get("id"),
                        "name": it.get("name"),
                        "lot": it.get("lot"),
                        "expiration_date": it.get("expiration_date"),
                    }
                    for it in items
                    if isinstance(it, dict)
                ],
            }
        )
    return out


def iter_experiment_rows(exp: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten every procedure/element/row item dict from an experiment payload."""
    rows: List[Dict[str, Any]] = []
    for wrapper in exp.get("experiment_procedures") or []:
        proc = wrapper.get("experiment_procedure", wrapper)
        for element in proc.get("elements") or []:
            for row in element.get("rows") or []:
                item = row.get("item", row)
                if item:
                    rows.append(item)
    return rows


def experiment_procedures(exp: Dict[str, Any]) -> List[Dict[str, Any]]:
    procedures: List[Dict[str, Any]] = []
    for wrapper in exp.get("experiment_procedures") or []:
        proc = wrapper.get("experiment_procedure", wrapper)
        procedures.append({"id": proc.get("id"), "name": proc.get("name")})
    return procedures
