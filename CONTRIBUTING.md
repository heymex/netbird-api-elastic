# Contributing

Thanks for your interest in improving `netbird-api`.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
```

## Running tests

```bash
.venv/bin/pytest
```

Tests use a fake transport — no live NetBird or Elasticsearch instance is needed.

## Project layout

```
src/netbird_api/client.py    Token auth, GET, path checks
src/netbird_api/ecs.py       Peer state and audit event documents
src/netbird_api/elastic.py   Templates, peer snapshot, audit insert
src/netbird_api/cli.py       probe, get, export, index
src/netbird_api/config.py    .env
src/netbird_api/templates.py Elasticsearch index templates
```

## How to extend

### Add a new activity code mapping

Edit `classify()` in `src/netbird_api/ecs.py`. Add the NetBird activity code
to the appropriate branch, or add a new branch if the code doesn't fit an
existing pattern. Add a test in `tests/test_ecs.py`.

### Add a new peer field to ECS

1. Add the field to `peer_document()` in `src/netbird_api/ecs.py`.
2. Add the mapping to `PEER_PROPERTIES` in `src/netbird_api/templates.py`.
3. Add a test in `tests/test_ecs.py`.

### Add a new API collection

1. Add a method to `NetBirdClient` in `src/netbird_api/client.py`.
2. Add a test in `tests/test_client.py`.

## Code style

- Python 3.11+
- Type hints on all public functions
- `from __future__ import annotations` at the top of each module
- Tests for all new behavior
