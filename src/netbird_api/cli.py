from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone

from netbird_api.client import NetBirdClient, NetBirdError
from netbird_api.config import Settings
from netbird_api.ecs import audit_document, peer_document

_COLLECTIONS = ("peers", "users", "groups", "policies", "routes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="netbird-api",
        description="Read the self-hosted NetBird management API.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("probe", help="Confirm the token and print collection counts")

    get = sub.add_parser("get", help="GET one path under /api and print JSON")
    get.add_argument("path", help="Resource path, for example peers or events/audit")

    export = sub.add_parser("export", help="Write ECS documents as newline-delimited JSON")
    export.add_argument("--only", choices=["peers", "audit"], required=True)
    export.add_argument("-o", "--output", default="-", help="Output path, or - for stdout")
    export.add_argument("--max-peers", type=int, help="Stop after this many peers")

    index = sub.add_parser("index", help="Index peer snapshots and new audit events")
    index.add_argument("--only", choices=["peers", "audit"])
    index.add_argument("--dry-run", action="store_true", help="Map documents and print a count")
    index.add_argument("--no-bronze", action="store_true", help="Skip the append-only peer data stream")
    index.add_argument("--no-current", action="store_true", help="Skip the current peer snapshot")
    index.add_argument("--install-templates", action="store_true", help="Create or update index templates first")
    index.add_argument("--max-peers", type=int, help="Stop after this many peers. Refuses to replace the current snapshot.")

    templates = sub.add_parser("install-templates", help="Create or update Elasticsearch index templates")
    templates.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    settings = Settings.from_env()
    try:
        if args.command == "install-templates":
            return _install(settings, dry_run=args.dry_run)
        client = _client(settings)
        if args.command == "probe":
            report = _probe(client)
        elif args.command == "get":
            report = client.get(args.path)
        elif args.command == "export":
            return _export(client, args)
        else:
            return _index(settings, client, args)
    except (NetBirdError, RuntimeError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    json.dump(report, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def _client(settings: Settings) -> NetBirdClient:
    if not settings.url:
        raise NetBirdError("NETBIRD_URL is required")
    if not settings.token:
        raise NetBirdError("NETBIRD_TOKEN is required")
    return NetBirdClient(
        settings.url,
        settings.token,
        verify_tls=settings.verify_tls,
        timeout=settings.timeout,
    )


def _probe(client: NetBirdClient) -> dict:
    # Service-user tokens are rejected by GET /api/users/current. Accounts is
    # the auth check; the caller is the users row with is_current set.
    accounts = client.accounts()
    users = client.users()
    counts: dict[str, int | str] = {"users": len(users)}
    for name in _COLLECTIONS:
        if name == "users":
            continue
        try:
            counts[name] = len(getattr(client, name)())
        except NetBirdError as err:
            counts[name] = f"error: {err.status or 'request'}"
    account = accounts[0] if accounts and isinstance(accounts[0], dict) else {}
    return {
        "url": client.api_url,
        "account_id": account.get("id"),
        "user": _current_user(users),
        "counts": counts,
    }


def _export(client: NetBirdClient, args) -> int:
    ingested = datetime.now(timezone.utc)
    pull_id = str(uuid.uuid4())
    documents = _documents(client, args.only, pull_id=pull_id, ingested=ingested, max_peers=args.max_peers)
    payload = "".join(json.dumps(doc, default=str) + "\n" for doc in documents)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(payload)
    print(f"wrote {len(documents)} {args.only} documents", file=sys.stderr)
    return 0


def _index(settings: Settings, client: NetBirdClient, args) -> int:
    want_peers = args.only in {None, "peers"}
    want_audit = args.only in {None, "audit"}
    if want_peers and args.no_bronze and args.no_current and not args.dry_run and not want_audit:
        raise NetBirdError("both --no-bronze and --no-current were set")
    if args.max_peers is not None and args.max_peers < 1:
        raise NetBirdError("--max-peers must be >= 1")
    if want_peers and args.max_peers is not None and not args.no_current and not args.dry_run:
        raise NetBirdError(
            "--max-peers is a partial pull; pass --no-current so the current snapshot is not replaced"
        )
    ingested = datetime.now(timezone.utc)
    pull_id = str(uuid.uuid4())
    peers = _documents(client, "peers", pull_id=pull_id, ingested=ingested, max_peers=args.max_peers) if want_peers else []
    audits = _documents(client, "audit", pull_id=pull_id, ingested=ingested, max_peers=None) if want_audit else []
    print(f"mapped peers={len(peers)} audit={len(audits)} (pull {pull_id})")
    if args.dry_run:
        sample = (peers or audits or [None])[0]
        if sample:
            print(json.dumps(sample, indent=2, default=str))
        return 0
    from netbird_api.elastic import connect, index_audits, index_peers, install_templates

    es = connect(settings)
    if args.install_templates:
        install_templates(es)
    if want_peers:
        if not peers:
            print("no peers; current snapshot left unchanged")
        elif not args.no_bronze or not args.no_current:
            stats = index_peers(
                es,
                peers,
                bronze_index=None if args.no_bronze else settings.peer_bronze_index,
                current_index=None if args.no_current else settings.peer_current_index,
                lookup_index=None if args.no_current else settings.peer_lookup_index,
                pull_id=pull_id,
            )
            print(
                f"peers bronze={stats['bronze']} current={stats['current']} "
                f"removed={stats['removed']} lookup={stats['lookup']}"
            )
    if want_audit:
        stats = index_audits(es, audits, index=settings.audit_index)
        print(f"audit created={stats['created']} existing={stats['existing']}")
    return 0


def _documents(client: NetBirdClient, kind: str, *, pull_id: str, ingested: datetime, max_peers: int | None) -> list[dict]:
    if kind == "peers":
        peers = client.peers()
        if max_peers is not None:
            peers = peers[:max_peers]
        return [doc for peer in peers if (doc := peer_document(peer, pull_id=pull_id, ingested=ingested))]
    return [doc for event in client.audit_events() if (doc := audit_document(event, ingested=ingested))]


def _install(settings: Settings, *, dry_run: bool) -> int:
    from netbird_api.templates import AUDIT_TEMPLATE, PEER_BRONZE_TEMPLATE, PEER_CURRENT_TEMPLATE

    if dry_run:
        json.dump(
            {"peers_bronze": PEER_BRONZE_TEMPLATE, "peers_current": PEER_CURRENT_TEMPLATE, "audit": AUDIT_TEMPLATE},
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0
    from netbird_api.elastic import connect, install_templates

    install_templates(connect(settings))
    print("installed index templates")
    return 0


def _current_user(users: list) -> dict:
    current = next((user for user in users if isinstance(user, dict) and user.get("is_current")), None)
    if current is None:
        return {}
    return {
        "id": current.get("id"),
        "email": current.get("email"),
        "name": current.get("name"),
        "role": current.get("role"),
        "is_service_user": current.get("is_service_user"),
    }
