# NetBird API

Read-only client for the self-hosted NetBird management API on the Internet VPN host (`netbird-mvp`).

The management API is the same host as the dashboard, under `/api`. A personal access token is sent as `Authorization: Token <pat>`.

Deployment and the dashboard hostname live in `rctc-linux-ansible` (`docs/netbird.md`, `inventory/group_vars/netbird/`). Design notes live in `rctc-net-vpn`. The hostname in Ansible is still a placeholder, so set the real origin in `.env`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
```

Create a service user in the dashboard (**Team → Service Users**), issue a token, and put it in `NETBIRD_TOKEN`. The plain token is shown once. `NETBIRD_URL` is the dashboard origin, for example `https://vpn.example.edu`. The client appends `/api`.

## Commands

```bash
netbird-api probe
netbird-api export --only peers -o peers.ndjson
netbird-api export --only audit -o audit.ndjson
netbird-api index --dry-run
netbird-api index --install-templates
```

`probe` calls `GET /api/accounts` to confirm the token, then counts peers, users, groups, policies, and routes. The caller is the user row with `is_current`. NetBird returns 403 for `GET /api/users/current` when the token belongs to a service user. Indexing does not pull the user list.

This host publishes the API through Traefik on 443 at `/api`. Management port 33073 is for the multi-container advanced guide and is not exposed here.

`get` is GET-only. It accepts a path under `/api` (`peers`, `events/audit`).

## Elasticsearch

Two datasets, both ECS:

| Dataset | What a run does | Index |
|---|---|---|
| Peers | Appends one observation per peer, then replaces the current snapshot and the lookup index | `logs-netbird.peer-default`, `netbird-peer-current`, and `netbird-peer-lookup` |
| Audit | Inserts events by id. A later run leaves events already stored | `logs-netbird.audit` |

Peer `@timestamp` is the time of the pull. `netbird.last_seen` is when the peer last reached management. Audit `@timestamp` is the event time from NetBird. The initiator name and email are the fields already on the audit event.

An empty peer pull does not change the current snapshot. `--max-peers` refuses to replace that snapshot. Audit events are not deleted.

Set `ELASTIC_URL` and `ELASTIC_API_KEY` in `.env`. Run `index --install-templates` once, then schedule `index`:

```bash
*/15 * * * * cd /opt/rctc/repos/netbird-api && .venv/bin/netbird-api index
```

## Token

Use a service-user token for this repo. Owner and admin passwords stay in the Ansible vault. Do not commit `.env`.
