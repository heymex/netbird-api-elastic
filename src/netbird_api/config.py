from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    url: str
    token: str
    verify_tls: bool
    timeout: int
    elastic_url: str | None = None
    elastic_api_key: str | None = None
    elastic_user: str | None = None
    elastic_password: str | None = None
    elastic_verify_tls: bool = True
    peer_bronze_index: str = "logs-netbird.peer-default"
    peer_current_index: str = "netbird-peer-current"
    peer_lookup_index: str = "netbird-peer-lookup"
    audit_index: str = "logs-netbird.audit"

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        _load_dotenv(env_file or Path.cwd() / ".env")
        timeout = int(os.environ.get("NETBIRD_TIMEOUT", "30"))
        if timeout < 1:
            raise ValueError("NETBIRD_TIMEOUT must be >= 1")
        return cls(
            url=os.environ.get("NETBIRD_URL", "").strip(),
            token=os.environ.get("NETBIRD_TOKEN", "").strip(),
            verify_tls=_bool("NETBIRD_VERIFY_TLS", True),
            timeout=timeout,
            elastic_url=(os.environ.get("ELASTIC_URL") or "").rstrip("/") or None,
            elastic_api_key=os.environ.get("ELASTIC_API_KEY") or None,
            elastic_user=os.environ.get("ELASTIC_USER") or None,
            elastic_password=os.environ.get("ELASTIC_PASSWORD") or None,
            elastic_verify_tls=_bool("ELASTIC_VERIFY_TLS", True),
            peer_bronze_index=os.environ.get("ELASTIC_PEER_BRONZE_INDEX", "logs-netbird.peer-default"),
            peer_current_index=os.environ.get("ELASTIC_PEER_CURRENT_INDEX", "netbird-peer-current"),
            peer_lookup_index=os.environ.get("ELASTIC_PEER_LOOKUP_INDEX", "netbird-peer-lookup"),
            audit_index=os.environ.get("ELASTIC_AUDIT_INDEX", "logs-netbird.audit"),
        )
