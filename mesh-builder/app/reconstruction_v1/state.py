from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

TRANSITIONS = {
    None: {"PREPARED"},
    "PREPARED": {"BUNDLE_APPROVED"},
    "BUNDLE_APPROVED": {"CONTRACT_REVERIFIED"},
    "CONTRACT_REVERIFIED": {"AUTHORIZATION_PREVIEWED"},
    "AUTHORIZATION_PREVIEWED": {"COST_APPROVED"},
    "COST_APPROVED": {"SUBMITTING"},
    "SUBMITTING": {"SUBMITTED", "FAILED"},
    "SUBMITTED": {"POLLING"},
    "POLLING": {"POLLING", "SUCCEEDED", "FAILED", "CANCELED"},
    "SUCCEEDED": {"DOWNLOADED"},
    "DOWNLOADED": {"VALIDATED"},
    "VALIDATED": {"USER_ACCEPTED", "USER_REJECTED"},
    "FAILED": set(),
    "CANCELED": set(),
    "USER_ACCEPTED": set(),
    "USER_REJECTED": set(),
}


class StateError(RuntimeError):
    pass


class TaskLog:
    def __init__(self, path: Path):
        self.path = path

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]
        prior_hash = None
        for sequence, event in enumerate(events):
            event_hash = event.get("eventHash")
            projection = {key: value for key, value in event.items() if key != "eventHash"}
            expected = hashlib.sha256(
                json.dumps(projection, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if event.get("sequence") != sequence or event.get("priorHash") != prior_hash or event_hash != expected:
                raise StateError("Provider task log integrity check failed")
            prior_hash = event_hash
        return events

    def append(self, state: str, *, timestamp: str, details: dict[str, Any] | None = None) -> None:
        prior = self.events()
        current = prior[-1]["state"] if prior else None
        if state not in TRANSITIONS.get(current, set()):
            raise StateError(f"Illegal reconstruction transition: {current} -> {state}")
        event = {
            "sequence": len(prior),
            "timestamp": timestamp,
            "state": state,
            "details": details or {},
            "priorHash": prior[-1]["eventHash"] if prior else None,
        }
        event["eventHash"] = hashlib.sha256(
            json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
