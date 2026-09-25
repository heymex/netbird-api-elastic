import json

import pytest

from netbird_api.client import NetBirdClient, NetBirdError, api_base, resource_path


class _Response:
    def __init__(self, status, body, content_type="application/json"):
        self.status_code = status
        self._body = body
        self.text = body if isinstance(body, str) else json.dumps(body)
        self.headers = {"content-type": content_type}

    def json(self):
        if isinstance(self._body, str):
            return json.loads(self._body)
        return self._body


def test_api_base_accepts_origin_or_api_suffix():
    assert api_base("https://vpn.example.edu") == "https://vpn.example.edu/api"
    assert api_base("https://vpn.example.edu/") == "https://vpn.example.edu/api"
    assert api_base("https://vpn.example.edu/api") == "https://vpn.example.edu/api"
    assert api_base("https://vpn.example.edu/api/") == "https://vpn.example.edu/api"


def test_api_base_rejects_other_paths_and_queries():
    with pytest.raises(ValueError):
        api_base("https://vpn.example.edu/dashboard")
    with pytest.raises(ValueError):
        api_base("https://vpn.example.edu/api?account=1")
    with pytest.raises(ValueError):
        api_base("vpn.example.edu")


def test_resource_path_strips_api_prefix_and_rejects_traversal():
    assert resource_path("peers") == "peers"
    assert resource_path("/api/users/current") == "users/current"
    assert resource_path("api/groups") == "groups"
    with pytest.raises(ValueError):
        resource_path("../peers")
    with pytest.raises(ValueError):
        resource_path("https://vpn.example.edu/api/peers")
    with pytest.raises(ValueError):
        resource_path("users?service_user=true")


def test_get_sends_token_header_and_returns_json():
    seen = {}

    def transport(method, url, headers, timeout):
        seen["method"] = method
        seen["url"] = url
        seen["headers"] = headers
        seen["timeout"] = timeout
        return _Response(200, [{"id": "peer-1", "name": "laptop"}])

    client = NetBirdClient(
        "https://vpn.example.edu",
        "nbp_test",
        timeout=12,
        transport=transport,
    )
    assert client.peers() == [{"id": "peer-1", "name": "laptop"}]
    assert seen["method"] == "GET"
    assert seen["url"] == "https://vpn.example.edu/api/peers"
    assert seen["headers"]["Authorization"] == "Token nbp_test"
    assert seen["timeout"] == 12


def test_http_error_includes_status_and_message():
    def transport(method, url, headers, timeout):
        return _Response(401, {"message": "token invalid"})

    client = NetBirdClient("https://vpn.example.edu", "nbp_test", transport=transport)
    with pytest.raises(NetBirdError) as err:
        client.current_user()
    assert err.value.status == 401
    assert "token invalid" in str(err.value)
    assert "nbp_test" not in str(err.value)


def test_non_json_success_is_rejected():
    def transport(method, url, headers, timeout):
        return _Response(200, "<html></html>", content_type="text/html")

    client = NetBirdClient("https://vpn.example.edu", "nbp_test", transport=transport)
    with pytest.raises(NetBirdError, match="non-JSON"):
        client.get("peers")
