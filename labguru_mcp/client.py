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
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from .config import Settings
from .errors import AuthError, LabguruError
from .formatting import extract_list


class LabguruClient:
    """Async client bound to a :class:`~labguru_mcp.config.Settings` instance.

    Args:
        settings: Resolved configuration.
        transport: Optional ``httpx`` transport. Used by tests to inject a
            ``MockTransport``; ``None`` in production.
    """

    def __init__(
        self, settings: Settings, transport: Optional[httpx.AsyncBaseTransport] = None
    ) -> None:
        self.settings = settings
        self._token: Optional[str] = settings.token
        self._lock = asyncio.Lock()
        self._http: Optional[httpx.AsyncClient] = None
        self._transport = transport
        self._cache: Dict[Tuple[Any, ...], Tuple[float, List[Dict[str, Any]]]] = {}
        self._obj_cache: Dict[Tuple[Any, ...], Tuple[float, Any]] = {}

    # -- lifecycle ----------------------------------------------------------

    def http(self) -> httpx.AsyncClient:
        # Created lazily so it binds to the active event loop.
        if self._http is None:
            kwargs: Dict[str, Any] = dict(
                base_url=self.settings.base_url,
                timeout=httpx.Timeout(self.settings.timeout),
                headers={"Accept": "application/json"},
            )
            if self._transport is not None:
                kwargs["transport"] = self._transport
            self._http = httpx.AsyncClient(**kwargs)
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

    async def _send_with_retry(
        self, make_request: Callable[[], Any]
    ) -> httpx.Response:
        """Send a request, retrying transport errors and 429/5xx with backoff.

        HTTP 401 is intentionally returned (not retried) so the caller can run
        its re-authentication flow.
        """
        delay = self.settings.retry_base_delay
        attempts = max(0, self.settings.max_retries)
        last_exc: Optional[Exception] = None
        resp: Optional[httpx.Response] = None
        for attempt in range(attempts + 1):
            try:
                resp = await make_request()
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt >= attempts:
                    raise LabguruError(f"Network error after retries: {exc}") from exc
                await asyncio.sleep(delay)
                delay *= 2
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt >= attempts:
                    return resp
                retry_after = resp.headers.get("Retry-After", "")
                sleep_for = float(retry_after) if retry_after.isdigit() else delay
                await asyncio.sleep(sleep_for)
                delay *= 2
                continue
            return resp
        if resp is not None:
            return resp
        raise LabguruError(f"Request failed: {last_exc}")

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Authenticated request with retry/backoff and one 401 re-auth retry."""
        token = await self.ensure_token()
        method_up = method.upper()

        def _make(tok: str) -> Callable[[], Any]:
            def _do() -> Any:
                p = {k: v for k, v in (params or {}).items() if v is not None}
                b = dict(json_body or {})
                if method_up in ("GET", "DELETE"):
                    p["token"] = tok
                else:
                    b["token"] = tok
                return self.http().request(
                    method_up, path, params=p or None, json=b or None
                )

            return _do

        resp = await self._send_with_retry(_make(token))
        if resp.status_code == 401:
            async with self._lock:
                self._token = None
            s = self.settings
            if s.login and s.password:
                token = await self.ensure_token()
                resp = await self._send_with_retry(_make(token))
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
        params: Optional[Dict[str, Any]] = None,
        **extra: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch all pages and return a flat list.

        Stops when a page is empty or shorter than ``per_page``. When ``limit``
        is set, stops once that many items are collected (and shrinks the page
        size for small limits to issue a single request).

        Args:
            params: Extra query params as a dict. Use this for Rails/Kendo-style
                bracketed keys (e.g. ``sort[0][field]``) that cannot be passed as
                Python keyword arguments.
            **extra: Additional simple query params.
        """
        query = {**(params or {}), **extra}
        if limit is not None and limit < per_page:
            per_page = max(1, limit)

        results: List[Dict[str, Any]] = []
        page = 1
        # The API may silently cap per_page (e.g. stocks at 100). Detect the
        # effective page size from the first page instead of trusting per_page,
        # otherwise a capped first page looks like the last page.
        page_size: Optional[int] = None
        while True:
            raw = await self.request(
                "GET", path, params={**query, "page": page, "per_page": per_page}
            )
            batch = extract_list(raw)
            if not batch:
                break
            results.extend(batch)
            if limit is not None and len(results) >= limit:
                return results[:limit]
            if page_size is None:
                page_size = len(batch)
            if len(batch) < page_size:
                break
            page += 1
        return results

    async def count(self, path: str, **extra: Any) -> Optional[int]:
        """Return the total item count for a list endpoint via ``meta=true``.

        Issues a single cheap request. Returns ``None`` if the endpoint does not
        report a count.
        """
        raw = await self.request(
            "GET", path, params={**extra, "meta": "true", "page": 1, "per_page": 1}
        )
        if isinstance(raw, dict):
            meta = raw.get("meta") or {}
            if isinstance(meta, dict) and "item_count" in meta:
                return meta["item_count"]
        return None

    async def paginate_all(
        self,
        path: str,
        *,
        per_page: int = 200,
        **extra: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch every page of a list endpoint, in parallel when possible.

        Requests the first page with ``meta=true`` to learn the total page
        count, then fetches the remaining pages concurrently. Falls back to
        sequential pagination when the endpoint does not report ``page_count``.
        """
        first = await self.request(
            "GET", path, params={**extra, "meta": "true", "page": 1, "per_page": per_page}
        )
        batch = extract_list(first)
        results: List[Dict[str, Any]] = list(batch)
        meta = first.get("meta") if isinstance(first, dict) else None

        if not isinstance(meta, dict):
            # Endpoint has no usable meta: fall back to sequential paging.
            return await self.paginate(path, per_page=per_page, **extra)
        if not batch:
            return results

        # The server may cap per_page; use the page size it actually returned so
        # subsequent page numbers line up, and recompute the page count from it.
        page_size = meta.get("page_size") or len(batch)
        item_count = meta.get("item_count")
        if isinstance(item_count, int) and page_size:
            page_count = -(-item_count // page_size)  # ceil division
        else:
            page_count = meta.get("page_count")
        if not isinstance(page_count, int) or page_count <= 1:
            return results

        async def _page(p: int) -> List[Dict[str, Any]]:
            raw = await self.request(
                "GET", path, params={**extra, "meta": "true", "page": p, "per_page": page_size}
            )
            return extract_list(raw)

        pages = await self.gather([_page(p) for p in range(2, page_count + 1)])
        for r in pages:
            if isinstance(r, list):
                results.extend(r)
        return results

    async def cached_paginate(
        self,
        path: str,
        *,
        per_page: int = 200,
        **extra: Any,
    ) -> List[Dict[str, Any]]:
        """Like :meth:`paginate_all` but caches the full result for ``cache_ttl`` seconds.

        Intended for full-collection fetches reused across scan tools. Bypassed
        when ``cache_ttl`` is 0. Returns the cached list object directly, so
        callers must not mutate it in place.
        """
        ttl = self.settings.cache_ttl
        if ttl <= 0:
            return await self.paginate_all(path, per_page=per_page, **extra)

        key = (path, tuple(sorted(extra.items())))
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit is not None and (now - hit[0]) < ttl:
            return hit[1]
        result = await self.paginate_all(path, per_page=per_page, **extra)
        self._cache[key] = (now, result)
        return result

    async def cached_get(self, path: str, **params: Any) -> Any:
        """Like :meth:`get` but caches the parsed response for ``cache_ttl`` seconds.

        Intended for immutable-ish single resources fetched repeatedly across a
        report (experiment details, samples elements). Bypassed when
        ``cache_ttl`` is 0.
        """
        ttl = self.settings.cache_ttl
        if ttl <= 0:
            return await self.get(path, **params)
        key = ("GET", path, tuple(sorted(params.items())))
        now = time.monotonic()
        hit = self._obj_cache.get(key)
        if hit is not None and (now - hit[0]) < ttl:
            return hit[1]
        value = await self.get(path, **params)
        self._obj_cache[key] = (now, value)
        return value

    def clear_cache(self) -> int:
        """Drop all cached paginations and single-resource fetches.

        Returns the number of entries cleared.
        """
        count = len(self._cache) + len(self._obj_cache)
        self._cache.clear()
        self._obj_cache.clear()
        return count

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
