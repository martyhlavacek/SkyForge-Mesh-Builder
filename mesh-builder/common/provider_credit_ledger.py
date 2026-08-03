from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Protocol, Sequence


class ProviderLedgerError(RuntimeError):
    """Base failure for the authoritative provider-credit ledger."""


class ProviderLedgerUnavailable(ProviderLedgerError):
    """The ledger or its lock cannot be read/written safely."""


class ProviderBudgetExceeded(ProviderLedgerError):
    """A write-ahead reservation would exceed a configured local cap."""


class ProviderDispatchBlocked(ProviderLedgerError):
    """Dispatch is blocked by an unresolved or duplicate reservation."""


class ProviderStateError(ProviderLedgerError):
    """An invalid state transition was requested."""


TERMINAL_RESERVATION_STATES = frozenset({"reconciled", "released"})
ACTIVE_CHARGE_STATES = frozenset({"intent_persisted", "reserved", "submitted", "unresolved"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decimal(value: Decimal | str | int | float) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ProviderLedgerError(f"Invalid credit amount: {value!r}") from exc
    if parsed < 0:
        raise ProviderLedgerError("Credit amounts cannot be negative")
    return parsed.quantize(Decimal("0.000001"))


def _amount(value: Decimal | str | int | float) -> str:
    return format(_decimal(value), "f")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass(frozen=True)
class CreditCaps:
    per_request: Decimal
    per_asset: Decimal
    per_session: Decimal

    @classmethod
    def from_values(
        cls,
        *,
        per_request: Decimal | str | int | float,
        per_asset: Decimal | str | int | float,
        per_session: Decimal | str | int | float,
    ) -> "CreditCaps":
        return cls(_decimal(per_request), _decimal(per_asset), _decimal(per_session))


@dataclass(frozen=True)
class RecoveryCorrelation:
    request_digest: str
    provider_id: str
    provider_model: str
    resolved_provider_options_digest: str
    authority_set_sha256: str
    account_identity_digest: str
    dispatch_window_start: str
    dispatch_window_end: str
    expected_cost_amount: Decimal
    expected_cost_unit: str = "credits"

    def as_json(self) -> dict[str, Any]:
        digest_fields = {
            "requestDigest": self.request_digest,
            "resolvedProviderOptionsDigest": self.resolved_provider_options_digest,
            "authoritySetSha256": self.authority_set_sha256,
            "accountIdentityDigest": self.account_identity_digest,
        }
        for name, value in digest_fields.items():
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ProviderLedgerError(f"{name} must be a lowercase SHA-256 digest")
        if self.expected_cost_unit != "credits":
            raise ProviderLedgerError("The provider-credit ledger accepts credits only")
        return {
            "requestDigest": self.request_digest,
            "providerId": self.provider_id,
            "providerModel": self.provider_model,
            "resolvedProviderOptionsDigest": self.resolved_provider_options_digest,
            "authoritySetSha256": self.authority_set_sha256,
            "accountIdentityDigest": self.account_identity_digest,
            "dispatchWindowStart": self.dispatch_window_start,
            "dispatchWindowEnd": self.dispatch_window_end,
            "expectedCost": {"unit": self.expected_cost_unit, "amount": float(_decimal(self.expected_cost_amount))},
        }


class RecoverableProviderTask(Protocol):
    task_id: str
    request_digest: str
    state: str
    consumed_cost: Decimal
    recovery_correlation: Mapping[str, Any]


class RecoveryProvider(Protocol):
    def get_task(self, task_id: str) -> RecoverableProviderTask | None: ...

    def list_recent_tasks(self, correlation: Mapping[str, Any]) -> Sequence[RecoverableProviderTask]: ...


class ProviderCreditLedger:
    """Authoritative, append-evidenced local reservation ledger for provider credits.

    The existing OpenAI USD ledger is intentionally not imported or modified. Every
    mutation is a whole-file atomic replacement under an O_EXCL single-writer lock.
    """

    SCHEMA_VERSION = "skyforge.provider-credit-ledger.v1"

    def __init__(
        self,
        path: Path,
        *,
        session_id: str,
        caps: CreditCaps,
        process_id: int | None = None,
        clock: Callable[[], str] = utc_now,
        pid_alive: Callable[[int], bool] = _pid_alive,
        stale_after: timedelta = timedelta(seconds=30),
        lock_timeout_seconds: float = 5.0,
    ) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        self.session_id = session_id
        self.caps = caps
        self.process_id = process_id or os.getpid()
        self.clock = clock
        self.pid_alive = pid_alive
        self.stale_after = stale_after
        self.lock_timeout_seconds = lock_timeout_seconds

    def _empty(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.SCHEMA_VERSION,
            "nextSequence": 1,
            "reservations": [],
            "events": [],
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderLedgerUnavailable("Provider credit ledger cannot be read safely") from exc
        if (
            not isinstance(data, dict)
            or data.get("schemaVersion") != self.SCHEMA_VERSION
            or not isinstance(data.get("nextSequence"), int)
            or not isinstance(data.get("reservations"), list)
            or not isinstance(data.get("events"), list)
        ):
            raise ProviderLedgerUnavailable("Provider credit ledger schema is invalid")
        return data

    def _write(self, data: Mapping[str, Any]) -> None:
        temp = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temp.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, indent=2, sort_keys=False, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
            try:
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except OSError as exc:
            temp.unlink(missing_ok=True)
            raise ProviderLedgerUnavailable("Provider credit ledger cannot be written safely") from exc

    def _lock_owner(self) -> dict[str, Any] | None:
        # O_EXCL establishes ownership before the new owner can fsync metadata. A
        # contender may briefly observe an empty lock file, so retry that narrow
        # initialization window instead of misclassifying it as corruption.
        for attempt in range(5):
            try:
                text = self.lock_path.read_text(encoding="utf-8")
                if not text.strip():
                    raise json.JSONDecodeError("empty lock metadata", text, 0)
                return json.loads(text)
            except FileNotFoundError:
                return None
            except json.JSONDecodeError as exc:
                if attempt < 4:
                    time.sleep(0.002)
                    continue
                raise ProviderLedgerUnavailable("Provider ledger lock metadata is invalid") from exc
            except OSError as exc:
                raise ProviderLedgerUnavailable("Provider ledger lock cannot be inspected safely") from exc
        raise ProviderLedgerUnavailable("Provider ledger lock cannot be inspected safely")

    def _stale(self, owner: Mapping[str, Any]) -> bool:
        try:
            pid = int(owner["pid"])
            heartbeat = _parse_time(str(owner["heartbeatAt"]))
            now = _parse_time(self.clock())
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderLedgerUnavailable("Provider ledger lock metadata is invalid") from exc
        return (not self.pid_alive(pid)) or (now - heartbeat > self.stale_after)

    @contextmanager
    def _single_writer(self) -> Iterator[None]:
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProviderLedgerUnavailable("Provider ledger directory cannot be created") from exc
        deadline = time.monotonic() + self.lock_timeout_seconds
        stale_owner: dict[str, Any] | None = None
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                owner = self._lock_owner()
                if owner is not None and self._stale(owner):
                    stale_owner = dict(owner)
                    try:
                        self.lock_path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise ProviderLedgerUnavailable("Provider ledger single-writer lock is busy")
                time.sleep(0.01)
                continue
            except OSError as exc:
                raise ProviderLedgerUnavailable("Provider ledger lock cannot be acquired") from exc
            else:
                try:
                    owner = {"pid": self.process_id, "heartbeatAt": self.clock()}
                    os.write(fd, (json.dumps(owner, sort_keys=True) + "\n").encode("utf-8"))
                    os.fsync(fd)
                finally:
                    os.close(fd)
                break
        try:
            if stale_owner is not None:
                data = self._read()
                self._append_event(
                    data,
                    reservation_id=None,
                    event_type="stale_lock_recovered",
                    details={"priorOwner": stale_owner, "newOwnerPid": self.process_id},
                )
                self._write(data)
            yield
        finally:
            try:
                current = self._lock_owner()
                if current is not None and int(current.get("pid", -1)) == self.process_id:
                    self.lock_path.unlink(missing_ok=True)
            except (OSError, ValueError, ProviderLedgerUnavailable):
                pass

    def _next_sequence(self, data: dict[str, Any]) -> int:
        sequence = int(data["nextSequence"])
        data["nextSequence"] = sequence + 1
        return sequence

    def _append_event(
        self,
        data: dict[str, Any],
        *,
        reservation_id: str | None,
        event_type: str,
        details: Mapping[str, Any],
    ) -> dict[str, Any]:
        event = {
            "schemaVersion": "skyforge.provider-credit-ledger-event.v1",
            "sequence": self._next_sequence(data),
            "eventId": uuid.uuid4().hex,
            "reservationId": reservation_id,
            "eventType": event_type,
            "occurredAt": self.clock(),
            "process": {"pid": self.process_id, "heartbeatAt": self.clock()},
            "details": deepcopy(dict(details)),
        }
        data["events"].append(event)
        return event

    @staticmethod
    def _find(data: Mapping[str, Any], reservation_id: str) -> dict[str, Any]:
        for reservation in data["reservations"]:
            if reservation.get("reservationId") == reservation_id:
                return reservation
        raise ProviderStateError(f"Unknown reservation: {reservation_id}")

    @staticmethod
    def _charged_amount(reservation: Mapping[str, Any]) -> Decimal:
        state = reservation.get("state")
        if state == "released":
            return Decimal("0")
        if state == "reconciled" and reservation.get("actualCost") is not None:
            return _decimal(reservation["actualCost"]["amount"])
        return _decimal(reservation["estimatedCost"]["amount"])

    def totals(self, *, asset_id: str | None = None, data: Mapping[str, Any] | None = None) -> dict[str, str]:
        ledger = data or self._read()
        session = Decimal("0")
        asset = Decimal("0")
        for reservation in ledger["reservations"]:
            charged = self._charged_amount(reservation)
            if reservation.get("sessionId") == self.session_id:
                session += charged
            if asset_id is not None and reservation.get("assetId") == asset_id:
                asset += charged
        return {"sessionCredits": _amount(session), "assetCredits": _amount(asset)}

    def snapshot(self) -> dict[str, Any]:
        with self._single_writer():
            return deepcopy(self._read())

    def reservation_contract(self, reservation_id: str) -> dict[str, Any]:
        """Return the exact frozen provider-spend-reservation.v1 projection."""
        with self._single_writer():
            reservation = deepcopy(self._find(self._read(), reservation_id))
        document = {
            "schemaVersion": "skyforge.provider-spend-reservation.v1",
            "sequence": reservation["sequence"],
            "reservationId": reservation["reservationId"],
            "requestDigest": reservation["requestDigest"],
            "providerId": reservation["providerId"],
            "estimatedCost": reservation["estimatedCost"],
            "state": reservation["state"],
            "createdAt": reservation["createdAt"],
            "updatedAt": reservation["updatedAt"],
            "process": reservation["process"],
        }
        if reservation.get("providerTaskId"):
            document["providerTaskId"] = reservation["providerTaskId"]
        return document

    def task_record_contract(self, reservation_id: str) -> dict[str, Any]:
        """Return the exact frozen provider-task-record.v1 projection for mock evidence."""
        with self._single_writer():
            reservation = deepcopy(self._find(self._read(), reservation_id))
        correspondence = reservation.get("correspondenceStatus")
        if correspondence is None:
            correspondence = "not_required_local"
        document = {
            "schemaVersion": "skyforge.provider-task-record.v1",
            "reservationId": reservation["reservationId"],
            "requestDigest": reservation["requestDigest"],
            "state": reservation["state"],
            "sequence": reservation["sequence"],
            "timestamps": {
                "createdAt": reservation["createdAt"],
                "updatedAt": reservation["updatedAt"],
            },
            "resolvedRequestDigest": reservation["requestDigest"],
            "evidenceClass": "mock_provider",
            "recoveryCorrelation": reservation["recoveryCorrelation"],
            "correspondenceStatus": correspondence,
        }
        if reservation.get("providerTaskId"):
            document["providerTaskId"] = reservation["providerTaskId"]
        return document

    def assert_dispatch_allowed(self, *, request_digest: str | None = None) -> None:
        with self._single_writer():
            data = self._read()
            unresolved = [item["reservationId"] for item in data["reservations"] if item["state"] == "unresolved"]
            if unresolved:
                raise ProviderDispatchBlocked(f"Unresolved reservations block dispatch: {', '.join(unresolved)}")
            if request_digest is not None:
                duplicate = next(
                    (
                        item
                        for item in data["reservations"]
                        if item["requestDigest"] == request_digest and item["state"] != "released"
                    ),
                    None,
                )
                if duplicate is not None:
                    raise ProviderDispatchBlocked(
                        f"Request digest already has reservation {duplicate['reservationId']} in state {duplicate['state']}"
                    )

    def create_intent(
        self,
        *,
        request_digest: str,
        provider_id: str,
        provider_model: str,
        asset_id: str,
        estimated_cost: Decimal | str | int | float,
        correlation: RecoveryCorrelation,
        reservation_id: str | None = None,
    ) -> dict[str, Any]:
        estimate = _decimal(estimated_cost)
        if estimate > self.caps.per_request:
            raise ProviderBudgetExceeded("Estimated credits exceed the per-request cap")
        correlation_json = correlation.as_json()
        if correlation_json["requestDigest"] != request_digest or correlation_json["providerId"] != provider_id:
            raise ProviderLedgerError("Recovery correlation does not match the reservation request/provider")
        with self._single_writer():
            data = self._read()
            unresolved = [item["reservationId"] for item in data["reservations"] if item["state"] == "unresolved"]
            if unresolved:
                raise ProviderDispatchBlocked(f"Unresolved reservations block dispatch: {', '.join(unresolved)}")
            duplicate = next(
                (item for item in data["reservations"] if item["requestDigest"] == request_digest and item["state"] != "released"),
                None,
            )
            if duplicate is not None:
                raise ProviderDispatchBlocked("Duplicate request rejected before provider transport")
            totals = self.totals(asset_id=asset_id, data=data)
            if _decimal(totals["assetCredits"]) + estimate > self.caps.per_asset:
                raise ProviderBudgetExceeded("Estimated credits would exceed the per-asset cap")
            if _decimal(totals["sessionCredits"]) + estimate > self.caps.per_session:
                raise ProviderBudgetExceeded("Estimated credits would exceed the per-session cap")
            now = self.clock()
            reservation = {
                "schemaVersion": "skyforge.provider-spend-reservation.v1",
                "sequence": self._next_sequence(data),
                "reservationId": reservation_id or uuid.uuid4().hex,
                "requestDigest": request_digest,
                "providerId": provider_id,
                "providerModel": provider_model,
                "assetId": asset_id,
                "sessionId": self.session_id,
                "estimatedCost": {"unit": "credits", "amount": float(estimate)},
                "actualCost": None,
                "state": "intent_persisted",
                "createdAt": now,
                "updatedAt": now,
                "providerTaskId": None,
                "process": {"pid": self.process_id, "heartbeatAt": now},
                "recoveryCorrelation": correlation_json,
                "correspondenceStatus": None,
            }
            data["reservations"].append(reservation)
            self._append_event(
                data,
                reservation_id=reservation["reservationId"],
                event_type="intent_persisted",
                details={"requestDigest": request_digest, "estimatedCost": reservation["estimatedCost"]},
            )
            self._write(data)
            return deepcopy(reservation)

    def mark_reserved(self, reservation_id: str) -> dict[str, Any]:
        return self._transition(reservation_id, expected={"intent_persisted"}, state="reserved", event_type="budget_reserved")

    def mark_submitted(self, reservation_id: str, *, provider_task_id: str | None) -> dict[str, Any]:
        return self._transition(
            reservation_id,
            expected={"reserved"},
            state="submitted",
            event_type="provider_dispatched",
            updates={
                "providerTaskId": provider_task_id,
                "correspondenceStatus": "known_task_id" if provider_task_id else None,
            },
            details={"providerTaskId": provider_task_id},
        )

    def persist_task_id(self, reservation_id: str, provider_task_id: str, *, correspondence_status: str) -> dict[str, Any]:
        with self._single_writer():
            data = self._read()
            reservation = self._find(data, reservation_id)
            if reservation["state"] not in {"reserved", "submitted", "unresolved"}:
                raise ProviderStateError("Task ID cannot be persisted from the current reservation state")
            reservation["providerTaskId"] = provider_task_id
            reservation["state"] = "submitted"
            reservation["correspondenceStatus"] = correspondence_status
            reservation["updatedAt"] = self.clock()
            reservation["process"] = {"pid": self.process_id, "heartbeatAt": self.clock()}
            self._append_event(
                data,
                reservation_id=reservation_id,
                event_type="provider_task_id_persisted",
                details={"providerTaskId": provider_task_id, "correspondenceStatus": correspondence_status},
            )
            self._write(data)
            return deepcopy(reservation)

    def mark_unresolved(self, reservation_id: str, *, reason: str, match_count: int | None = None) -> dict[str, Any]:
        correspondence_status = None
        if reason == "zero_matches_unresolved":
            correspondence_status = "zero_matches_unresolved"
        elif reason == "multiple_matches_unresolved":
            correspondence_status = "multiple_matches_unresolved"
        return self._transition(
            reservation_id,
            expected={"reserved", "submitted", "unresolved"},
            state="unresolved",
            event_type="reservation_unresolved",
            updates={"correspondenceStatus": correspondence_status},
            details={"reason": reason, "matchCount": match_count},
        )

    def reconcile(
        self,
        reservation_id: str,
        *,
        consumed_cost: Decimal | str | int | float,
        provider_state: str,
        capture_complete: bool,
    ) -> dict[str, Any]:
        actual = _decimal(consumed_cost)
        with self._single_writer():
            data = self._read()
            reservation = self._find(data, reservation_id)
            if reservation["state"] not in {"submitted", "unresolved"}:
                raise ProviderStateError("Only submitted/unresolved reservations can be reconciled")
            if provider_state == "completed" and not capture_complete:
                reservation["state"] = "unresolved"
                event_type = "capture_failed_unresolved"
            elif provider_state == "expired_uncaptured":
                reservation["state"] = "unresolved"
                event_type = "expired_uncaptured"
            else:
                reservation["state"] = "reconciled"
                event_type = "credits_reconciled"
            reservation["actualCost"] = {"unit": "credits", "amount": float(actual)}
            reservation["updatedAt"] = self.clock()
            self._append_event(
                data,
                reservation_id=reservation_id,
                event_type=event_type,
                details={
                    "providerState": provider_state,
                    "captureComplete": capture_complete,
                    "actualCost": reservation["actualCost"],
                },
            )
            self._write(data)
            return deepcopy(reservation)

    def release(self, reservation_id: str, *, reason: str) -> dict[str, Any]:
        with self._single_writer():
            data = self._read()
            reservation = self._find(data, reservation_id)
            if reservation["state"] not in {"intent_persisted", "reserved", "reconciled"}:
                raise ProviderStateError("Reservation cannot be released from its current state")
            if reservation["state"] == "reconciled" and reservation.get("actualCost", {}).get("amount", 0) != 0:
                raise ProviderStateError("Consumed credits cannot be released")
            reservation["state"] = "released"
            reservation["updatedAt"] = self.clock()
            self._append_event(
                data,
                reservation_id=reservation_id,
                event_type="reservation_released",
                details={"reason": reason},
            )
            self._write(data)
            return deepcopy(reservation)

    def manual_adjudicate(
        self,
        reservation_id: str,
        *,
        decision: str,
        consumed_cost: Decimal | str | int | float,
        rationale: str,
    ) -> dict[str, Any]:
        if decision not in {"charged", "not_charged"}:
            raise ProviderLedgerError("Manual adjudication decision must be charged or not_charged")
        actual = _decimal(consumed_cost)
        if decision == "not_charged" and actual != 0:
            raise ProviderLedgerError("not_charged adjudication requires zero consumed cost")
        with self._single_writer():
            data = self._read()
            reservation = self._find(data, reservation_id)
            if reservation["state"] != "unresolved":
                raise ProviderStateError("Only unresolved reservations may be manually adjudicated")
            self._append_event(
                data,
                reservation_id=reservation_id,
                event_type="manual_adjudication",
                details={"decision": decision, "consumedCost": _amount(actual), "rationale": rationale},
            )
            reservation["actualCost"] = {"unit": "credits", "amount": float(actual)}
            reservation["state"] = "reconciled" if actual != 0 else "released"
            reservation["updatedAt"] = self.clock()
            self._write(data)
            return deepcopy(reservation)

    def _transition(
        self,
        reservation_id: str,
        *,
        expected: set[str],
        state: str,
        event_type: str,
        updates: Mapping[str, Any] | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._single_writer():
            data = self._read()
            reservation = self._find(data, reservation_id)
            if reservation["state"] not in expected:
                raise ProviderStateError(
                    f"Reservation {reservation_id} state {reservation['state']!r} not in {sorted(expected)!r}"
                )
            reservation["state"] = state
            reservation.update(dict(updates or {}))
            reservation["updatedAt"] = self.clock()
            reservation["process"] = {"pid": self.process_id, "heartbeatAt": self.clock()}
            self._append_event(
                data,
                reservation_id=reservation_id,
                event_type=event_type,
                details=dict(details or {}),
            )
            self._write(data)
            return deepcopy(reservation)

    def recover(self, provider: RecoveryProvider) -> list[dict[str, Any]]:
        """Reconcile all non-terminal reservations in monotonic order.

        The provider is queried outside the ledger lock only via deterministic methods;
        each adoption/state mutation is separately persisted. New dispatch must remain
        disabled until this pass has left no unresolved records.
        """
        snapshot = self.snapshot()
        outcomes: list[dict[str, Any]] = []
        pending = sorted(
            (item for item in snapshot["reservations"] if item["state"] not in TERMINAL_RESERVATION_STATES),
            key=lambda item: item["sequence"],
        )
        for item in pending:
            reservation_id = item["reservationId"]
            state = item["state"]
            task_id = item.get("providerTaskId")
            if state == "intent_persisted":
                outcomes.append(self.release(reservation_id, reason="crash_before_local_reserve_no_dispatch"))
                continue
            if task_id:
                task = provider.get_task(task_id)
                if task is None:
                    outcomes.append(self.mark_unresolved(reservation_id, reason="known_task_id_not_found"))
                    continue
                self.persist_task_id(reservation_id, task.task_id, correspondence_status="known_task_id")
                outcomes.append(self._recover_task(reservation_id, task))
                continue
            matches = list(provider.list_recent_tasks(item["recoveryCorrelation"]))
            if len(matches) == 0:
                if state == "reserved":
                    outcomes.append(self.release(reservation_id, reason="provider_query_proved_no_dispatch"))
                else:
                    outcomes.append(self.mark_unresolved(reservation_id, reason="zero_matches_unresolved", match_count=0))
                continue
            if len(matches) > 1:
                outcomes.append(self.mark_unresolved(reservation_id, reason="multiple_matches_unresolved", match_count=len(matches)))
                continue
            task = matches[0]
            self.persist_task_id(reservation_id, task.task_id, correspondence_status="unique_correlated_match")
            outcomes.append(self._recover_task(reservation_id, task))
        return outcomes

    def _recover_task(self, reservation_id: str, task: RecoverableProviderTask) -> dict[str, Any]:
        if task.state == "failed_refunded":
            reconciled = self.reconcile(
                reservation_id,
                consumed_cost=0,
                provider_state="failed",
                capture_complete=True,
            )
            return self.release(reconciled["reservationId"], reason="provider_failure_refunded")
        if task.state == "completed_captured":
            return self.reconcile(
                reservation_id,
                consumed_cost=task.consumed_cost,
                provider_state="completed",
                capture_complete=True,
            )
        if task.state == "completed_capture_failed":
            return self.reconcile(
                reservation_id,
                consumed_cost=task.consumed_cost,
                provider_state="completed",
                capture_complete=False,
            )
        if task.state == "expired_uncaptured":
            return self.reconcile(
                reservation_id,
                consumed_cost=task.consumed_cost,
                provider_state="expired_uncaptured",
                capture_complete=False,
            )
        return self.mark_unresolved(reservation_id, reason=f"provider_nonterminal:{task.state}")
