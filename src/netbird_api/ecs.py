from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from typing import Any

ECS_VERSION = "8.17.0"

# Meta values that can carry a credential. Names and ids stay.
_SECRET_META = ("password", "token", "secret", "private", "credential", "authorization")


def peer_document(peer: dict[str, Any], *, pull_id: str, ingested: datetime) -> dict[str, Any] | None:
    """Map one management peer to an ECS state document.

    ``@timestamp`` is the observation time, so each scheduled pull lines up in
    the time picker. ``last_seen`` stays on the document.
    """
    peer_id = _text(peer.get("id"))
    if not peer_id:
        return None
    ingested_iso = _iso(ingested)
    name = _text(peer.get("name")) or _text(peer.get("hostname")) or peer_id
    hostname = _text(peer.get("hostname"))
    connected = bool(peer.get("connected"))
    overlay = _ips(peer.get("ip"), peer.get("ipv6"))
    connection_ip = _ip(peer.get("connection_ip"))
    group_ids, group_names = _groups(peer.get("groups"))
    dns_label = _text(peer.get("dns_label"))

    doc: dict[str, Any] = {
        "@timestamp": ingested_iso,
        "ecs": {"version": ECS_VERSION},
        "message": f"{name} {'connected' if connected else 'disconnected'}",
        "event": {
            "kind": "state",
            "category": ["host", "network"],
            "type": ["info", "connection"],
            "action": "connected" if connected else "disconnected",
            "dataset": "netbird.peer",
            "module": "netbird",
            "provider": "NetBird",
            "outcome": "success",
            "created": _text(peer.get("created_at")),
            "ingested": ingested_iso,
            "id": peer_id,
        },
        "observer": {"vendor": "NetBird", "product": "NetBird", "type": "vpn"},
        "host": {"id": peer_id, "name": name},
        "netbird": {
            "pull_id": pull_id,
            "peer_id": peer_id,
            "connected": connected,
            "ssh_enabled": bool(peer.get("ssh_enabled")),
            "login_expired": bool(peer.get("login_expired")),
            "login_expiration_enabled": bool(peer.get("login_expiration_enabled")),
            "inactivity_expiration_enabled": bool(peer.get("inactivity_expiration_enabled")),
            "ephemeral": bool(peer.get("ephemeral")),
            "approval_required": bool(peer.get("approval_required")),
        },
    }
    if hostname:
        doc["host"]["hostname"] = hostname
    os_doc = _os(peer.get("os"), peer.get("kernel_version"))
    if os_doc:
        doc["host"]["os"] = os_doc
    if overlay:
        doc["host"]["ip"] = overlay
    if connection_ip:
        doc["source"] = {"ip": connection_ip}
        geo = {}
        country = _text(peer.get("country_code"))
        city = _text(peer.get("city_name"))
        if country:
            geo["country_iso_code"] = country
        if city:
            geo["city_name"] = city
        if geo:
            doc["source"]["geo"] = geo
    if group_ids or group_names:
        doc["group"] = {}
        if group_ids:
            doc["group"]["id"] = group_ids
        if group_names:
            doc["group"]["name"] = group_names
    related_ip = list(dict.fromkeys([*overlay, *([connection_ip] if connection_ip else [])]))
    related_hosts = [value for value in (hostname, name, dns_label) if value]
    if related_ip or related_hosts:
        doc["related"] = {}
        if related_ip:
            doc["related"]["ip"] = related_ip
        if related_hosts:
            doc["related"]["hosts"] = list(dict.fromkeys(related_hosts))
    _copy_text(doc["netbird"], peer, ("dns_label", "version", "ui_version", "serial_number", "user_id", "last_seen", "last_login"))
    labels = [label for label in peer.get("extra_dns_labels") or [] if _text(label)]
    if labels:
        doc["netbird"]["extra_dns_labels"] = labels
    flags = _flags(peer.get("local_flags"))
    if flags:
        doc["netbird"]["local_flags"] = flags
    count = peer.get("accessible_peers_count")
    if isinstance(count, int):
        doc["netbird"]["accessible_peers_count"] = count
    doc["event"] = {key: value for key, value in doc["event"].items() if value}
    return doc


