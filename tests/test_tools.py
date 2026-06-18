"""
Tool-level tests against an in-memory fake Labguru API (httpx.MockTransport).

No token or network needed. Each test installs the mock transport onto the
shared client singleton, then calls the tool functions directly.

Run with:  python -m pytest tests/test_tools.py  (or)  python tests/test_tools.py
"""

from __future__ import annotations

import asyncio
import datetime
import json
import math
import os
import re
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import labguru_mcp.app as app  # noqa: E402
from labguru_mcp.errors import LabguruError  # noqa: E402

# Tool modules (importing registers them; we call the functions directly).
from labguru_mcp import resources as R  # noqa: E402
from labguru_mcp.tools import (  # noqa: E402
    cmr,
    companies,
    experiments as E,
    inventory as INV,
    projects as P,
    shopping as SH,
    stocks as ST,
)

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    {
        "id": 11,
        "title": "Old experiment",
        "start_date": "2026-01-05 10:00",
        "project_id": 3,
        "uuid": "u11",
        "member": {"name": "Alice"},
        "experiment_procedures": [],
    },
    {
        "id": 12,
        "title": "Mid experiment",
        "start_date": "2026-03-10 10:00",
        "project_id": 3,
        "uuid": "u12",
        "member": {"name": "Bob"},
        "protocol_id": 1,
        "experiment_procedures": [
            {"experiment_procedure": {"id": 1, "name": "Procedure A",
                                      "elements": [{"element_type": "samples", "id": 501, "uuid": "el-501"}]}}
        ],
    },
    {
        "id": 13,
        "title": "New experiment",
        "start_date": "2026-06-15 10:00",
        "project_id": 7,
        "uuid": "u13",
        "member": {"name": "Carol"},
        "experiment_procedures": [],
    },
]

ELEMENTS = {
    501: {
        "samples": [
            {
                "name": "PFA 4%",
                "collection_name": "SP BIOCHes",
                "itemsKey": "stocks",
                "saved_stocks_ids": [900],
                "stocks": [
                    {"id": 900, "name": "PFA", "lot": "L1", "expiration_date": "2026-06-20",
                     "auto_name": "SB-23.0002"}
                ],
            }
        ]
    }
}

INVENTORY = {
    "biochemistry": [
        {"id": 268, "name": "ACETIC ACID", "auto_name": "BI-23.0001", "catalog_number": "A1",
         "manufacturer": {"name": "SIGMA", "url": "/c/1"}, "web_page": {"url": "http://sds/acetic"}},
        {"id": 269, "name": "CMR CHEMICAL", "auto_name": "BI-23.0009", "custom5": "Carc. 1A",
         "custom6": "Use gloves", "web_page": {"url": "http://sds/cmr"}},
    ],
    "sp_bioch": [
        {"id": 50, "name": "PFA 4%", "auto_name": "SB-23.0002", "custom3": "Carc. 1B", "custom4": "Fume hood"},
    ],
}

STOCKS = [
    {"id": 900, "name": "PFA", "lot": "L1", "expiration_date": "2026-06-20",
     "inventory_item_id": 50, "storage_location": {"name": "Fridge A"}, "volume": 50, "volume_unit": "mL"},
    {"id": 901, "name": "Expired thing", "lot": "L0", "expiration_date": "2026-05-01"},
    {"id": 902, "name": "Far future", "lot": "L9", "expiration_date": "2027-01-01"},
    {"id": 903, "name": "No expiry", "lot": "L8"},
]

SHOPPING = [
    {"order_number": "PO-1", "name": "Tubes", "price": 10, "quantity": 2, "requested_at": "2026-06-01",
     "approved_at": "2026-06-02", "Delivery fee (€)": 5, "material": {"catalog_number": "T-1"}},
    {"order_number": "PO-1", "name": "Pipettes", "price": 4, "quantity": 1, "requested_at": "2026-06-01",
     "material": {"catalog_number": "P-1"}},
    {"order_number": "PO-2", "name": "Gloves", "price": 3, "quantity": 10, "requested_at": "2026-06-10",
     "submited_at": "2026-06-11", "material": {"catalog_number": "G-1"}},
]

PROJECTS = [
    {"id": 3, "name": "Neuro Project", "uuid": "p3"},
    {"id": 7, "name": "Glia Project", "uuid": "p7"},
]

COMPANIES = [
    {"id": 211, "name": "SIGMA-ALDRICH", "email": {"value": "orders@sigma.com"}},
    {"id": 212, "name": "Bio-Rad", "email": "sales@biorad.com"},
]


