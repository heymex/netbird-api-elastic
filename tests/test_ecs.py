from datetime import datetime, timezone

from netbird_api.ecs import audit_document, classify, document_id, peer_document
from netbird_api.elastic import _status


INGESTED = datetime(2026, 9, 24, 17, 0, tzinfo=timezone.utc)


def test_peer_document_maps_connection_state_and_groups():
    doc = peer_document(
        {
            "id": "peer-1",
            "name": "laptop",
            "hostname": "laptop.local",
            "ip": "100.64.0.2",
            "ipv6": "not-an-ip",
            "connection_ip": "203.0.113.10",
            "connected": True,
            "os": "Darwin 13.2.1",
            "kernel_version": "23.2.0",
            "country_code": "US",
            "city_name": "Rochester",
            "dns_label": "laptop.netbird.local",
            "version": "0.65.0",
            "user_id": "user-1",
            "last_seen": "2026-09-24T16:00:00Z",
            "groups": [{"id": "g1", "name": "staff"}, "g2"],
            "local_flags": {"block_inbound": False, "note": "skip"},
            "ssh_enabled": False,
        },
        pull_id="pull-1",
        ingested=INGESTED,
    )
    assert doc["@timestamp"] == "2026-09-24T17:00:00Z"
    assert doc["event"]["kind"] == "state"
    assert doc["event"]["action"] == "connected"
    assert doc["event"]["dataset"] == "netbird.peer"
    assert doc["host"]["ip"] == ["100.64.0.2"]
    assert doc["host"]["os"] == {"full": "Darwin 13.2.1", "name": "Darwin", "version": "13.2.1", "kernel": "23.2.0"}
    assert doc["source"]["ip"] == "203.0.113.10"
    assert doc["source"]["geo"]["city_name"] == "Rochester"
    assert doc["group"]["name"] == ["staff"]
    assert doc["group"]["id"] == ["g1", "g2"]
    assert doc["netbird"]["pull_id"] == "pull-1"
    assert doc["netbird"]["user_id"] == "user-1"
    assert doc["netbird"]["local_flags"] == {"block_inbound": False}
    assert document_id(doc) == "peer-1"


def test_peer_without_id_is_skipped():
    assert peer_document({"name": "nope", "connected": False}, pull_id="pull-1", ingested=INGESTED) is None


def test_audit_document_uses_event_time_and_drops_secrets():
    doc = audit_document(
        {
            "id": 10,
            "timestamp": "2026-09-24T16:04:37Z",
            "activity": "Setup key created",
            "activity_code": "setupkey.add",
            "initiator_id": "user-1",
            "initiator_name": "Ada",
            "initiator_email": "ada@example.edu",
            "target_id": "key-1",
            "meta": {"name": "laptop", "key": "nbp_secret", "password": "nope", "network_range": "10.0.0.0/24"},
        },
        ingested=INGESTED,
    )
    assert doc["@timestamp"] == "2026-09-24T16:04:37Z"
    assert doc["event"]["category"] == ["iam"]
    assert doc["event"]["type"] == ["creation"]
    assert doc["event"]["action"] == "setupkey.add"
    assert doc["user"]["email"] == "ada@example.edu"
    assert doc["netbird"]["meta"] == {"name": "laptop", "network_range": "10.0.0.0/24"}
    assert "key" not in doc["netbird"]["meta"]
    assert document_id(doc) == "10"


def test_audit_conflict_status_is_409():
    assert _status({"create": {"status": 409, "error": {"type": "version_conflict_engine_exception"}}}) == 409
    assert _status({"create": {"status": 400}}) == 400


def test_classify_login_and_peer_delete():
    assert classify("user.peer.login") == (["authentication"], ["start"])
    assert classify("peer.login.expire") == (["authentication"], ["end"])
    assert classify("user.peer.delete") == (["host"], ["deletion"])
    assert classify("policy.update") == (["configuration"], ["change"])
    assert classify("account.setting.local.mfa.enable") == (["configuration"], ["change"])
