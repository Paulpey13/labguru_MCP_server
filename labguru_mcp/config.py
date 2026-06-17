"""
labguru_mcp.config
------------------
Configuration for the Labguru MCP server.

Settings are resolved, in order of precedence:

1. Environment variables (and a ``.env`` file loaded automatically).
2. An optional JSON config file (``LABGURU_CONFIG`` path, or
   ``labguru.config.json`` next to the package).
3. Built-in defaults.

This makes the server reusable by any lab: custom biocollections, a custom
CMR (Chemical Material Registry) field mapping, the instance domain, timeouts,
concurrency, and a read-only safety switch are all configurable without
touching the code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Built-in defaults
# ---------------------------------------------------------------------------

DEFAULT_DOMAIN = "eu.labguru.com"

# Collections served through /api/v1/biocollections/{slug}.json
DEFAULT_BIOCOLLECTIONS: Tuple[str, ...] = (
    "biochemistry",
    "culture",
    "crispr",
    "mrna",
    "rodents",
    "sirna",
    "taqman",
    "sp_bioch",
)

# Collections served through /api/v1/{type}.json directly
DEFAULT_DIRECT_INVENTORY: Tuple[str, ...] = (
    "antibodies",
    "cell_lines",
    "plasmids",
    "primers",
)

# CMR custom-field mapping per collection: {collection: {"risk": field, "measure": field}}
DEFAULT_CMR_MAP: Dict[str, Dict[str, str]] = {
    "biochemistry": {"risk": "custom5", "measure": "custom6"},
    "culture": {"risk": "custom3", "measure": "custom4"},
    "sp_bioch": {"risk": "custom3", "measure": "custom4"},
}

# Keys Labguru uses to wrap list responses on some endpoints.
WRAPPER_KEYS: Tuple[str, ...] = (
    "value",
    "data",
    "items",
    "results",
    "experiments",
    "protocols",
    "projects",
    "stocks",
    "companies",
    "reports",
    "instruments",
    "generic_items",
    "maintenance_events",
)


# ---------------------------------------------------------------------------
# .env loading (no python-dotenv dependency required)
# ---------------------------------------------------------------------------

def _candidate_dirs() -> List[str]:
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(pkg_dir)
    return [os.getcwd(), project_dir, pkg_dir]


def load_dotenv() -> None:
    """Load KEY=VALUE pairs from the first ``.env`` found, without overriding
    variables already present in the environment."""
    for directory in _candidate_dirs():
        path = os.path.join(directory, ".env")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return


def _load_config_file() -> Dict[str, Any]:
    """Return the parsed JSON config file, or an empty dict if none exists."""
    explicit = os.environ.get("LABGURU_CONFIG", "").strip()
    candidates = [explicit] if explicit else []
    for directory in _candidate_dirs():
        candidates.append(os.path.join(directory, "labguru.config.json"))
    for path in candidates:
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return data
            except (ValueError, OSError):
                continue
    return {}


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_tuple(value: Any) -> Optional[Tuple[str, ...]]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    return tuple(s.strip() for s in str(value).split(",") if s.strip())


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    """Resolved runtime configuration for the server."""

    base_url: str = f"https://{DEFAULT_DOMAIN}"
    token: Optional[str] = None
    login: Optional[str] = None
    password: Optional[str] = None
    timeout: float = 60.0
    max_concurrency: int = 8
    read_only: bool = False
    biocollections: Tuple[str, ...] = DEFAULT_BIOCOLLECTIONS
    direct_inventory: Tuple[str, ...] = DEFAULT_DIRECT_INVENTORY
    cmr_map: Dict[str, Dict[str, str]] = field(default_factory=lambda: dict(DEFAULT_CMR_MAP))

    @property
    def all_collections(self) -> Tuple[str, ...]:
        return tuple(self.biocollections) + tuple(self.direct_inventory)

    def inventory_path(self, collection: str) -> str:
        """Return the API path for a collection, routing direct vs biocollection."""
        if collection in self.direct_inventory:
            return f"/api/v1/{collection}.json"
        return f"/api/v1/biocollections/{collection}.json"

    def has_auth(self) -> bool:
        return bool(self.token or (self.login and self.password))


def _resolve_base_url(cfg: Dict[str, Any]) -> str:
    base = os.environ.get("LABGURU_BASE_URL") or cfg.get("base_url")
    if base:
        return str(base).rstrip("/")
    domain = os.environ.get("LABGURU_DOMAIN") or cfg.get("domain") or DEFAULT_DOMAIN
    domain = str(domain).replace("https://", "").replace("http://", "").rstrip("/")
    return f"https://{domain}"


def load_settings() -> Settings:
    """Build a :class:`Settings` object from env vars and an optional config file."""
    load_dotenv()
    cfg = _load_config_file()

    biocollections = (
        _as_tuple(os.environ.get("LABGURU_BIOCOLLECTIONS"))
        or _as_tuple(cfg.get("biocollections"))
        or DEFAULT_BIOCOLLECTIONS
    )
    direct_inventory = (
        _as_tuple(os.environ.get("LABGURU_DIRECT_INVENTORY"))
        or _as_tuple(cfg.get("direct_inventory"))
        or DEFAULT_DIRECT_INVENTORY
    )

    cmr_map: Dict[str, Dict[str, str]] = dict(DEFAULT_CMR_MAP)
    raw_cmr = os.environ.get("LABGURU_CMR_MAP")
    cmr_source: Any = None
    if raw_cmr:
        try:
            cmr_source = json.loads(raw_cmr)
        except ValueError:
            cmr_source = None
    if cmr_source is None:
        cmr_source = cfg.get("cmr_map")
    if isinstance(cmr_source, dict):
        for collection, fields in cmr_source.items():
            if isinstance(fields, dict) and "risk" in fields and "measure" in fields:
                cmr_map[collection] = {"risk": fields["risk"], "measure": fields["measure"]}

    def _num(env: str, key: str, default: float) -> float:
        raw = os.environ.get(env) or cfg.get(key)
        try:
            return float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    return Settings(
        base_url=_resolve_base_url(cfg),
        token=(
            os.environ.get("LABGURU_TOKEN")
            or os.environ.get("LABGURU_API_KEY")
            or cfg.get("token")
            or None
        ),
        login=os.environ.get("LABGURU_LOGIN") or cfg.get("login"),
        password=os.environ.get("LABGURU_PASSWORD") or cfg.get("password"),
        timeout=_num("LABGURU_TIMEOUT", "timeout", 60.0),
        max_concurrency=int(_num("LABGURU_MAX_CONCURRENCY", "max_concurrency", 8)),
        read_only=_as_bool(
            os.environ.get("LABGURU_READ_ONLY", cfg.get("read_only")), default=False
        ),
        biocollections=biocollections,
        direct_inventory=direct_inventory,
        cmr_map=cmr_map,
    )
