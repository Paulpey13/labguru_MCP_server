"""Experiment element, section, and UUID-resolution tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..app import client, tool
from ..errors import LabguruError

API = "/api/v1"


@tool()
async def get_element(element_id: int) -> Dict[str, Any]:
    """Get a single experiment element by its numeric ID.

    Args:
        element_id: Numeric Labguru element ID.
    """
    return await client.get(f"{API}/elements/{element_id}.json")


@tool()
async def get_element_by_uuid(uuid: str) -> Dict[str, Any]:
    """Get an experiment element (e.g. a sample table) by its UUID.

    Tries /api/v1/experiment_elements/{uuid}.json, then the generic resolver.

    Args:
        uuid: Element UUID string.
    """
    for path in (f"{API}/experiment_elements/{uuid}.json", f"/uuid/{uuid}"):
        try:
            return await client.get(path)
        except LabguruError:
            continue
    raise LabguruError(f"Element with UUID {uuid} not found.")


@tool()
async def get_element_rows(uuid: str) -> List[Dict[str, Any]]:
    """Extract the item dicts from every row of a sample-table element.

    Args:
        uuid: Element UUID string.
    """
    el = await get_element_by_uuid(uuid)
    return [row.get("item") for row in (el.get("rows") or []) if row.get("item")]


@tool()
async def resolve_uuid(uuid: str) -> Optional[Dict[str, Any]]:
    """Resolve any Labguru UUID to its underlying resource.

    Tries the generic /uuid/{uuid} endpoint, then experiment_elements.

    Args:
        uuid: Any Labguru UUID string.

    Returns the resource JSON, or null if it cannot be resolved.
    """
    for path in (f"/uuid/{uuid}", f"{API}/experiment_elements/{uuid}.json"):
        try:
            return await client.get(path)
        except LabguruError:
            continue
    return None


@tool()
async def list_sections(limit: int = 50) -> List[Dict[str, Any]]:
    """List experiment sections.

    Args:
        limit: Maximum number of sections to return (default 50).
    """
    return await client.paginate(f"{API}/sections.json", limit=limit)


@tool(write=True)
async def update_element(element_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update fields on an experiment element. (Write operation.)

    Args:
        element_id: Numeric element ID.
        fields: Attributes to change (e.g. {"data": "..."}).
    """
    return await client.put(f"{API}/elements/{element_id}.json", {"item": fields})


@tool(write=True)
async def create_element(
    section_id: int, element_type: str, fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a new element within a section. (Write operation.)

    Args:
        section_id: Parent section ID.
        element_type: Element type string (e.g. "samples", "text").
        fields: Optional additional fields.
    """
    item: Dict[str, Any] = {"section_id": section_id, "element_type": element_type}
    if fields:
        item.update(fields)
    return await client.post(f"{API}/elements.json", {"item": item})


@tool(write=True)
async def create_section(
    experiment_procedure_id: int, title: str = ""
) -> Dict[str, Any]:
    """Create a new section within an experiment procedure. (Write operation.)

    Args:
        experiment_procedure_id: Parent procedure ID.
        title: Section title.
    """
    item = {"experiment_procedure_id": experiment_procedure_id, "title": title}
    return await client.post(f"{API}/sections.json", {"item": item})
