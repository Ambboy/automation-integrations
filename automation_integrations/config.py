from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from urllib.parse import urlparse

from .contracts import ContractError, identifier


def secret_file(path):
    p = Path(path)
    if not p.is_absolute() or p.is_symlink():
        raise ContractError("secret_path_must_be_absolute_regular_file")
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ContractError("secret_file_permissions")
        value = os.read(fd, 8192).decode().strip()
    finally:
        os.close(fd)
    if len(value) < 24 or any(c.isspace() for c in value):
        raise ContractError("invalid_secret_file")
    return value


def load_config(path):
    config = json.loads(Path(path).read_text())
    if config.get("schema") != 1 or type(config.get("dry_run")) is not bool:
        raise ContractError("config_requires_schema_and_explicit_dry_run")
    state = Path(config["state_dir"])
    if not state.is_absolute():
        raise ContractError("state_dir_must_be_absolute")
    if config.get("listen", "127.0.0.1") != "127.0.0.1":
        raise ContractError("v1_listens_only_on_loopback")
    if not isinstance(config.get("connections"), dict) or not config["connections"]:
        raise ContractError("connections_required")
    seen_tokens = set()
    for name, conn in config["connections"].items():
        identifier(name)
        token = secret_file(conn["token_file"])
        if token in seen_tokens:
            raise ContractError("connections_require_distinct_tokens")
        seen_tokens.add(token)
        if not conn.get("routes") or not conn.get("modules"):
            raise ContractError("explicit_routes_and_modules_required")
        if set(conn["modules"]) - {"topic-icons", "voice-reply"}:
            raise ContractError("unknown_module")
        for route in conn["routes"]:
            if set(route) != {"profile", "platform", "chat_id", "user_id", "thread_ids"}:
                raise ContractError("invalid_route_config")
            for key in ("profile", "platform", "chat_id", "user_id"):
                identifier(route[key])
            if not isinstance(route["thread_ids"], list) or not route["thread_ids"]:
                raise ContractError("thread_allowlist_required")
            for thread in route["thread_ids"]:
                if thread not in ("", "*"):
                    identifier(thread)
        age = conn.get("max_event_age_seconds", 86400)
        if type(age) is not int or not 1 <= age <= 604800:
            raise ContractError("invalid_max_event_age")
    base = config.get("telegram", {}).get("base_url", "https://api.telegram.org")
    parsed = urlparse(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ContractError("invalid_telegram_endpoint")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}):
        raise ContractError("telegram_requires_https_or_loopback")
    if not config["dry_run"]:
        for conn in config["connections"].values():
            secret_file(conn["telegram_token_file"])
        if any("voice-reply" in c["modules"] for c in config["connections"].values()):
            tts = config.get("voice", {}).get("tts_argv")
            if not isinstance(tts, list) or not tts or not all(isinstance(x, str) for x in tts):
                raise ContractError("live_voice_requires_tts_argv")
            if not Path(tts[0]).is_absolute() or not any("{output_file}" in x for x in tts):
                raise ContractError("tts_requires_absolute_executable_and_output_placeholder")
            for executable in (tts[0], config.get("voice", {}).get("ffmpeg", "/usr/bin/ffmpeg"),
                               config.get("voice", {}).get("ffprobe", "/usr/bin/ffprobe")):
                if not Path(executable).is_absolute() or not Path(executable).is_file() or not os.access(executable, os.X_OK):
                    raise ContractError("media_executable_unavailable")
    return config
