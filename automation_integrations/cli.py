from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import threading

from .api import running
from .config import load_config
from .contracts import validate_event
from .store import Store
from .worker import Worker


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Automation Integrations v0.1")
    parser.add_argument("--config", required=True)
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("serve")
    subs.add_parser("check")
    subs.add_parser("status")
    subs.add_parser("work-once")
    inspect = subs.add_parser("job")
    inspect.add_argument("id")
    submit = subs.add_parser("submit")
    submit.add_argument("--connection", required=True)
    submit.add_argument("--event-file", required=True)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.command == "check":
            print(json.dumps({"valid": True, "dry_run": config["dry_run"],
                              "connections": list(config["connections"])}))
            return 0
        if args.command == "serve":
            logging.basicConfig(level=logging.INFO)
            stopped = threading.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: stopped.set())
            with running(config) as server:
                while not stopped.wait(0.5):
                    if not server.worker_thread.is_alive():
                        raise RuntimeError("worker_stopped")
            return 0
        store = Store(config["state_dir"])
        if args.command == "status":
            result = {"jobs": store.counts(), "dry_run": config["dry_run"]}
        elif args.command == "job":
            result = store.snapshot(args.id) or {"error": "not_found"}
        elif args.command == "submit":
            from pathlib import Path
            event = validate_event(json.loads(Path(args.event_file).read_text()), config["connections"][args.connection])
            job_id, created = store.accept(args.connection, event, dry_run=config["dry_run"])
            result = {"job_id": job_id, "created": created}
        else:
            with store.worker_lock():
                store.recover()
                result = {"processed": Worker(store, config).once()}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        # Configs/paths/provider exceptions can contain secrets; no raw exception rendering.
        print(json.dumps({"error": "operation_failed", "class": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
