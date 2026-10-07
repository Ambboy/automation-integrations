"""Validate wire data independently of plugins and transports."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

KINDS = {"topic.observed": "topic-icons", "reply.completed": "voice-reply"}
IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
SOURCE_FIELDS = {"profile", "platform", "chat_id", "thread_id", "user_id",
                 "message_id", "session_id", "turn_id"}


class ContractError(ValueError):
    pass


class Conflict(ContractError):
    pass


class Forbidden(ContractError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ContractError("invalid_identifier")
    return value


def validate_event(raw, connection, now=None):
    if not isinstance(raw, dict) or set(raw) != {"schema", "event_id", "kind", "occurred_at", "source", "data"}:
        raise ContractError("invalid_event_envelope")
    if type(raw["schema"]) is not int or raw["schema"] != 1 or raw["kind"] not in KINDS:
        raise ContractError("unsupported_contract")
    identifier(raw["event_id"])
    try:
        timestamp = datetime.fromisoformat(raw["occurred_at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError()
        age = (now or datetime.now(timezone.utc)).timestamp() - timestamp.timestamp()
    except (TypeError, ValueError, AttributeError):
        raise ContractError("invalid_timestamp") from None
    if not -60 <= age <= connection.get("max_event_age_seconds", 86400):
        raise ContractError("stale_event")
    source = raw["source"]
    if not isinstance(source, dict) or set(source) != SOURCE_FIELDS:
        raise ContractError("invalid_source")
    for name, value in source.items():
        if name == "thread_id" and value == "":
            continue
        identifier(value)
    if source["platform"] != "telegram":
        raise ContractError("unsupported_platform")
    allowed = any(
        all(source[k] == route[k] for k in ("profile", "platform", "chat_id", "user_id"))
        and (source["thread_id"] in route["thread_ids"] or "*" in route["thread_ids"])
        for route in connection["routes"]
    )
    if not allowed:
        raise Forbidden("route_not_allowed")
    module = KINDS[raw["kind"]]
    if module not in connection["modules"]:
        raise Forbidden("module_not_enabled")
    data = raw["data"]
    if not isinstance(data, dict):
        raise ContractError("invalid_data")
    if module == "topic-icons":
        if set(data) != {"title"} or not source["thread_id"]:
            raise ContractError("topic_requires_thread_and_title")
        if not isinstance(data["title"], str) or not 1 <= len(data["title"].strip()) <= 128:
            raise ContractError("invalid_title")
    else:
        if set(data) != {"text", "origin_type"} or data["origin_type"] != "voice":
            raise ContractError("voice_requires_verified_origin")
        if not isinstance(data["text"], str) or not 1 <= len(data["text"].strip()) <= 24000:
            raise ContractError("invalid_reply")
    return raw


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()
