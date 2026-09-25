# AGENTS.md — NetBird management API

Read-only client for the self-hosted NetBird management API. The server is
deployed by `rctc-linux-ansible` (`roles/netbird_server`, host `netbird-mvp`).
Design context is in `rctc-net-vpn`.

## Hard rules

- Secrets stay in `.env`. Never commit a personal access token, owner password,
  or dashboard hostname that is not already public in another repo.
- Authenticate with a **service-user PAT**: `Authorization: Token <pat>`.
  Do not use the owner password or a browser session cookie.
- The API base is `<dashboard origin>/api` on that host. Do not call
  `api.netbird.io`.
- This package is **GET-only**. Do not add POST, PUT, PATCH, or DELETE until
  an operator asks for a specific write and this file is updated in the same
  change.
- TLS verification stays on. The edge certificate is Let's Encrypt via the
  Ansible role. Do not default `NETBIRD_VERIFY_TLS` to false.
- `probe` is the first live call. It authenticates with `GET /api/accounts`.
  `GET /api/users/current` returns 403 for service users. Do not switch the
  base URL to port 33073 — that port is for the multi-container guide and is
  not published here.
- Collect peers and audit events only. Do not call `/api/users` to build a
  user index. Initiator name and email on an audit event are already on the
  event. A peer's `user_id` may be stored; do not join it to a user record.
- Peer bronze (`logs-netbird.peer-*`) is append-only. The current index is
  replaced only after a non-empty full pull. Never delete it on an empty
  result or a `--max-peers` sample. The same pull rebuilds
  `netbird-peer-lookup` (`index.mode: lookup`) so ES|QL can `LOOKUP JOIN` on
  `source.ip`. Do not point that join at `netbird-peer-current`.
- Audit events are inserted with `_id` = the NetBird event id and `op_type`
  create. A repeat pull must not duplicate or delete them. There is no
  current-index replacement for audit.
- Drop credential-shaped audit meta (`key`, and keys containing password,
  token, secret, private, credential, authorization). Setup-key material is
  in meta key `key`.

## Layout

```
src/netbird_api/client.py    Token auth, GET, path checks
src/netbird_api/ecs.py       Peer state and audit event documents
src/netbird_api/elastic.py   Templates, peer snapshot, audit insert
src/netbird_api/cli.py       probe, get, export, index
src/netbird_api/config.py    .env
```
