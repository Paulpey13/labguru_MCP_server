"""
labguru_mcp.resources
---------------------
MCP resources: addressable, read-only views of Labguru records the client can
attach as context (as opposed to tool calls). Each returns the record as
pretty-printed JSON.

URIs:
  labguru://experiment/{id}
  labguru://protocol/{id}
  labguru://stock/{id}
  labguru://inventory_item/{id}
"""

from __future__ import annotations

import json
from typing import Any

from .app import client, mcp

API = "/api/v1"


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.resource("labguru://experiment/{experiment_id}", title="Labguru experiment")
async def experiment_resource(experiment_id: str) -> str:
    """Full JSON of an experiment by ID."""
    return _dump(await client.get(f"{API}/experiments/{experiment_id}.json"))


@mcp.resource("labguru://protocol/{protocol_id}", title="Labguru protocol")
async def protocol_resource(protocol_id: str) -> str:
    """Full JSON of a protocol by ID."""
    return _dump(await client.get(f"{API}/protocols/{protocol_id}.json"))


@mcp.resource("labguru://stock/{stock_id}", title="Labguru stock")
async def stock_resource(stock_id: str) -> str:
    """Full JSON of a stock entry by ID."""
    return _dump(await client.get(f"{API}/stocks/{stock_id}.json"))


@mcp.resource("labguru://inventory_item/{item_id}", title="Labguru inventory item")
async def inventory_item_resource(item_id: str) -> str:
    """Full JSON of an inventory item by ID."""
    return _dump(await client.get(f"{API}/inventory_items/{item_id}.json"))
