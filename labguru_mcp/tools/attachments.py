"""Attachment tools: list, metadata, download, upload."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..app import client, tool
from ..errors import LabguruError

API = "/api/v1"


@tool()
async def list_attachments(
    attachable_type: Optional[str] = None,
    attachable_id: Optional[int] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List attachments, optionally filtered by parent object.

    Args:
        attachable_type: Parent type, e.g. "Experiment", "Protocol".
        attachable_id: Parent object ID.
        limit: Maximum number of attachments to return (default 50).
    """
    params: Dict[str, Any] = {}
    if attachable_type is not None:
        params["attachable_type"] = attachable_type
    if attachable_id is not None:
        params["attachable_id"] = attachable_id
    raw = await client.paginate(f"{API}/attachments.json", limit=limit, **params)
    return [
        {
            "id": a.get("id"),
            "filename": a.get("attachment_file_name") or a.get("title"),
            "attachable_type": a.get("attachable_type"),
            "attachable_id": a.get("attachable_id"),
        }
        for a in raw
    ]


@tool()
async def get_attachment(attachment_id: int) -> Dict[str, Any]:
    """Get a single attachment's metadata by ID.

    Args:
        attachment_id: Numeric Labguru attachment ID.
    """
    return await client.get(f"{API}/attachments/{attachment_id}.json")


@tool()
async def download_attachment(attachment_id: int, save_path: str) -> Dict[str, Any]:
    """Download an attachment's binary content to a local file.

    Args:
        attachment_id: Numeric Labguru attachment ID.
        save_path: Local filesystem path to write the file to.

    Returns the saved path and byte count.
    """
    content = await client.get_bytes(f"{API}/attachments/{attachment_id}/download")
    with open(save_path, "wb") as fh:
        fh.write(content)
    return {"saved_to": save_path, "bytes": len(content)}


@tool(write=True)
async def upload_attachment(
    file_path: str,
    attachable_type: Optional[str] = None,
    attachable_id: Optional[int] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload a local file and attach it to a Labguru object. (Write operation.)

    Args:
        file_path: Path to the local file to upload.
        attachable_type: Parent type, e.g. "Experiment".
        attachable_id: Parent object ID.
        title: Optional display title.
    """
    if not os.path.exists(file_path):
        raise LabguruError(f"File not found: {file_path}")
    data: Dict[str, Any] = {}
    if attachable_type:
        data["item[attachable_type]"] = attachable_type
    if attachable_id is not None:
        data["item[attachable_id]"] = str(attachable_id)
    if title:
        data["item[title]"] = title
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as fh:
        files = {"item[attachment]": (filename, fh.read())}
    return await client.post_multipart(f"{API}/attachments.json", data, files)
