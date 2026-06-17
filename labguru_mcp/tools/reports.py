"""Knowledge base report tools (used for PO generation workflows)."""

from __future__ import annotations

from typing import Any, Dict, List

from ..app import client, tool

API = "/api/v1"


@tool()
async def list_reports(limit: int = 25) -> List[Dict[str, Any]]:
    """List knowledge base reports, most recent first.

    Args:
        limit: Maximum number of reports to return (default 25).
    """
    raw = await client.paginate(
        f"{API}/reports.json", limit=limit, sort="created_at", direction="desc"
    )
    return [
        {
            "id": r.get("id"),
            "title": r.get("title"),
            "report_type": r.get("report_type"),
            "created_at": r.get("created_at"),
            "owner_id": r.get("owner_id"),
        }
        for r in raw
    ]


@tool()
async def get_report(report_id: int) -> Dict[str, Any]:
    """Get a single report by ID.

    Args:
        report_id: Numeric Labguru report ID.
    """
    return await client.get(f"{API}/reports/{report_id}.json")


@tool(write=True)
async def create_report(title: str, report_type: str = "Report") -> Dict[str, Any]:
    """Create a new report. (Write operation.)

    Args:
        title: Report title.
        report_type: Labguru report type string (default "Report").
    """
    item = {"title": title, "report_type": report_type}
    return await client.post(f"{API}/reports", {"item": item})


@tool(write=True)
async def update_report(report_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update fields on a report (e.g. owner). (Write operation.)

    Args:
        report_id: Numeric report ID.
        fields: Attributes to change, e.g. {"owner_id": 5}.
    """
    return await client.put(f"{API}/reports/{report_id}", {"item": fields})


@tool(write=True)
async def tag_report(report_id: int, tag: str) -> Dict[str, Any]:
    """Attach a tag to a report. (Write operation.)

    Args:
        report_id: Numeric report ID.
        tag: Tag string to attach.
    """
    item = {
        "title": tag,
        "taggable_type": "Knowledgebase::Report",
        "taggable_id": report_id,
    }
    return await client.post(f"{API}/tags", {"item": item})
