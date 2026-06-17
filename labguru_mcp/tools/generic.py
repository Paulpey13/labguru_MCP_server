"""Generic / introspection tools: raw API access, server info, capabilities."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .. import __version__
from ..app import client, mcp, settings, tool

API = "/api/v1"


@tool()
async def get_generic_item(item_id: int) -> Dict[str, Any]:
    """Get a Biocollections::Generic item by ID.

    Args:
        item_id: Numeric generic item ID.
    """
    return await client.get(f"{API}/generics/{item_id}.json")


@tool(write=True)
async def api_request(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
) -> Any:
    """Escape hatch: perform an arbitrary authenticated Labguru API request.

    Use for endpoints without a dedicated tool. The auth token is injected
    automatically (query for GET/DELETE, body for POST/PUT). Marked as a write
    tool because it can mutate data; disabled in read-only mode.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE).
        path: API path starting with "/", e.g. "/api/v1/experiments.json".
        params: Optional query parameters.
        body: Optional JSON body (for POST/PUT).
    """
    return await client.request(method, path, params=params, json_body=body)


@tool()
async def whoami() -> Dict[str, Any]:
    """Report the server configuration and auth status (no secret leaked).

    Returns base URL, auth mode, a short token hint, read-only flag, and version.
    """
    if settings.token:
        mode = "token"
    elif settings.login and settings.password:
        mode = "login_password"
    else:
        mode = "none"
    return {
        "version": __version__,
        "base_url": settings.base_url,
        "auth_mode": mode,
        "token_hint": client.token_hint(),
        "read_only": settings.read_only,
    }


@tool()
async def list_capabilities() -> Dict[str, Any]:
    """List the server's configured collections, CMR mapping, and registered tools.

    Useful for discovering how this instance is configured before calling tools.
    """
    tools = await mcp.list_tools()
    return {
        "version": __version__,
        "biocollections": list(settings.biocollections),
        "direct_inventory": list(settings.direct_inventory),
        "cmr_map": settings.cmr_map,
        "read_only": settings.read_only,
        "max_concurrency": settings.max_concurrency,
        "tool_count": len(tools),
        "tools": sorted(t.name for t in tools),
    }