# ---------------------------------------------------------------------------
# Fake API
# ---------------------------------------------------------------------------

def _paged(items, params):
    page = int(params.get("page", 1))
    per = int(params.get("per_page", 200)) or 200
    # Kendo sort by id, if requested.
    if params.get("sort[0][field]") == "id":
        reverse = params.get("sort[0][dir]", "desc") != "asc"
        items = sorted(items, key=lambda x: x.get("id") or 0, reverse=reverse)
    chunk = items[(page - 1) * per:(page - 1) * per + per]
    if params.get("meta") == "true":
        page_count = max(1, math.ceil(len(items) / per)) if per else 1
        return httpx.Response(200, json={
            "data": chunk,
            "meta": {"page": page, "page_size": per, "page_count": page_count,
                     "item_count": len(items)},
        })
    return httpx.Response(200, json=chunk)


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    params = request.url.params

    if path == "/api/v1/sessions.json":
        return httpx.Response(200, json={"token": "session-token"})
    if path == "/api/v1/experiments.json":
        items = EXPERIMENTS
        pid = params.get("project_id")
        if pid is not None:
            items = [e for e in items if str(e.get("project_id")) == str(pid)]
        return _paged(items, params)
    m = re.match(r"^/api/v1/experiments/(\d+)\.json$", path)
    if m:
        exp = next((e for e in EXPERIMENTS if e["id"] == int(m.group(1))), None)
        return httpx.Response(200, json=exp) if exp else httpx.Response(404, json={})
    m = re.match(r"^/api/v1/elements/(\d+)\.json$", path)
    if m:
        eid = int(m.group(1))
        data = ELEMENTS.get(eid)
        body = {"id": eid, "element_type": "samples"}
        if data is not None:
            body["data"] = json.dumps(data)
        return httpx.Response(200, json=body)
    m = re.match(r"^/api/v1/biocollections/([a-z_]+)\.json$", path)
    if m:
        return _paged(INVENTORY.get(m.group(1), []), params)
    m = re.match(r"^/api/v1/(antibodies|cell_lines|plasmids|primers)\.json$", path)
    if m:
        return _paged(INVENTORY.get(m.group(1), []), params)
    if path == "/api/v1/stocks.json":
        return _paged(STOCKS, params)
    if path == "/api/v1/shopping_list.json":
        return _paged(SHOPPING, params)
    if path == "/api/v1/projects.json":
        return _paged(PROJECTS, params)
    if path == "/api/v1/companies.json":
        return _paged(COMPANIES, params)
    return httpx.Response(404, json={"error": f"unhandled {path}"})


def _install() -> None:
    """Point the shared client at the fake API and reset its state."""
    app.client._transport = httpx.MockTransport(handler)
    app.client._http = None
    app.client._token = "test-token"
    app.client._cache.clear()
    app.client._obj_cache.clear()
    app.settings.cache_ttl = 0  # deterministic: no cross-test caching


async def _call(toolobj, *args, **kwargs):
    fn = getattr(toolobj, "fn", toolobj)
    return await fn(*args, **kwargs)


def run(coro):
    _install()
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------

def test_list_experiments_recency():
    rows = run(_call(E.list_experiments, limit=10))
    assert [r["id"] for r in rows] == [13, 12, 11]  # newest first
    assert rows[0]["owner"] == "Carol"


def test_list_experiments_oldest_first():
    rows = run(_call(E.list_experiments, limit=10, oldest_first=True))
    assert [r["id"] for r in rows] == [11, 12, 13]


def test_list_experiments_by_project():
    rows = run(_call(E.list_experiments, project_id=3))
    assert {r["project_id"] for r in rows} == {3}
    assert [r["id"] for r in rows] == [12, 11]


def test_list_experiments_date_filter():
    rows = run(_call(E.list_experiments, since="2026-03-01", until="2026-03-31"))
    assert [r["id"] for r in rows] == [12]


def test_count_experiments():
    assert run(_call(E.count_experiments))["count"] == 3


def test_get_experiment():
    exp = run(_call(E.get_experiment, 12))
    assert exp["id"] == 12
    assert exp["procedures"] == [{"id": 1, "name": "Procedure A"}]


def test_get_experiment_samples():
    samples = run(_call(E.get_experiment_samples, 12))
    assert len(samples) == 1
    assert samples[0]["sys_id"] == "SB-23.0002"
    assert samples[0]["stock_ids"] == [900]


def test_get_experiment_stock_ids():
    assert run(_call(E.get_experiment_stock_ids, 12)) == [900]


