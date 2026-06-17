# Labguru MCP Server

A modular, configurable [Model Context Protocol](https://modelcontextprotocol.io)
server that exposes the [Labguru](https://www.labguru.com) laboratory management
REST API as native LLM tools. Point any MCP client (Claude Code, Claude Desktop,
etc.) at it and ask questions or run workflows against your Labguru instance in
plain language.

Built with `FastMCP` + async `httpx`. Open source under the MIT license, so any
lab is free to use and adapt it.

- 63 tools across every Labguru domain (experiments, protocols, projects,
  inventory, stocks, elements, shopping list / PO, reports, companies,
  instruments, attachments, maintenance, plus CMR and safety helpers).
- Configurable per instance: domain, custom biocollections, CMR field mapping,
  timeouts, concurrency.
- Two auth modes: personal API token, or email/password (auto re-auth on expiry).
- Optional read-only mode that hides every write tool.

## Architecture

```
MCP_labguru/
  labguru_mcp/                package (importable, installable)
    config.py                 settings from env + optional JSON file
    client.py                 async HTTP client (auth, pagination, fan-out)
    formatting.py             pure payload-normalising helpers
    errors.py                 typed exceptions
    app.py                    builds settings + client + FastMCP; tool() decorator
    __main__.py               python -m labguru_mcp
    tools/                    one module per domain; importing registers tools
      experiments.py  protocols.py  projects.py  inventory.py  stocks.py
      elements.py  shopping.py  reports.py  companies.py  instruments.py
      attachments.py  maintenance.py  search.py  generic.py
  mcp_server.py               thin entry-point shim (back-compat)
  pyproject.toml              packaging + `labguru-mcp` console script
  .env.example                config template
  labguru.config.example.json optional JSON config template
  LICENSE                     MIT
```

Adding a tool = add a function decorated with `@tool()` (or `@tool(write=True)`)
in the relevant `tools/*.py` module. No registry to update; importing the module
registers it.

## Install

```bash
cd MCP_labguru
pip install -e .          # installs deps and the `labguru-mcp` command
# or, without installing the package:
pip install -r requirements.txt
```

Requires Python 3.10+.

## Configure

Copy `.env.example` to `.env` and fill it in (env vars and an optional
`labguru.config.json` are also supported; env vars win).

### Authentication (choose one)

- **Personal API token** (recommended): set `LABGURU_TOKEN`. Generate it in the
  Labguru UI under Account > API token.
- **Email + password**: set `LABGURU_LOGIN` and `LABGURU_PASSWORD`. They are
  exchanged for a session token via `POST /api/v1/sessions.json`, and the server
  re-authenticates automatically if the token expires (HTTP 401).

Run the `whoami` tool any time to confirm the active base URL and auth mode
(only a short token hint is shown, never the secret).

### Settings

| Variable | Purpose | Default |
|---|---|---|
| `LABGURU_TOKEN` / `LABGURU_API_KEY` | Personal API token | — |
| `LABGURU_LOGIN` / `LABGURU_PASSWORD` | Email + password fallback | — |
| `LABGURU_DOMAIN` | Instance domain (no scheme) | `eu.labguru.com` |
| `LABGURU_BASE_URL` | Full base URL, overrides `LABGURU_DOMAIN` | — |
| `LABGURU_READ_ONLY` | Hide all write tools | `false` |
| `LABGURU_TIMEOUT` | HTTP timeout (seconds) | `60` |
| `LABGURU_MAX_CONCURRENCY` | Max concurrent calls in fan-out scans | `8` |
| `LABGURU_BIOCOLLECTIONS` | Comma-separated biocollection slugs | built-in list |
| `LABGURU_DIRECT_INVENTORY` | Comma-separated direct inventory types | built-in list |
| `LABGURU_CMR_MAP` | JSON: per-collection CMR `risk`/`measure` fields | see below |
| `LABGURU_CONFIG` | Path to a JSON config file | `labguru.config.json` |

Adapting to your lab: if your instance uses different custom fields for CMR risk
classification, or has extra custom biocollections, set `LABGURU_CMR_MAP` and
`LABGURU_BIOCOLLECTIONS` rather than editing the code. The default CMR map is:

```json
{
  "biochemistry": { "risk": "custom5", "measure": "custom6" },
  "culture":      { "risk": "custom3", "measure": "custom4" },
  "sp_bioch":     { "risk": "custom3", "measure": "custom4" }
}
```

## Run

Register the server with your MCP client. A ready-made `.mcp.json` for Claude
Code is included:

```json
{
  "mcpServers": {
    "labguru": {
      "type": "stdio",
      "command": "python",
      "args": ["C:/Users/Paul/Documents/code/LABGURU/MCP_labguru/mcp_server.py"],
      "env": {}
    }
  }
}
```

If you installed the package you can use the console script instead:

```json
{ "mcpServers": { "labguru": { "type": "stdio", "command": "labguru-mcp" } } }
```

For local development / inspection:

```bash
mcp dev mcp_server.py     # MCP Inspector UI
python -m labguru_mcp     # plain stdio server
```

## Tools

| Domain | Tools |
|---|---|
| Experiments | `list_experiments`, `get_experiment`, `get_experiment_raw`, `get_experiment_samples`, `get_experiment_stock_ids`, `get_experiments_in_range`, `create_experiment`*, `update_experiment`* |
| Protocols | `list_protocols`, `get_protocol`, `search_protocols`, `find_protocols_with_sysid` |
| Projects | `list_projects`, `get_project`, `list_folders`, `create_project`*, `update_project`* |
| Inventory | `list_collections`, `list_inventory`, `search_inventory`, `get_inventory_item`, `get_collection_item`, `find_item_by_sysid`, `get_generic_item` |
| CMR / Safety | `get_cmr_items`, `get_safety_links` |
| Stocks | `list_stocks`, `get_stock`, `get_stock_by_barcode`, `create_stock`*, `update_stock`* |
| Elements / UUID | `get_element`, `get_element_by_uuid`, `get_element_rows`, `resolve_uuid`, `list_sections`, `update_element`*, `create_element`*, `create_section`* |
| Shopping / PO | `list_shopping_items`, `get_order`, `get_order_summary`, `get_last_order`, `add_shopping_item`* |
| Reports | `list_reports`, `get_report`, `create_report`*, `update_report`*, `tag_report`* |
| Companies | `list_companies`, `get_company` |
| Instruments | `list_instruments`, `get_instrument`, `post_measurement`* |
| Attachments | `list_attachments`, `get_attachment`, `download_attachment`, `upload_attachment`* |
| Maintenance | `list_maintenance_events` |
| Cross-resource | `global_search` |
| Generic / introspection | `api_request`*, `whoami`, `list_capabilities` |

`*` = write tool, hidden when `LABGURU_READ_ONLY=true`.

`api_request` is an escape hatch for any endpoint without a dedicated tool; the
auth token is injected automatically. `list_capabilities` reports the live
configuration (collections, CMR map, registered tools).

## Notes

- List tools return slim summaries to keep payloads small; use the matching
  `get_*` / `*_raw` tool for the full JSON of a single record.
- Pagination is handled internally (`page` / `per_page`), stopping when a page
  is empty or shorter than the page size. Wrapped responses (`value`, `data`,
  ...) are unwrapped automatically.
- Fan-out scans (`get_experiments_in_range`, `find_protocols_with_sysid`,
  `find_item_by_sysid`, `get_cmr_items`, `get_safety_links`, `global_search`)
  use bounded concurrency and can be slow on large instances.
- The server never writes to stdout (it would corrupt the JSON-RPC stream);
  warnings go to stderr.

## License

MIT (c) 2026 Paul Peyssard, Neuro-Sys. See [LICENSE](LICENSE).
