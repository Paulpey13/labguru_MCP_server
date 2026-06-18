# Contributing

Thanks for considering a contribution. This server is MIT-licensed and meant to
be reusable by any lab running Labguru.

## Development setup

```bash
git clone https://github.com/Paulpey13/labguru_MCP_server
cd labguru_MCP_server
python -m venv .venv && . .venv/bin/activate   # optional
pip install -e ".[dev]"
```

## Running the tests

No Labguru token or network access is required: the suites are fully offline
(pure helpers) and use `httpx.MockTransport` for the client.

```bash
pytest -q
# or run the files directly:
python tests/test_offline.py   # pure helpers and config
python tests/test_client.py    # HTTP client: auth, pagination, retries, cache
python tests/test_tools.py     # tools end-to-end against a fake Labguru API
```

## Project layout

```
labguru_mcp/
  config.py      settings (env + optional JSON file)
  client.py      async HTTP client (auth, pagination, retries, cache)
  formatting.py  pure payload-normalising helpers (easy to unit test)
  app.py         settings + client + FastMCP; the @tool decorator
  prompts.py     guided workflow prompts
  resources.py   addressable read-only resources
  tools/         one module per domain
```

## Adding a tool

1. Add an `async def` in the relevant `tools/<domain>.py` module.
2. Decorate it with `@tool()` for reads, or `@tool(write=True)` for writes
   (write tools are hidden in read-only mode and clear the cache after running).
3. Keep list tools returning slim summaries; expose full JSON via a `get_*`
   tool. Put any pure parsing logic in `formatting.py` and unit-test it.
4. Run `pytest` and, if you touched parsing/config/client logic, add a test.

## Guidelines

- Keep secrets out of code and logs (HTTP logging is silenced by default).
- Prefer configuration over hardcoding instance-specific values (collections,
  CMR fields, domain are all configurable).
- Match the existing style; `ruff check` should pass.
