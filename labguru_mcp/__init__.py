"""Labguru MCP server package.

A modular Model Context Protocol server exposing the Labguru laboratory
management REST API as native LLM tools.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["build_server", "main", "mcp", "client", "settings", "__version__"]


def __getattr__(name: str):
    # Lazy re-exports so `import labguru_mcp` stays cheap and avoids importing
    # FastMCP/httpx until something is actually used.
    if name in ("build_server", "main", "mcp", "client", "settings"):
        from . import app

        return getattr(app, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
