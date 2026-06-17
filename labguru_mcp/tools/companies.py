"""Company / manufacturer / supplier tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..app import client, tool

API = "/api/v1"


def _company_email(company: Dict[str, Any]) -> Optional[str]:
    email = company.get("email")
    if isinstance(email, dict):
        return email.get("value")
    return email


@tool()
async def list_companies(
    limit: int = 50, search: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List companies (manufacturers / suppliers), optionally filtered by name.

    Args:
        limit: Maximum number of companies to return (default 50).
        search: Optional case-insensitive name substring filter.
    """
    raw = await client.paginate(f"{API}/companies.json", limit=None if search else limit)
    companies = [
        {"id": c.get("id"), "name": c.get("name"), "email": _company_email(c)}
        for c in raw
    ]
    if search:
        q = search.lower()
        companies = [c for c in companies if q in (c["name"] or "").lower()]
    return companies[:limit]


@tool()
async def get_company(company_id: int) -> Dict[str, Any]:
    """Get a single company by ID.

    Args:
        company_id: Numeric Labguru company ID.
    """
    return await client.get(f"{API}/companies/{company_id}.json")
