"""Exception types raised by the Labguru MCP server."""

from __future__ import annotations


class LabguruError(RuntimeError):
    """Raised for any non-success Labguru API response or client misuse."""


class AuthError(LabguruError):
    """Raised when authentication is missing, invalid, or expired."""


class ReadOnlyError(LabguruError):
    """Raised when a write is attempted while the server is in read-only mode."""
