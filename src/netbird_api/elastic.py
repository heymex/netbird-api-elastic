from __future__ import annotations

import logging
from typing import Any

from netbird_api.ecs import document_id
from netbird_api.templates import AUDIT_TEMPLATE, PEER_BRONZE_TEMPLATE, PEER_CURRENT_TEMPLATE, PEER_PROPERTIES

log = logging.getLogger("netbird.elastic")

PEER_BRONZE_TEMPLATE_NAME = "logs-netbird.peer"
PEER_CURRENT_TEMPLATE_NAME = "netbird-peer-current"
AUDIT_TEMPLATE_NAME = "logs-netbird.audit"


def connect(settings):
    from elasticsearch import Elasticsearch

    if not settings.elastic_url:
        raise RuntimeError("ELASTIC_URL is required")
    kwargs: dict[str, Any] = {
        "request_timeout": 120,
        "verify_certs": settings.elastic_verify_tls,
    }
    if settings.elastic_api_key:
        kwargs["api_key"] = settings.elastic_api_key
    elif settings.elastic_user:
        kwargs["basic_auth"] = (settings.elastic_user, settings.elastic_password or "")
    return Elasticsearch(settings.elastic_url, **kwargs)


def install_templates(es) -> None:
    es.indices.put_index_template(name=PEER_BRONZE_TEMPLATE_NAME, **_body(PEER_BRONZE_TEMPLATE))
    es.indices.put_index_template(name=PEER_CURRENT_TEMPLATE_NAME, **_body(PEER_CURRENT_TEMPLATE))
    es.indices.put_index_template(name=AUDIT_TEMPLATE_NAME, **_body(AUDIT_TEMPLATE))


def index_peers(
    es,
    documents: list[dict[str, Any]],
    *,
    bronze_index: str | None,
    current_index: str | None,
    pull_id: str,
    lookup_index: str | None = None,
) -> dict[str, int]:
    """Append peer observations and replace the current snapshot.

    An empty document list must not be passed through to the current index.
    The caller keeps the previous snapshot when a pull returns no peers.
    ``lookup_index`` is rebuilt from the same snapshot for ES|QL LOOKUP JOIN.
    """
    stats = {"bronze": 0, "current": 0, "removed": 0, "lookup": 0}
    if bronze_index:
        stats["bronze"] = _bulk(es, bronze_index, documents, op_type="create", with_id=False)
    if current_index:
        stats["current"] = _bulk(es, current_index, documents, op_type="index", with_id=True)
        stats["removed"] = _delete_stale_peers(es, current_index, pull_id)
    if lookup_index and current_index:
        stats["lookup"] = replace_peer_lookup(es, documents, index=lookup_index)
    return stats


def replace_peer_lookup(es, documents: list[dict[str, Any]], *, index: str) -> int:
    """Replace the lookup-mode peer index. LOOKUP JOIN cannot read a standard index."""
    if es.indices.exists(index=index):
        es.indices.delete(index=index)
    es.indices.create(
        index=index,
        settings={"index.mode": "lookup", "number_of_shards": 1, "number_of_replicas": 0},
        mappings={"dynamic": True, "properties": PEER_PROPERTIES},
    )
    return _bulk(es, index, documents, op_type="index", with_id=True)


def index_audits(es, documents: list[dict[str, Any]], *, index: str) -> dict[str, int]:
    """Insert audit events by id. A repeat pull leaves existing events in place."""
    if not documents:
        return {"created": 0, "existing": 0}

    def actions():
        for doc in documents:
            yield {
                "_op_type": "create",
                "_index": index,
                "_id": document_id(doc),
                "_source": doc,
            }

    from elasticsearch.helpers import bulk

    success, errors = bulk(es, actions(), refresh="wait_for", raise_on_error=False)
    conflicts = [error for error in errors if _status(error) == 409]
    failures = [error for error in errors if _status(error) != 409]
    if failures:
        raise RuntimeError(f"Elasticsearch bulk to {index} failed ({len(failures)} errors): {failures[0]}")
    log.info("audit index %s created=%s existing=%s", index, success, len(conflicts))
    return {"created": int(success), "existing": len(conflicts)}


def _bulk(es, index: str, documents: list[dict[str, Any]], *, op_type: str, with_id: bool) -> int:
    from elasticsearch.helpers import bulk

    def actions():
        for doc in documents:
            action: dict[str, Any] = {"_op_type": op_type, "_index": index, "_source": doc}
            if with_id:
                action["_id"] = document_id(doc)
            yield action

    success, errors = bulk(es, actions(), refresh="wait_for", raise_on_error=False)
    if errors:
        raise RuntimeError(f"Elasticsearch bulk to {index} failed ({len(errors)} errors): {errors[0]}")
    log.info("indexed %s documents into %s", success, index)
    return int(success)


def _delete_stale_peers(es, index: str, pull_id: str) -> int:
    if not es.indices.exists(index=index):
        return 0
    result = es.delete_by_query(
        index=index,
        query={"bool": {"must_not": [{"term": {"netbird.pull_id": pull_id}}]}},
        conflicts="proceed",
        refresh=True,
    )
    return int(result.get("deleted", 0))


def _status(error: Any) -> int | None:
    if not isinstance(error, dict) or not error:
        return None
    info = next(iter(error.values()))
    if isinstance(info, dict):
        return info.get("status")
    return None


def _body(template: dict) -> dict:
    return {
        "index_patterns": template["index_patterns"],
        "priority": template["priority"],
        "template": template["template"],
        "meta": template.get("_meta"),
        **({"data_stream": template["data_stream"]} if "data_stream" in template else {}),
    }
