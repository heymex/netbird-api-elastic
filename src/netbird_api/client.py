from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import requests

# (method, url, headers, timeout) -> response with status_code, text, json(), headers
Transport = Callable[..., Any]


class NetBirdError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def api_base(url: str) -> str:
    """Normalize a dashboard origin or an /api URL to the management API base."""
    raw = url.strip().rstrip("/")
    if not raw:
        raise ValueError("NETBIRD_URL is required")
    parts = urlsplit(raw)
    if parts.scheme not in {"https", "http"} or not parts.netloc:
        raise ValueError(f"NETBIRD_URL must be an http(s) origin: {url!r}")
    if parts.query or parts.fragment:
        raise ValueError("NETBIRD_URL must not include a query or fragment")
    path = parts.path.rstrip("/")
    if path not in {"", "/api"}:
        raise ValueError("NETBIRD_URL must be the dashboard origin or end in /api")
    origin = f"{parts.scheme}://{parts.netloc}"
    return f"{origin}/api"


def resource_path(path: str) -> str:
    """Turn a user path into a relative path under /api. GET only; no traversal."""
    raw = path.strip()
    if not raw:
        raise ValueError("path is required")
    if "://" in raw or raw.startswith("//"):
        raise ValueError("pass a path under /api, not a URL")
    if "?" in raw or "#" in raw:
        raise ValueError("put filters in the path only; query strings are not accepted")
    raw = raw.lstrip("/")
    if raw == "api" or raw.startswith("api/"):
        raw = raw[4:].lstrip("/")
    parts = [part for part in raw.split("/") if part != ""]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError(f"invalid API path: {path!r}")
    return "/".join(parts)


class NetBirdClient:
    """Read-only client for the NetBird management HTTP API.

    Self-hosted management is served at ``<dashboard>/api``. Personal access
    tokens use ``Authorization: Token <pat>``.
    """

    def __init__(
        self,
        url: str,
        token: str,
        *,
        verify_tls: bool = True,
        timeout: int = 30,
        transport: Transport | None = None,
    ) -> None:
        if not token:
            raise ValueError("NETBIRD_TOKEN is required")
        self.api_url = api_base(url)
        self._token = token
        self.verify_tls = verify_tls
        self.timeout = timeout
        self._transport = transport
        self._http = requests.Session()
        self._http.headers["User-Agent"] = "rctc-netbird-api/0.1"
        self._http.headers["Accept"] = "application/json"
        self._http.headers["Authorization"] = f"Token {token}"

    def get(self, path: str) -> Any:
        rel = resource_path(path)
        url = f"{self.api_url}/{rel}"
        response = self._send(url)
        return _decode(response, url)

    def current_user(self) -> Any:
        return self.get("users/current")

    def accounts(self) -> list[Any]:
        return _as_list(self.get("accounts"), "accounts")

    def peers(self) -> list[Any]:
        return _as_list(self.get("peers"), "peers")

    def audit_events(self) -> list[Any]:
        return _as_list(self.get("events/audit"), "events/audit")

    def users(self) -> list[Any]:
        return _as_list(self.get("users"), "users")

    def groups(self) -> list[Any]:
        return _as_list(self.get("groups"), "groups")

    def policies(self) -> list[Any]:
        return _as_list(self.get("policies"), "policies")

    def routes(self) -> list[Any]:
        return _as_list(self.get("routes"), "routes")

    def _send(self, url: str) -> Any:
        headers = {"Authorization": f"Token {self._token}", "Accept": "application/json"}
        try:
            if self._transport is not None:
                return self._transport("GET", url, headers, self.timeout)
            return self._http.get(url, timeout=self.timeout, verify=self.verify_tls)
        except requests.RequestException as err:
            raise NetBirdError(f"GET {url} failed: {err}") from err


def _decode(response: Any, url: str) -> Any:
    status = int(response.status_code)
    if status >= 400:
        detail = _error_detail(response)
        raise NetBirdError(f"GET {url} returned {status}: {detail}", status=status)
    if status == 204 or not getattr(response, "text", ""):
        return None
    content_type = ""
    headers = getattr(response, "headers", {}) or {}
    if hasattr(headers, "get"):
        content_type = str(headers.get("content-type", ""))
    if "json" not in content_type.lower():
        raise NetBirdError(f"GET {url} returned {status} with a non-JSON body", status=status)
    try:
        return response.json()
    except (ValueError, json.JSONDecodeError) as err:
        raise NetBirdError(f"GET {url} returned invalid JSON") from err


def _error_detail(response: Any) -> str:
    text = str(getattr(response, "text", "") or "").strip()
    if not text:
        return "(empty body)"
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError, AttributeError):
        return text[:300]
    if isinstance(body, dict):
        for key in ("message", "error", "detail"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value[:300]
    return text[:300]


def _as_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise NetBirdError(f"{name} response was not a JSON array")
    return value
