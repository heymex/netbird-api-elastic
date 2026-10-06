# NetBird API

Read-only client for the self-hosted [NetBird](https://netbird.io) management API.
It collects peer state and audit events, maps them to [Elastic Common Schema (ECS)](https://www.elastic.co/guide/en/ecs/current/index.html)
documents, and indexes them into Elasticsearch for search and visualization.

## Requirements

- Python 3.11+
- A self-hosted NetBird instance (any recent version)
- Elasticsearch 8.x or 9.x (or OpenSearch with minor adjustments)

## How it works

The management API is served at `<dashboard>/api` on your NetBird host.
Authenticate with a **service-user personal access token** sent as
`Authorization: Token <pat>`.

The client pulls two datasets:

| Dataset | What a run does | Index |
|---|---|---|
| Peers | Appends one observation per peer to a data stream, then replaces the current snapshot and the lookup index | `logs-netbird.peer-default`, `netbird-peer-current`, `netbird-peer-lookup` |
| Audit | Inserts events by event id. A later run leaves events already stored | `logs-netbird.audit` |

Peer `@timestamp` is the time of the pull. `netbird.last_seen` is when the peer
last reached management. Audit `@timestamp` is the event time from NetBird.

An empty peer pull does not change the current snapshot. `--max-peers` refuses
to replace that snapshot. Audit events are never deleted.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
```

Create a service user in the NetBird dashboard (**Team → Service Users**),
issue a token, and put it in `NETBIRD_TOKEN`. The plain token is shown once.
`NETBIRD_URL` is your dashboard origin, for example `https://vpn.example.edu`.
The client appends `/api`.

## Configuration

All configuration is via environment variables or `.env`:

| Variable | Required | Default | Description |
|---|---|---|---|
| `NETBIRD_URL` | yes | — | Dashboard origin, e.g. `https://vpn.example.edu` |
| `NETBIRD_TOKEN` | yes | — | Service-user personal access token |
| `NETBIRD_VERIFY_TLS` | no | `true` | Verify TLS certificates |
| `NETBIRD_TIMEOUT` | no | `30` | HTTP timeout in seconds |
| `ELASTIC_URL` | for `index` | — | Elasticsearch URL, e.g. `https://localhost:9200` |
| `ELASTIC_API_KEY` | no | — | API key for Elasticsearch auth |
| `ELASTIC_USER` | no | — | Basic auth username (alternative to API key) |
| `ELASTIC_PASSWORD` | no | — | Basic auth password |
| `ELASTIC_VERIFY_TLS` | no | `true` | Verify Elasticsearch TLS certificates |
| `ELASTIC_PEER_BRONZE_INDEX` | no | `logs-netbird.peer-default` | Append-only peer data stream |
| `ELASTIC_PEER_CURRENT_INDEX` | no | `netbird-peer-current` | Current peer snapshot |
| `ELASTIC_PEER_LOOKUP_INDEX` | no | `netbird-peer-lookup` | Lookup-mode index for ES\|QL JOIN |
| `ELASTIC_AUDIT_INDEX` | no | `logs-netbird.audit` | Audit event index |

## Commands

```bash
# Confirm the token works and print collection counts
netbird-api probe

# GET one path under /api and print JSON
netbird-api get peers
netbird-api get events/audit

# Write ECS documents as newline-delimited JSON
netbird-api export --only peers -o peers.ndjson
netbird-api export --only audit -o audit.ndjson

# Index into Elasticsearch (map + bulk insert)
netbird-api index --dry-run
netbird-api index --install-templates
netbird-api index
```

`probe` calls `GET /api/accounts` to confirm the token, then counts peers,
users, groups, policies, and routes. The caller is the user row with
`is_current`. NetBird returns 403 for `GET /api/users/current` when the token
belongs to a service user.

`get` is GET-only. It accepts a path under /api (`peers`, `events/audit`).

### Index options

```bash
# Only index peers or audit events
netbird-api index --only peers
netbird-api index --only audit

# Skip the append-only data stream or the current snapshot
netbird-api index --no-bronze
netbird-api index --no-current

# Partial pull (does not replace the current snapshot)
netbird-api index --max-peers 10 --no-current

# Create or update index templates first
netbird-api index --install-templates
```

## Scheduling

Run `index` on a schedule to keep Elasticsearch current. Example cron entry:

```bash
*/5 * * * * cd /path/to/netbird-api && flock -n /tmp/netbird-api.lock \
  .venv/bin/netbird-api index \
  >> logs/index.log 2>&1
```

The `flock` prevents overlapping runs.

## Elasticsearch

### Index templates

Run `netbird-api index --install-templates` once to create the index templates.
They define ECS-compatible field mappings for peers and audit events.

### Peer data

Peer documents are stored in three places:

1. **Bronze** (`logs-netbird.peer-default`): append-only data stream with one
   document per peer per pull. Use this for time-series analysis.
2. **Current** (`netbird-peer-current`): the latest snapshot, replaced on each
   full pull. Use this for "what is the current state" queries.
3. **Lookup** (`netbird-peer-lookup`): a lookup-mode index rebuilt from the
   current snapshot. Use this for ES|QL `LOOKUP JOIN` to enrich other log
   sources with NetBird peer data.

### Audit data

Audit events are inserted with `_id` = the NetBird event id and `op_type`
create. A repeat pull does not duplicate them.

### Example ES|QL queries

See [`kibana/queries.esql`](kibana/queries.esql) for examples.

## OpenSearch

This project uses the `elasticsearch` Python client. To use OpenSearch instead,
replace it with `opensearch-py` in `pyproject.toml` and update the import in
`src/netbird_api/elastic.py`. The API is compatible for the operations used here.

## License

[MIT](LICENSE)
