"""
Offline unit tests (no Labguru token or network required).

Run with:  python -m pytest        (or)  python tests/test_offline.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from labguru_mcp import config, formatting


def test_extract_list_variants():
    assert formatting.extract_list([{"a": 1}]) == [{"a": 1}]
    assert formatting.extract_list({"value": [{"a": 1}]}) == [{"a": 1}]
    assert formatting.extract_list({"data": [1, 2]}) == [1, 2]
    assert formatting.extract_list({"only": [9]}) == [9]
    assert formatting.extract_list({"x": 1, "y": 2}) == []
    assert formatting.extract_list("not a list") == []


def test_kendo_sort():
    s = formatting.kendo_sort("id", "desc")
    assert s == {"kendo": "true", "sort[0][field]": "id", "sort[0][dir]": "desc"}
    assert formatting.kendo_sort()["sort[0][dir]"] == "desc"


def test_safe_num():
    assert formatting.safe_num("3.5") == 3.5
    assert formatting.safe_num(None) == 0.0
    assert formatting.safe_num("oops", default=-1) == -1


def test_slim_inventory_normalises_manufacturer():
    item = {
        "id": 1,
        "name": "X",
        "auto_name": "BI-23.0001",
        "manufacturer": {"name": "SIGMA", "url": "/c/1"},
        "web_page": {"url": "https://example.com"},
    }
    slim = formatting.slim_inventory(item, "biochemistry")
    assert slim["manufacturer"] == "SIGMA"
    assert slim["manufacturer_url"] == "/c/1"
    assert slim["sys_id"] == "BI-23.0001"
    assert slim["url"] == "https://example.com"


def test_financial_summary():
    items = [
        {"price": 10, "quantity": 2, "Delivery fee (€)": 5},
        {"price": 4, "quantity": 1, "Dry ice (€)": 3},
    ]
    s = formatting.financial_summary(items)
    assert s["subtotal"] == 24.0
    assert s["delivery_fee"] == 5.0
    assert s["dry_ice"] == 3.0
    assert s["grand_total"] == 32.0


def test_shopping_status():
    assert formatting.shopping_status({"submited_at": "x"}) == "submitted"
    assert formatting.shopping_status({"approved_at": "x"}) == "approved"
    assert formatting.shopping_status({}) == "pending"


def test_iter_experiment_rows():
    exp = {
        "experiment_procedures": [
            {
                "experiment_procedure": {
                    "elements": [
                        {"rows": [{"item": {"name": "A"}}, {"item": {"name": "B"}}]}
                    ]
                }
            }
        ]
    }
    rows = formatting.iter_experiment_rows(exp)
    assert [r["name"] for r in rows] == ["A", "B"]


def test_settings_inventory_routing():
    s = config.Settings()
    assert s.inventory_path("antibodies") == "/api/v1/antibodies.json"
    assert s.inventory_path("biochemistry") == "/api/v1/biocollections/biochemistry.json"
    assert "biochemistry" in s.all_collections
    assert "antibodies" in s.all_collections


def test_settings_base_url_resolution(monkeypatch=None):
    # Direct construction keeps the default https scheme.
    s = config.Settings(base_url="https://my.labguru.com")
    assert s.base_url == "https://my.labguru.com"


def test_load_settings_respects_env():
    os.environ["LABGURU_DOMAIN"] = "demo.labguru.com"
    os.environ["LABGURU_READ_ONLY"] = "true"
    os.environ["LABGURU_CMR_MAP"] = '{"foo":{"risk":"c1","measure":"c2"}}'
    try:
        s = config.load_settings()
        assert s.base_url == "https://demo.labguru.com"
        assert s.read_only is True
        assert s.cmr_map["foo"] == {"risk": "c1", "measure": "c2"}
        # defaults are preserved alongside the override
        assert "biochemistry" in s.cmr_map
    finally:
        for key in ("LABGURU_DOMAIN", "LABGURU_READ_ONLY", "LABGURU_CMR_MAP"):
            os.environ.pop(key, None)


def _run_all():
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
