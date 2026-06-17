"""Inventory tools across all biocollections and direct inventory types.

Collections, routing, and the CMR field mapping are configuration-driven
(see labguru_mcp.config), so any lab can adapt them without code changes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..app import client, settings, tool
from ..errors import LabguruError
from ..formatting import extract_list, item_sys_id, slim_inventory

API = "/api/v1"


def _collections_arg(collections: Optional[str], default: List[str]) -> List[str]:
    if collections:
        return [c.strip() for c in collections.split(",") if c.strip()]
    return default


@tool()
async def list_collections() -> List[Dict[str, Any]]:
    """List the inventory collections available on this Labguru instance.

    Returns the API-reported biocollections; falls back to the configured
    collection names if the endpoint is unavailable.
    """
    try:
        raw = await client.get(f"{API}/biocollections.json")
        collections = extract_list(raw)
        if collections:
            return collections
    except LabguruError:
        pass
    return [{"slug": s, "name": s} for s in settings.all_collections]


@tool()
async def list_inventory(
    collection: str = "biochemistry", limit: int = 25
) -> List[Dict[str, Any]]:
    """List items from an inventory collection.

    Args:
        collection: Collection slug (e.g. biochemistry, antibodies, cell_lines,
            culture, plasmids, primers, sirna, taqman, crispr, mrna, rodents).
        limit: Maximum number of items to return (default 25).
    """
    raw = await client.paginate(settings.inventory_path(collection), limit=limit)
    return [slim_inventory(i, collection) for i in raw]


@tool()
async def search_inventory(
    query: str, collection: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """Search inventory items by name.

    Args:
        query: Case-insensitive substring to match against item names.
        collection: Collection slug to search. If omitted, all collections are
            searched in parallel.
        limit: Maximum matches to return (default 50).
    """
    q = query.lower()
    targets = [collection] if collection else list(settings.all_collections)

    async def _scan(col: str) -> List[Dict[str, Any]]:
        try:
            raw = await client.paginate(settings.inventory_path(col), per_page=1000)
        except LabguruError:
            return []
        return [slim_inventory(i, col) for i in raw if q in (i.get("name") or "").lower()]

    results = await client.gather([_scan(c) for c in targets])
    out: List[Dict[str, Any]] = []
    for r in results:
        if isinstance(r, list):
            out.extend(r)
    return out[:limit]


@tool()
async def get_inventory_item(item_id: int) -> Dict[str, Any]:
    """Get a single inventory item by its numeric inventory_item ID.

    Args:
        item_id: Numeric Labguru inventory item ID.
    """
    return await client.get(f"{API}/inventory_items/{item_id}.json")


@tool()
async def get_collection_item(collection: str, item_id: int) -> Dict[str, Any]:
    """Get an item by collection slug and ID (routes direct vs biocollection).

    Args:
        collection: Collection slug (e.g. biochemistry, antibodies).
        item_id: Numeric item ID.
    """
    if collection in settings.direct_inventory:
        return await client.get(f"{API}/{collection}/{item_id}.json")
    return await client.get(f"{API}/biocollections/{collection}/{item_id}.json")


@tool()
async def find_item_by_sysid(sysid: str) -> Optional[Dict[str, Any]]:
    """Search every collection for an inventory item matching a sys_id.

    Args:
        sysid: System ID such as "CU-23.0042" (matched against auto_name/sys_id).

    Returns the slim item (with its collection) or null if not found.
    """
    target = sysid.strip().lower()

    async def _scan(col: str) -> Optional[Dict[str, Any]]:
        try:
            raw = await client.paginate(settings.inventory_path(col), per_page=1000)
        except LabguruError:
            return None
        for i in raw:
            if item_sys_id(i).lower() == target:
                return slim_inventory(i, col)
        return None

    results = await client.gather([_scan(c) for c in settings.all_collections])
    for r in results:
        if isinstance(r, dict):
            return r
    return None


@tool()
async def get_cmr_items(collections: Optional[str] = None) -> List[Dict[str, Any]]:
    """List inventory items flagged as CMR (with risk classification fields filled).

    The CMR custom-field mapping per collection is configurable (LABGURU_CMR_MAP).
    Defaults: biochemistry custom5/custom6; culture and sp_bioch custom3/custom4.

    Args:
        collections: Comma-separated collection slugs to scan. Defaults to the
            collections present in the configured CMR map.

    Returns items with name, sys_id, collection, type_of_risk, preventive_measure.
    """
    cmr_map = settings.cmr_map
    targets = _collections_arg(collections, list(cmr_map.keys()))

    async def _scan(col: str) -> List[Dict[str, Any]]:
        mapping = cmr_map.get(col, {"risk": "custom5", "measure": "custom6"})
        risk_field, measure_field = mapping["risk"], mapping["measure"]
        try:
            raw = await client.paginate(settings.inventory_path(col), per_page=1000)
        except LabguruError:
            return []
        found = []
        for i in raw:
            risk = i.get(risk_field)
            measure = i.get(measure_field)
            if risk or measure:
                found.append(
                    {
                        "name": i.get("name"),
                        "sys_id": item_sys_id(i),
                        "collection": col,
                        "type_of_risk": risk or "",
                        "preventive_measure": measure or "",
                    }
                )
        return found

    results = await client.gather([_scan(c) for c in targets])
    out: List[Dict[str, Any]] = []
    for r in results:
        if isinstance(r, list):
            out.extend(r)
    return out


@tool()
async def get_safety_links(collections: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return name + web page URL for inventory items that have a link (safety data sheets).

    Args:
        collections: Comma-separated collection slugs. Defaults to all configured
            collections.

    Returns items with name, sys_id, collection, url.
    """
    targets = _collections_arg(collections, list(settings.all_collections))

    async def _scan(col: str) -> List[Dict[str, Any]]:
        try:
            raw = await client.paginate(settings.inventory_path(col), per_page=1000)
        except LabguruError:
            return []
        links = []
        for i in raw:
            web = i.get("web_page") or {}
            url = web.get("url") if isinstance(web, dict) else web
            if url:
                links.append(
                    {
                        "name": i.get("name"),
                        "sys_id": item_sys_id(i),
                        "collection": col,
                        "url": url,
                    }
                )
        return links

    results = await client.gather([_scan(c) for c in targets])
    out: List[Dict[str, Any]] = []
    for r in results:
        if isinstance(r, list):
            out.extend(r)
    return out
