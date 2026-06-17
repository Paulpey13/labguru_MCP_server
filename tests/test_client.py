"""
Client-level tests using httpx.MockTransport (no network, no real token).

Covers token injection, pagination, caching, 401 re-auth, and retry/backoff.

Run with:  python -m pytest tests/test_client.py   (or)  python tests/test_client.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from labguru_mcp.client import LabguruClient
from labguru_mcp.config import Settings


def _client(handler, **overrides) -> LabguruClient:
    base = dict(
        base_url="https://test.labguru.com",
        token="tok",
        retry_base_delay=0.0,
        cache_ttl=300.0,
    )
    base.update(overrides)
    return LabguruClient(Settings(**base), transport=httpx.MockTransport(handler))


def _run(coro):
    return asyncio.run(coro)


def test_token_injected_in_query_for_get():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.url.params.get("token")
        return httpx.Response(200, json={"ok": True})

    c = _client(handler)
    result = _run(c.get("/api/v1/ping.json"))
    assert result == {"ok": True}
    assert seen["token"] == "tok"


def test_token_injected_in_body_for_post():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": 1})

    c = _client(handler)
    _run(c.post("/api/v1/things", {"item": {"name": "x"}}))
    assert seen["body"]["token"] == "tok"
    assert seen["body"]["item"] == {"name": "x"}


def test_pagination_stops_on_short_page():
    pages = {
        1: [{"id": i} for i in range(200)],
        2: [{"id": 200}, {"id": 201}],  # short page -> last
    }
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        page = int(request.url.params.get("page", 1))
        return httpx.Response(200, json=pages.get(page, []))

    c = _client(handler)
    items = _run(c.paginate("/api/v1/items.json", per_page=200))
    assert len(items) == 202
    assert calls["n"] == 2


def test_cached_paginate_hits_cache():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=[{"id": 1}])

    c = _client(handler)
    first = _run(c.cached_paginate("/api/v1/items.json", per_page=1000))
    second = _run(c.cached_paginate("/api/v1/items.json", per_page=1000))
    assert first == second == [{"id": 1}]
    assert calls["n"] == 1  # second call served from cache
    assert c.clear_cache() == 1
    _run(c.cached_paginate("/api/v1/items.json", per_page=1000))
    assert calls["n"] == 2  # refetched after clear


def test_paginate_passes_bracket_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=[{"id": 1}])

    c = _client(handler)
    from labguru_mcp.formatting import kendo_sort

    _run(c.paginate("/api/v1/x.json", per_page=5, params=kendo_sort("id", "desc")))
    assert seen["params"]["kendo"] == "true"
    assert seen["params"]["sort[0][field]"] == "id"
    assert seen["params"]["sort[0][dir]"] == "desc"


def test_count_reads_meta_item_count():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("meta") == "true"
        return httpx.Response(200, json={"data": [], "meta": {"item_count": 10972}})

    c = _client(handler)
    assert _run(c.count("/api/v1/experiments.json")) == 10972


def test_401_triggers_reauth_with_credentials():
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/sessions.json":
            return httpx.Response(200, json={"token": "good"})
        token = request.url.params.get("token")
        state["calls"] += 1
        if token == "bad":
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json={"ok": True})

    c = _client(handler, token="bad", login="me@lab.com", password="pw")
    result = _run(c.get("/api/v1/experiments.json"))
    assert result == {"ok": True}
    assert state["calls"] == 2  # one 401, one success after re-auth


def test_retry_on_429_then_success():
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        return httpx.Response(200, json={"ok": True})

    c = _client(handler, max_retries=3)
    result = _run(c.get("/api/v1/x.json"))
    assert result == {"ok": True}
    assert state["n"] == 2


def test_retry_exhausted_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    c = _client(handler, max_retries=2)
    try:
        _run(c.get("/api/v1/x.json"))
    except Exception as exc:  # LabguruError (ServerError mapped)
        assert "Server error" in str(exc) or "503" in str(exc)
    else:
        raise AssertionError("expected an error after retries exhausted")


def _run_all() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc!r}")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
