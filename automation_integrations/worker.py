from __future__ import annotations

import json
import logging
import threading

from .contracts import ContractError, validate_event
from .modules import MODULES, FALLBACK_ICONS, PreparationError
from .telegram import DeliveryRejected, Telegram

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, store, config, connector_factory=Telegram):
        self.store, self.config, self.connector_factory = store, config, connector_factory
        self.stop = threading.Event()

    def once(self):
        job = self.store.claim()
        if not job:
            return False
        job_id = job["id"]
        try:
            conn = self.config["connections"][job["connection"]]
            # Recheck allowlist, enabled module and freshness at execution, not just admission.
            event = validate_event(job["event"], conn)
            if job["module"] == "topic-icons" and not self.store.current_topic(job["connection"], event["source"], job_id):
                self.store.finish(job_id, "superseded")
                return True
            dry_run = self.config["dry_run"] or bool(job["dry_run"])
            connector = None if dry_run else self.connector_factory(self.config, conn)
            context = {
                "dry_run": dry_run, "voice": self.config.get("voice", {}),
                "work_dir": self.store.root / "artifacts" / job_id,
                "recent_icons": self.store.recent_icons(job["connection"], event["source"]),
                "icon_catalog": ({emoji: "dry-run-only" for emoji in FALLBACK_ICONS} if dry_run
                                 else connector.catalog() if job["module"] == "topic-icons" else {}),
            }
            actions = MODULES[job["module"]].plan(event, context)
            self.store.prepare_actions(job_id, actions)
        except Exception as exc:
            # Never emit provider stderr, content, request URL or credentials in logs/errors.
            logger.warning("preparation_failed job=%s", job_id)
            error = str(exc) if isinstance(exc, (PreparationError, ContractError, DeliveryRejected)) else "preparation_failed"
            self.store.finish(job_id, "failed", error)
            return True
        if dry_run:
            for row in self.store.actions(job_id):
                self.store.action_state(row["id"], "simulated")
            self.store.finish(job_id, "simulated")
            return True
        delivered = 0
        for row in self.store.actions(job_id):
            action = json.loads(row["payload"])
            if job["module"] == "topic-icons" and not self.store.current_topic(job["connection"], event["source"], job_id):
                self.store.finish(job_id, "superseded")
                return True
            self.store.action_state(row["id"], "sending")
            try:
                receipt = connector.send(event["source"], action)
            except DeliveryRejected as exc:
                self.store.action_state(row["id"], "failed", error=str(exc))
                self.store.finish(job_id, "partial" if delivered else "failed", str(exc))
                return True
            except Exception:
                # Includes programming errors after a provider may have accepted the action.
                self.store.action_state(row["id"], "outcome_unknown", error="delivery_outcome_unknown")
                self.store.finish(job_id, "outcome_unknown", "delivery_outcome_unknown")
                return True
            self.store.delivered(row["id"], receipt, job["connection"], event["source"],
                                 action.get("emoji") if action["kind"] == "topic.icon" else None)
            delivered += 1
        self.store.finish(job_id, "delivered")
        return True

    def run(self):
        while not self.stop.is_set():
            if not self.once():
                self.stop.wait(0.25)
