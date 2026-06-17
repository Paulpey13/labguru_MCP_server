"""Project and folder tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..app import client, tool
from ..errors import LabguruError

API = "/api/v1"


@tool()
async def list_projects(
    limit: int = 50, search: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List projects, optionally filtered by a name substring.

    Args:
        limit: Maximum number of projects to return (default 50).
        search: Optional case-insensitive name filter.
    """
    raw = await client.paginate(f"{API}/projects.json", limit=None if search else limit)
    items = [{"id": p.get("id"), "name": p.get("name"), "uuid": p.get("uuid")} for p in raw]
    if search:
        q = search.lower()
        items = [p for p in items if q in (p["name"] or "").lower()]
    return items[:limit]


@tool()
async def get_project(project_id: int) -> Dict[str, Any]:
    """Get a single project by ID.

    Args:
        project_id: Numeric Labguru project ID.
    """
    return await client.get(f"{API}/projects/{project_id}.json")


@tool()
async def list_folders(limit: int = 50) -> List[Dict[str, Any]]:
    """List project folders (returns an empty list if unavailable on this instance).

    Args:
        limit: Maximum number of folders to return (default 50).
    """
    try:
        return await client.paginate(f"{API}/folders.json", limit=limit)
    except LabguruError:
        return []


@tool(write=True)
async def create_project(name: str, description: str = "") -> Dict[str, Any]:
    """Create a new project. (Write operation.)

    Args:
        name: Project name.
        description: Optional description.
    """
    item: Dict[str, Any] = {"name": name}
    if description:
        item["description"] = description
    return await client.post(f"{API}/projects.json", {"item": item})


@tool(write=True)
async def update_project(project_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update fields on a project. (Write operation.)

    Args:
        project_id: Numeric project ID.
        fields: Attributes to change.
    """
    return await client.put(f"{API}/projects/{project_id}.json", {"item": fields})
