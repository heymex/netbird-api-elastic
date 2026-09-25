from __future__ import annotations

_EVENT = {
    "properties": {
        "kind": {"type": "keyword"},
        "category": {"type": "keyword"},
        "type": {"type": "keyword"},
        "action": {"type": "keyword"},
        "dataset": {"type": "keyword"},
        "module": {"type": "keyword"},
        "provider": {"type": "keyword"},
        "outcome": {"type": "keyword"},
        "id": {"type": "keyword"},
        "created": {"type": "date"},
        "ingested": {"type": "date"},
    }
}

_OBSERVER = {
    "properties": {
        "vendor": {"type": "keyword"},
        "product": {"type": "keyword"},
        "type": {"type": "keyword"},
        "name": {"type": "keyword"},
    }
}


def _template(index_patterns: list[str], properties: dict, *, data_stream: bool, description: str) -> dict:
    body: dict = {
        "index_patterns": index_patterns,
        "priority": 500,
        "template": {"mappings": {"dynamic": True, "properties": properties}},
        "_meta": {"description": description},
    }
    if data_stream:
        body["data_stream"] = {}
    return body


PEER_PROPERTIES = {
    "@timestamp": {"type": "date"},
    "message": {"type": "match_only_text"},
    "ecs": {"properties": {"version": {"type": "keyword"}}},
    "event": _EVENT,
    "observer": _OBSERVER,
    "host": {
        "properties": {
            "id": {"type": "keyword"},
            "name": {"type": "keyword"},
            "hostname": {"type": "keyword"},
            "ip": {"type": "ip"},
            "os": {
                "properties": {
                    "name": {"type": "keyword"},
                    "full": {"type": "keyword"},
                    "version": {"type": "keyword"},
                    "kernel": {"type": "keyword"},
                }
            },
        }
    },
    "source": {
        "properties": {
            "ip": {"type": "ip"},
            "geo": {
                "properties": {
                    "country_iso_code": {"type": "keyword"},
                    "city_name": {"type": "keyword"},
                }
            },
        }
    },
    "group": {"properties": {"id": {"type": "keyword"}, "name": {"type": "keyword"}}},
    "related": {"properties": {"ip": {"type": "ip"}, "hosts": {"type": "keyword"}}},
    "netbird": {
        "properties": {
            "pull_id": {"type": "keyword"},
            "peer_id": {"type": "keyword"},
            "connected": {"type": "boolean"},
            "dns_label": {"type": "keyword"},
            "version": {"type": "keyword"},
            "ui_version": {"type": "keyword"},
            "serial_number": {"type": "keyword"},
            "user_id": {"type": "keyword"},
            "last_seen": {"type": "date"},
            "last_login": {"type": "date"},
            "ssh_enabled": {"type": "boolean"},
            "login_expired": {"type": "boolean"},
            "login_expiration_enabled": {"type": "boolean"},
            "inactivity_expiration_enabled": {"type": "boolean"},
            "ephemeral": {"type": "boolean"},
            "approval_required": {"type": "boolean"},
            "accessible_peers_count": {"type": "long"},
            "extra_dns_labels": {"type": "keyword"},
        }
    },
}

AUDIT_PROPERTIES = {
    "@timestamp": {"type": "date"},
    "message": {"type": "match_only_text"},
    "ecs": {"properties": {"version": {"type": "keyword"}}},
    "event": _EVENT,
    "observer": _OBSERVER,
    "user": {
        "properties": {
            "id": {"type": "keyword"},
            "name": {"type": "keyword"},
            "email": {"type": "keyword"},
        }
    },
    "related": {"properties": {"user": {"type": "keyword"}}},
    "netbird": {
        "properties": {
            "activity": {"type": "keyword"},
            "activity_code": {"type": "keyword"},
            "target_id": {"type": "keyword"},
            "meta": {"type": "flattened"},
        }
    },
}

PEER_BRONZE_TEMPLATE = _template(
    ["logs-netbird.peer-*"],
    PEER_PROPERTIES,
    data_stream=True,
    description="NetBird peer observations mapped to ECS",
)
PEER_CURRENT_TEMPLATE = _template(
    ["netbird-peer-current"],
    PEER_PROPERTIES,
    data_stream=False,
    description="Current NetBird peer snapshot mapped to ECS",
)
AUDIT_TEMPLATE = _template(
    ["logs-netbird.audit"],
    AUDIT_PROPERTIES,
    data_stream=False,
    description="NetBird audit events mapped to ECS",
)
