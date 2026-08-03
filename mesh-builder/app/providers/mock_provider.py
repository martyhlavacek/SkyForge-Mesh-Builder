from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from common.provider_credit_ledger import RecoveryCorrelation


@dataclass(frozen=True)
class MockTask:
    task_id: str
    request_digest: str
    state: str
    consumed_cost: Decimal
    recovery_correlation: Mapping[str, Any]
    history: tuple[Mapping[str, Any], ...]


class MockProvider:
    """Deterministic, persisted no-charge provider used only for lifecycle tests."""

    PROVIDER_ID = "mock_provider"
    PROVIDER_MODEL = "mock-lifecycle-v1"

    def __init__(self, store_path: Path) -> None:
        self.store_path = store_path

    def _read(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {"schemaVersion": "skyforge.mock-provider-store.v1", "dispatchCount": 0, "tasks": []}
        return json.loads(self.store_path.read_text(encoding="utf-8"))

    def _write(self, data: Mapping[str, Any]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store_path.with_name(f".{self.store_path.name}.{uuid.uuid4().hex}.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, sort_keys=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.store_path)

    @staticmethod
    def correlation(
        *,
        request_digest: str,
        authority_sha256: str,
        options_digest: str,
        account_identity_digest: str,
        dispatch_window_start: str,
        dispatch_window_end: str,
        expected_cost: Decimal | str | int,
    ) -> RecoveryCorrelation:
        return RecoveryCorrelation(
            request_digest=request_digest,
            provider_id=MockProvider.PROVIDER_ID,
            provider_model=MockProvider.PROVIDER_MODEL,
            resolved_provider_options_digest=options_digest,
            authority_set_sha256=authority_sha256,
            account_identity_digest=account_identity_digest,
            dispatch_window_start=dispatch_window_start,
            dispatch_window_end=dispatch_window_end,
            expected_cost_amount=Decimal(str(expected_cost)),
        )

    def dispatch(self, correlation: RecoveryCorrelation, *, scenario: str = "success") -> MockTask:
        terminal_state = {
            "success": "completed_captured",
            "failure_refund": "failed_refunded",
            "delayed": "processing",
            "timeout": "processing_timeout",
            "expiry": "expired_uncaptured",
            "capture_failure": "completed_capture_failed",
            "ambiguous_recovery": "processing",
        }.get(scenario)
        if terminal_state is None:
            raise ValueError(f"Unsupported mock scenario: {scenario}")
        data = self._read()
        dispatch_ordinal = int(data["dispatchCount"]) + 1
        data["dispatchCount"] = dispatch_ordinal
        correlation_json = correlation.as_json()
        task_id = hashlib.sha256(
            f"{correlation.request_digest}:{dispatch_ordinal}:{scenario}".encode("utf-8")
        ).hexdigest()[:24]
        consumed = Decimal("0") if scenario == "failure_refund" else correlation.expected_cost_amount
        history = [
            {"sequence": 1, "state": "submitted", "sanitized": True},
            {"sequence": 2, "state": terminal_state, "sanitized": True},
        ]
        task_json = {
            "taskId": task_id,
            "requestDigest": correlation.request_digest,
            "state": terminal_state,
            "consumedCost": format(consumed, "f"),
            "recoveryCorrelation": correlation_json,
            "history": history,
        }
        data["tasks"].append(task_json)
        if scenario == "ambiguous_recovery":
            twin = dict(task_json)
            twin["taskId"] = task_id + "-twin"
            data["tasks"].append(twin)
            data["dispatchCount"] = dispatch_ordinal + 1
        self._write(data)
        return self._to_task(task_json)

    def set_state(self, task_id: str, state: str, *, consumed_cost: Decimal | str | int | None = None) -> MockTask:
        data = self._read()
        for task in data["tasks"]:
            if task["taskId"] == task_id:
                task["state"] = state
                if consumed_cost is not None:
                    task["consumedCost"] = format(Decimal(str(consumed_cost)), "f")
                task["history"].append(
                    {"sequence": len(task["history"]) + 1, "state": state, "sanitized": True}
                )
                self._write(data)
                return self._to_task(task)
        raise KeyError(task_id)

    def get_task(self, task_id: str) -> MockTask | None:
        for task in self._read()["tasks"]:
            if task["taskId"] == task_id:
                return self._to_task(task)
        return None

    def list_recent_tasks(self, correlation: Mapping[str, Any]) -> Sequence[MockTask]:
        fields = (
            "requestDigest",
            "providerId",
            "providerModel",
            "resolvedProviderOptionsDigest",
            "authoritySetSha256",
            "accountIdentityDigest",
            "dispatchWindowStart",
            "dispatchWindowEnd",
            "expectedCost",
        )
        matches: list[MockTask] = []
        for task in self._read()["tasks"]:
            stored = task["recoveryCorrelation"]
            if all(stored.get(field) == correlation.get(field) for field in fields):
                matches.append(self._to_task(task))
        return matches

    def dispatch_count(self) -> int:
        return int(self._read()["dispatchCount"])

    @staticmethod
    def _to_task(task: Mapping[str, Any]) -> MockTask:
        return MockTask(
            task_id=str(task["taskId"]),
            request_digest=str(task["requestDigest"]),
            state=str(task["state"]),
            consumed_cost=Decimal(str(task["consumedCost"])),
            recovery_correlation=dict(task["recoveryCorrelation"]),
            history=tuple(dict(item) for item in task["history"]),
        )