def audit_document(event: dict[str, Any], *, ingested: datetime) -> dict[str, Any] | None:
    """Map one audit event. ``@timestamp`` is when NetBird says it happened."""
    event_id = _text(event.get("id"))
    when = _text(event.get("timestamp"))
    if not event_id or not when:
        return None
    code = _text(event.get("activity_code")) or "unknown"
    category, event_type = classify(code)
    activity = _text(event.get("activity")) or code
    ingested_iso = _iso(ingested)
    doc: dict[str, Any] = {
        "@timestamp": when,
        "ecs": {"version": ECS_VERSION},
        "message": activity,
        "event": {
            "kind": "event",
            "category": category,
            "type": event_type,
            "action": code,
            "dataset": "netbird.audit",
            "module": "netbird",
            "provider": "NetBird",
            "outcome": "success",
            "id": event_id,
            "created": when,
            "ingested": ingested_iso,
        },
        "observer": {"vendor": "NetBird", "product": "NetBird", "type": "vpn"},
        "netbird": {
            "activity": activity,
            "activity_code": code,
        },
    }
    target = _text(event.get("target_id"))
    if target:
        doc["netbird"]["target_id"] = target
    user = {}
    initiator_id = _text(event.get("initiator_id"))
    initiator_name = _text(event.get("initiator_name"))
    initiator_email = _text(event.get("initiator_email"))
    if initiator_id:
        user["id"] = initiator_id
    if initiator_name:
        user["name"] = initiator_name
    if initiator_email:
        user["email"] = initiator_email
    if user:
        doc["user"] = user
        related = [value for value in (initiator_name, initiator_email) if value]
        if related:
            doc["related"] = {"user": related}
    meta = _meta(event.get("meta"))
    if meta:
        doc["netbird"]["meta"] = meta
    return doc


def classify(code: str) -> tuple[list[str], list[str]]:
    """ECS category and type for a NetBird activity code."""
    if code in {"dashboard.login", "user.peer.login", "user.join"} or code.endswith(".login"):
        return ["authentication"], ["start"]
    if "expire" in code:
        return ["authentication"], ["end"]
    if code.startswith("peer.") or code.startswith("user.peer."):
        category = ["host"]
    elif (
        code.startswith("user.")
        or code.startswith("service.user")
        or code.startswith("setupkey")
        or code.startswith("personal.access.token")
        or code == "transferred.owner.role"
    ):
        category = ["iam"]
    else:
        category = ["configuration"]
    if any(token in code for token in (".delete", ".revoke", ".reject")):
        event_type = ["deletion"]
    elif any(token in code for token in (".add", ".create")):
        event_type = ["creation"]
    else:
        event_type = ["change"]
    return category, event_type


def document_id(doc: dict[str, Any]) -> str:
    dataset = (doc.get("event") or {}).get("dataset")
    if dataset == "netbird.audit":
        return str((doc.get("event") or {}).get("id") or "")
    return str((doc.get("host") or {}).get("id") or "")


def _groups(raw: Any) -> tuple[list[str], list[str]]:
    ids: list[str] = []
    names: list[str] = []
    if not isinstance(raw, list):
        return ids, names
    for group in raw:
        if isinstance(group, str) and group:
            ids.append(group)
        elif isinstance(group, dict):
            group_id = _text(group.get("id"))
            group_name = _text(group.get("name"))
            if group_id:
                ids.append(group_id)
            if group_name:
                names.append(group_name)
    return ids, names


def _meta(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    kept: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or _secret_key(key):
            continue
        text = _text(value)
        if text is not None:
            kept[key] = text
    return kept


def _secret_key(key: str) -> bool:
    lowered = key.lower()
    if lowered == "key":
        return True
    return any(part in lowered for part in _SECRET_META)


def _flags(raw: Any) -> dict[str, bool]:
    if not isinstance(raw, dict):
        return {}
    return {key: bool(value) for key, value in raw.items() if isinstance(key, str) and isinstance(value, bool)}


def _os(name: Any, kernel: Any) -> dict[str, str]:
    fields: dict[str, str] = {}
    full = _text(name)
    if full:
        fields["full"] = full
        head, _, rest = full.partition(" ")
        fields["name"] = head
        if rest:
            fields["version"] = rest
    kernel_text = _text(kernel)
    if kernel_text:
        fields["kernel"] = kernel_text
    return fields


def _copy_text(dest: dict[str, Any], source: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        text = _text(source.get(key))
        if text:
            dest[key] = text


def _ips(*values: Any) -> list[str]:
    found: list[str] = []
    for value in values:
        parsed = _ip(value)
        if parsed and parsed not in found:
            found.append(parsed)
    return found


def _ip(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return None


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
