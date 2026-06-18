# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses semantic
versioning.

## [1.0.0]

First public release.

### Features

- 67 tools, 4 prompts, and 4 resources covering experiments, protocols,
  projects, inventory/biocollections, stocks, elements, the shopping list /
  purchase orders, reports, companies, instruments, attachments, maintenance,
  plus CMR (Chemical Material Registry) and safety-data-sheet helpers.
- Two authentication modes: personal API token, or email/password exchanged for
  a session token with automatic re-authentication on HTTP 401.
- Configurable per instance: domain, custom biocollections, CMR custom-field
  mapping, timeouts, concurrency, cache TTL, and retry policy (env vars or a
  JSON config file).
- Read-only mode (`LABGURU_READ_ONLY`) that hides every write tool, and
  machine-readable read/write tool annotations.
- Recency-ordered listings via the Kendo grid sort, date-range filtering
  (`since`/`until`) for experiments, and `count_*` helpers using metadata.
- End-to-end `cmr_experiment_report` and `expiring_stocks` workflows.
- Performance: in-memory TTL cache for full-collection scans and per-element
  fetches, and parallel pagination driven by response metadata.
- Resilience: retry with exponential backoff on 429/5xx/network errors.

### Security

- HTTP request logging is silenced by default so the `?token=` query parameter
  is never written to logs. Set `LABGURU_DEBUG=true` to re-enable verbose logs.

### Tooling

- Offline and mocked-HTTP test suites (no token or network required).
- GitHub Actions CI across Python 3.10-3.13.
