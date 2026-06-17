"""
labguru_mcp.app
---------------
Application wiring: builds the shared :class:`Settings`, the async
:class:`LabguruClient`, and the :class:`FastMCP` instance, and exposes a
``tool`` decorator used by every tool module.

The ``tool`` decorator adds one feature on top of ``mcp.tool()``: when the
server runs in read-only mode (``LABGURU_READ_ONLY=true``), tools marked
``write=True`` are simply not registered, so they never appear to the client.
"""

from __future__ import annotations

import functools
import sys
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .client import LabguruClient
from .config import Settings, load_settings

settings: Settings = load_settings()
client: LabguruClient = LabguruClient(settings)
mcp: FastMCP = FastMCP("labguru")


def tool(
    write: bool = False, destructive: bool = False, **kwargs: Any
) -> Callable[[Callable], Callable]:
    """Register a function as an MCP tool with standard annotations.

    Adds machine-readable hints so clients can treat reads and writes
    differently (e.g. auto-approve read-only tools). All tools talk to a remote
    API, so ``openWorldHint`` is always true.

    Args:
        write: Mark the tool as a write operation. When the server is in
            read-only mode, write tools are not registered at all.
        destructive: Mark a write tool as potentially destructive.
        **kwargs: Forwarded to ``FastMCP.tool`` (e.g. ``name``).
    """

    def decorator(fn: Callable) -> Callable:
        if write and settings.read_only:
            return fn
        annotations = ToolAnnotations(
            readOnlyHint=not write,
            destructiveHint=destructive if write else False,
            idempotentHint=not write,
            openWorldHint=True,
        )
        target = fn
        if write:
            # A successful write may change what scans return; drop the cache so
            # subsequent reads reflect the change before the TTL expires.
            @functools.wraps(fn)
            async def target(*args: Any, **kw: Any) -> Any:  # type: ignore[misc]
                result = await fn(*args, **kw)
                client.clear_cache()
                return result

        return mcp.tool(annotations=annotations, **kwargs)(target)

    return decorator


def _register_tools() -> None:
    # Importing each module runs the @tool / @mcp.prompt decorators.
    from . import prompts  # noqa: F401
    from .tools import (  # noqa: F401
        attachments,
        cmr,
        companies,
        elements,
        experiments,
        generic,
        instruments,
        inventory,
        maintenance,
        projects,
        protocols,
        reports,
        search,
        shopping,
        stocks,
    )


def build_server() -> FastMCP:
    """Register all tools and prompts and return the configured FastMCP server."""
    _register_tools()
    return mcp


def main() -> None:
    """Console entry point: run the server over stdio."""
    if not settings.has_auth():
        print(
            "WARNING: No Labguru credentials found. Set LABGURU_TOKEN, or "
            "LABGURU_LOGIN and LABGURU_PASSWORD, in the environment or a .env file.",
            file=sys.stderr,
        )
    if settings.read_only:
        print("Labguru MCP: read-only mode (write tools disabled).", file=sys.stderr)
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
