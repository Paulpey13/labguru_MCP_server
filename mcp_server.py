"""
mcp_server.py - entry point shim for the Labguru MCP server.

The implementation lives in the modular ``labguru_mcp`` package. This file
exists so existing ``.mcp.json`` configs that run ``python mcp_server.py``
keep working. Prefer ``python -m labguru_mcp`` or the ``labguru-mcp`` console
script when installing the package.
"""

from __future__ import annotations

import os
import sys

# Ensure the package directory is importable when run as a loose script.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from labguru_mcp.app import main  # noqa: E402

if __name__ == "__main__":
    main()
