import json

from netbird_api.cli import main
from netbird_api.client import NetBirdError
from netbird_api.config import Settings


def test_probe_prints_user_and_counts(monkeypatch, capsys):
    class FakeClient:
        api_url = "https://vpn.example.edu/api"

        def accounts(self):
            return [{"id": "acct-1", "settings": {"secret": "nope"}}]

        def peers(self):
            return [{}, {}]

        def users(self):
            return [
                {"id": "owner", "email": "owner@example.edu", "is_current": False},
                {
                    "id": "user-1",
                    "email": "api@example.edu",
                    "name": "API",
                    "role": "admin",
                    "is_service_user": True,
                    "is_current": True,
                    "password": "should-not-appear",
                },
            ]

        def groups(self):
            return []

        def policies(self):
            return [{}]

        def routes(self):
            raise NetBirdError("denied", status=403)

    monkeypatch.setattr(
        "netbird_api.cli.Settings.from_env",
        lambda: Settings(url="https://vpn.example.edu", token="nbp_test", verify_tls=True, timeout=30),
    )
    monkeypatch.setattr("netbird_api.cli._client", lambda settings: FakeClient())

    assert main(["probe"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["url"] == "https://vpn.example.edu/api"
    assert report["account_id"] == "acct-1"
    assert report["user"]["email"] == "api@example.edu"
    assert "password" not in report["user"]
    assert "settings" not in report
    assert report["counts"] == {
        "peers": 2,
        "users": 2,
        "groups": 0,
        "policies": 1,
        "routes": "error: 403",
    }


def test_max_peers_refuses_to_replace_current_snapshot(monkeypatch, capsys):
    monkeypatch.setattr(
        "netbird_api.cli.Settings.from_env",
        lambda: Settings(url="https://vpn.example.edu", token="nbp_test", verify_tls=True, timeout=30),
    )
    assert main(["index", "--only", "peers", "--max-peers", "1"]) == 1
    assert "partial pull" in capsys.readouterr().err


def test_audit_dry_run_does_not_call_peers(monkeypatch, capsys):
    class FakeClient:
        def peers(self):
            raise AssertionError("peers should not be collected")

        def audit_events(self):
            return [
                {
                    "id": "9",
                    "timestamp": "2026-09-24T16:00:00Z",
                    "activity": "Peer login",
                    "activity_code": "user.peer.login",
                    "initiator_id": "user-1",
                    "initiator_name": "Ada",
                    "initiator_email": "ada@example.edu",
                    "target_id": "peer-1",
                    "meta": {},
                }
            ]

    monkeypatch.setattr(
        "netbird_api.cli.Settings.from_env",
        lambda: Settings(url="https://vpn.example.edu", token="nbp_test", verify_tls=True, timeout=30),
    )
    monkeypatch.setattr("netbird_api.cli._client", lambda settings: FakeClient())
    assert main(["index", "--only", "audit", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "audit=1" in out
    assert "user.peer.login" in out


def test_missing_token_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(
        "netbird_api.cli.Settings.from_env",
        lambda: Settings(url="https://vpn.example.edu", token="", verify_tls=True, timeout=30),
    )
    assert main(["get", "peers"]) == 1
    assert "NETBIRD_TOKEN" in capsys.readouterr().err