def test_get_experiments_in_range():
    rows = run(_call(E.get_experiments_in_range, 11, 13))
    assert [r["id"] for r in rows] == [11, 12, 13]


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def test_list_inventory():
    rows = run(_call(INV.list_inventory, "biochemistry"))
    assert {r["sys_id"] for r in rows} == {"BI-23.0001", "BI-23.0009"}
    assert rows[0]["manufacturer"] in ("SIGMA", None)


def test_search_inventory():
    rows = run(_call(INV.search_inventory, "cmr", "biochemistry"))
    assert [r["sys_id"] for r in rows] == ["BI-23.0009"]


def test_find_item_by_sysid():
    item = run(_call(INV.find_item_by_sysid, "SB-23.0002"))
    assert item is not None
    assert item["collection"] == "sp_bioch"


def test_find_item_by_sysid_missing():
    assert run(_call(INV.find_item_by_sysid, "ZZ-99.9999")) is None


def test_get_cmr_items():
    items = run(_call(INV.get_cmr_items))
    by_sysid = {i["sys_id"]: i for i in items}
    assert set(by_sysid) == {"BI-23.0009", "SB-23.0002"}
    assert by_sysid["BI-23.0009"]["type_of_risk"] == "Carc. 1A"
    assert by_sysid["SB-23.0002"]["type_of_risk"] == "Carc. 1B"


def test_get_safety_links():
    links = run(_call(INV.get_safety_links, "biochemistry"))
    urls = {row["url"] for row in links}
    assert "http://sds/acetic" in urls and "http://sds/cmr" in urls


def test_invalid_collection_raises():
    try:
        run(_call(INV.list_inventory, "not_a_collection"))
    except LabguruError as exc:
        assert "Unknown collection" in str(exc)
    else:
        raise AssertionError("expected LabguruError for unknown collection")


# ---------------------------------------------------------------------------
# Stocks
# ---------------------------------------------------------------------------

def test_list_stocks():
    rows = run(_call(ST.list_stocks, limit=10))
    assert {r["id"] for r in rows} == {900, 901, 902, 903}


def test_expiring_stocks():
    class _FakeDate:
        @classmethod
        def today(cls):
            return datetime.date(2026, 6, 18)

    original = ST.date
    ST.date = _FakeDate
    try:
        rep = run(_call(ST.expiring_stocks, within_days=30))
        assert rep["scanned"] == 4
        assert rep["expired_count"] == 1
        assert [s["stock_id"] for s in rep["stocks"]] == [900]  # only the soon-to-expire one
        rep2 = run(_call(ST.expiring_stocks, within_days=30, include_expired=True))
        assert {s["stock_id"] for s in rep2["stocks"]} == {900, 901}
    finally:
        ST.date = original


# ---------------------------------------------------------------------------
# Shopping / CMR / projects / companies
# ---------------------------------------------------------------------------

def test_list_shopping_items_status_filter():
    submitted = run(_call(SH.list_shopping_items, "submitted"))
    assert [i["order_number"] for i in submitted] == ["PO-2"]


def test_order_summary_financials():
    summary = run(_call(SH.get_order_summary, "PO-1"))
    assert summary["item_count"] == 2
    assert summary["subtotal"] == 24.0  # 10*2 + 4*1
    assert summary["delivery_fee"] == 5.0
    assert summary["grand_total"] == 29.0


def test_cmr_experiment_report():
    rep = run(_call(cmr.cmr_experiment_report, 11, 13))
    assert rep["scanned"] == 3
    assert rep["with_cmr"] == 1
    assert rep["rows"][0]["experiment_id"] == 12
    assert rep["rows"][0]["cmr_products"][0]["sys_id"] == "SB-23.0002"


def test_list_projects_search():
    rows = run(_call(P.list_projects, search="glia"))
    assert [r["id"] for r in rows] == [7]


def test_list_companies_email_normalised():
    rows = run(_call(companies.list_companies))
    by_id = {c["id"]: c for c in rows}
    assert by_id[211]["email"] == "orders@sigma.com"
    assert by_id[212]["email"] == "sales@biorad.com"


# ---------------------------------------------------------------------------
# Resources & read-only decorator
# ---------------------------------------------------------------------------

def test_experiment_resource():
    txt = run(_call(R.experiment_resource, "12"))
    data = json.loads(txt)
    assert data["id"] == 12


def test_readonly_hides_write_tools():
    original = app.settings.read_only
    app.settings.read_only = True
    try:
        def my_writer():
            return None

        result = app.tool(write=True)(my_writer)
        assert result is my_writer  # not registered/wrapped in read-only mode
    finally:
        app.settings.read_only = original


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
