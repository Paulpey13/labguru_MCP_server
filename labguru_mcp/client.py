"""
labguru_mcp.client
------------------
Async HTTP client for the Labguru REST API.

Handles authentication (personal token or email/password exchanged for a
session token), automatic re-authentication on HTTP 401, pagination, bounded
concurrent fan-out, and typed error mapping. The token is sent as the ``token``
query parameter on GET/DELETE and inside the JSON body on POST/PUT, per the
Labguru convention.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from .config import Settings
from .errors import AuthError, LabguruError
from .formatting import extract_list


class LabguruClient:
    """Async client bound to a :class:`~labguru_mcp.config.Settings` instance."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._token: Optional[str] = settings.token
        self._lock = asyncio.Lock()
        self._http: Optional[httpx.AsyncClient] = None

    # -- lifecycle ----------------------------------------------------------

    def http(self) -> httpx.AsyncClient:
        # Created lazily so it binds to the active event loop.
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.settings.base_url,
                timeout=httpx.Timeout(self.settings.timeout),
                headers={"Accept": "application/json"},
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # -- auth ---------------------------------------------------------------

    async def _authenticate(self) -> str:
        s = self.settings
        if not (s.login and s.password):
            raise AuthError(
                "No token configured and credentials are incomplete. Set "
                "LABGURU_TOKEN, or LABGURU_LOGIN and LABGURU_PASSWORD."
            )
        resp = await self.http().post(
            "/api/v1/sessions.json",
            json={"login": s.login, "password": s.password},
        )
        if resp.status_code == 401:
            raise AuthError("Invalid email or password.")
        resp.raise_for_status()
        data = resp.json()
        token = data.get("token") or (data.get("data") or {}).get("token")
        if not token:
            raise AuthError(f"Login returned no token: {resp.text[:200]}")
        self._token = token
        return token

    async def ensure_token(self) -> str:
        async with self._lock:
            if self._token:
                return self._token
            return await self._authenticate()

    def token_hint(self) -> str:
        return (self._token[:6] + "...") if self._token else ""

    # -- response handling --------------------------------------------------

    @staticmethod
    def _check(resp: httpx.Response) -> Any:
        code = resp.status_code
        if code == 404:
            raise LabguruError(f"Not found: {resp.request.url}")
        if code == 422:
            raise LabguruError(f"Validation error (422): {resp.text[:300]}")
        if code == 429:
            raise LabguruError("Rate limit reached (429). Slow down requests.")
        if code >= 500:
            raise LabguruError(f"Server error ({code}): {resp.text[:300]}")
        resp.raise_for_status()
        if not resp.text:
            return {}
        try:
            return resp.json()
        except ValueError:
            return resp.text

    # -- core request -------------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Authenticated request. Retries once after re-auth on HTTP 401."""
        token = await self.ensure_token()
        method_up = method.upper()

        async def _do(tok: str) -> httpx.Response:
            p = {k: v for k, v in (params or {}).items() if v is not None}
            b = dict(json_body or {})
            if method_up in ("GET", "DELETE"):
                p["token"] = tok
            else:
                b["token"] = tok
            return await self.http().request(
                method_up, path, params=p or None, json=b or None
            )

        resp = await _do(token)
        if resp.status_code == 401:
            async with self._lock:
                self._token = None
            s = self.settings
            if s.login and s.password:
                token = await self.ensure_token()
                resp = await _do(token)
            else:
                raise AuthError(
                    "Authentication failed (401). Token invalid or expired and "
                    "no LABGURU_LOGIN/LABGURU_PASSWORD available for re-auth."
                )
        return self._check(resp)

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, payload: Dict[str, Any]) -> Any:
        return await self.request("POST", path, json_body=payload)

    async def put(self, path: str, payload: Dict[str, Any]) -> Any:
        return await self.request("PUT", path, json_body=payload)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)

    async def get_bytes(self, path: str, **params: Any) -> bytes:
        """GET raw binary content (file downloads)."""
        token = await self.ensure_token()
        p = {k: v for k, v in params.items() if v is not None}
        p["token"] = token
        resp = await self.http().get(path, params=p)
        resp.raise_for_status()
        return resp.content

    async def post_multipart(
        self, path: str, data: Dict[str, Any], files: Dict[str, Any]
    ) -> Any:
        """POST multipart/form-data (file uploads)."""
        token = await self.ensure_token()
        payload = {"token": token, **data}
        resp = await self.http().post(path, data=payload, files=files, timeout=120.0)
        if resp.status_code not in (200, 201):
            raise LabguruError(f"Upload failed ({resp.status_code}): {resp.text[:300]}")
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}

    # -- pagination & concurrency ------------------------------------------

    async def paginate(
        self,
        path: str,
        *,
        per_page: int = 200,
        limit: Optional[int] = None,
        **extra: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch all pages and return a flat list.

        Stops when a page is empty or shorter than ``per_page``. When ``limit``
        is set, stops once that many items are collected (and shrinks the page
        size for small limits to issue a single request).
        """
        if limit is not None and limit < per_page:
            per_page = max(1, limit)

        results: List[Dict[str, Any]] = []
        page = 1
        while True:
            raw = await self.get(path, page=page, per_page=per_page, **extra)
            batch = extract_list(raw)
            if not batch:
                break
            results.extend(batch)
            if limit is not None and len(results) >= limit:
                return results[:limit]
            if len(batch) < per_page:
                break
            page += 1
        return results

    async def gather(
        self, coros: List[Any], concurrency: Optional[int] = None
    ) -> List[Any]:
        """Run coroutines with bounded concurrency, preserving order.

        Exceptions are returned in place (not raised) so partial failures in a
        fan-out do not abort the whole batch.
        """
        limit = concurrency or self.settings.max_concurrency
        sem = asyncio.Semaphore(max(1, limit))

        async def _bounded(coro: Any) -> Any:
            async with sem:
                return await coro

        return await asyncio.gather(*[_bounded(c) for c in coros], return_exceptions=True)
