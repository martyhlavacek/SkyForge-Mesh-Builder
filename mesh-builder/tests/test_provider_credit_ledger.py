from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.providers.mock_operation import SimulatedProcessCrash, execute_mock_operation
from app.providers.mock_provider import MockProvider
from common.provider_credit_ledger import (
    CreditCaps,
    ProviderBudgetExceeded,
    ProviderCreditLedger,
    ProviderDispatchBlocked,
    ProviderStateError,
)

DIGEST_A = hashlib.sha256(b"a").hexdigest()
DIGEST_B = hashlib.sha256(b"b").hexdigest()
DIGEST_C = hashlib.sha256(b"c").hexdigest()
DIGEST_D = hashlib.sha256(b"d").hexdigest()


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> str:
        return self.value.isoformat()

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def ledger(tmp_path: Path, *, clock: Clock | None = None, pid: int = 1001) -> ProviderCreditLedger:
    return ProviderCreditLedger(
        tmp_path / "provider_credit_ledger.json",
        session_id="session-1",
        caps=CreditCaps.from_values(per_request=20, per_asset=40, per_session=60),
        process_id=pid,
        clock=clock or Clock(),
        pid_alive=lambda candidate: candidate == pid,
        stale_after=timedelta(seconds=5),
        lock_timeout_seconds=0.5,
    )


def correlation(provider: MockProvider, *, request_digest: str = DIGEST_A, cost: int = 20):
    return provider.correlation(
        request_digest=request_digest,
        authority_sha256=DIGEST_B,
        options_digest=DIGEST_C,
        account_identity_digest=DIGEST_D,
        dispatch_window_start="2026-08-01T12:00:00+00:00",
        dispatch_window_end="2026-08-01T12:05:00+00:00",
        expected_cost=cost,
    )


def create_reserved(book: ProviderCreditLedger, provider: MockProvider, *, digest: str = DIGEST_A):
    entry = book.create_intent(
        request_digest=digest,
        provider_id=provider.PROVIDER_ID,
        provider_model=provider.PROVIDER_MODEL,
        asset_id="asset-1",
        estimated_cost=20,
        correlation=correlation(provider, request_digest=digest),
    )
    return book.mark_reserved(entry["reservationId"])


def test_write_ahead_sequence_and_reserve_before_dispatch(tmp_path: Path):
    provider = MockProvider(tmp_path / "mock_tasks.json")
    book = ledger(tmp_path)
    result = execute_mock_operation(
        ledger=book,
        provider=provider,
        request_digest=DIGEST_A,
        asset_id="asset-1",
        expected_cost=20,
        correlation=correlation(provider),
        scenario="success",
    )
    snapshot = book.snapshot()
    events = snapshot["events"]
    assert [event["eventType"] for event in events[:3]] == [
        "intent_persisted",
        "budget_reserved",
        "provider_dispatched",
    ]
    assert [event["sequence"] for event in events] == sorted(event["sequence"] for event in events)
    assert result.reservation["state"] == "reconciled"
    assert result.reservation["actualCost"] == {"unit": "credits", "amount": 20.0}
    assert provider.dispatch_count() == 1


def test_provider_credits_are_separate_from_openai_usd_ledger(tmp_path: Path):
    openai_ledger = tmp_path / "image_spend_ledger.json"
    original = b'{"schemaVersion":"skyforge.image-spend-ledger.v1","entries":[]}\n'
    openai_ledger.write_bytes(original)
    provider = MockProvider(tmp_path / "mock_tasks.json")
    create_reserved(ledger(tmp_path), provider)
    assert openai_ledger.read_bytes() == original


def test_request_asset_and_session_caps_are_authoritative(tmp_path: Path):
    provider = MockProvider(tmp_path / "mock_tasks.json")
    book = ledger(tmp_path)
    with pytest.raises(ProviderBudgetExceeded, match="per-request"):
        book.create_intent(
            request_digest=DIGEST_A,
            provider_id=provider.PROVIDER_ID,
            provider_model=provider.PROVIDER_MODEL,
            asset_id="asset-1",
            estimated_cost=21,
            correlation=correlation(provider, cost=21),
        )
    create_reserved(book, provider, digest=DIGEST_A)
    second = book.create_intent(
        request_digest=DIGEST_B,
        provider_id=provider.PROVIDER_ID,
        provider_model=provider.PROVIDER_MODEL,
        asset_id="asset-1",
        estimated_cost=20,
        correlation=correlation(provider, request_digest=DIGEST_B),
    )
    book.mark_reserved(second["reservationId"])
    with pytest.raises(ProviderBudgetExceeded, match="per-asset"):
        book.create_intent(
            request_digest=DIGEST_C,
            provider_id=provider.PROVIDER_ID,
            provider_model=provider.PROVIDER_MODEL,
            asset_id="asset-1",
            estimated_cost=1,
            correlation=correlation(provider, request_digest=DIGEST_C, cost=1),
        )


def test_crash_after_intent_releases_without_dispatch(tmp_path: Path):
    provider = MockProvider(tmp_path / "mock_tasks.json")
    book = ledger(tmp_path)
    with pytest.raises(SimulatedProcessCrash):
        execute_mock_operation(
            ledger=book,
            provider=provider,
            request_digest=DIGEST_A,
            asset_id="asset-1",
            expected_cost=20,
            correlation=correlation(provider),
            scenario="success",
            crash_point="after_intent",
        )
    outcomes = book.recover(provider)
    assert outcomes[0]["state"] == "released"
    assert provider.dispatch_count() == 0


def test_crash_after_reserve_releases_only_after_zero_provider_matches(tmp_path: Path):
    provider = MockProvider(tmp_path / "mock_tasks.json")
    book = ledger(tmp_path)
    with pytest.raises(SimulatedProcessCrash):
        execute_mock_operation(
            ledger=book,
            provider=provider,
            request_digest=DIGEST_A,
            asset_id="asset-1",
            expected_cost=20,
            correlation=correlation(provider),
            scenario="success",
            crash_point="after_reserve",
        )
    outcomes = book.recover(provider)
    assert outcomes[0]["state"] == "released"
    events = book.snapshot()["events"]
    assert events[-1]["details"]["reason"] == "provider_query_proved_no_dispatch"


def test_orphaned_dispatch_uniquely_correlates_and_is_adopted(tmp_path: Path):
    provider = MockProvider(tmp_path / "mock_tasks.json")
    book = ledger(tmp_path)
    with pytest.raises(SimulatedProcessCrash):
        execute_mock_operation(
            ledger=book,
            provider=provider,
            request_digest=DIGEST_A,
            asset_id="asset-1",
            expected_cost=20,
            correlation=correlation(provider),
            scenario="success",
            crash_point="after_dispatch_before_task_id",
        )
    outcomes = book.recover(provider)
    assert outcomes[0]["state"] == "reconciled"
    reservation = book.snapshot()["reservations"][0]
    assert reservation["providerTaskId"] is not None
    assert reservation["correspondenceStatus"] == "unique_correlated_match"


def test_ambiguous_orphan_remains_unresolved_and_charged(tmp_path: Path):
    provider = MockProvider(tmp_path / "mock_tasks.json")
    book = ledger(tmp_path)
    with pytest.raises(SimulatedProcessCrash):
        execute_mock_operation(
            ledger=book,
            provider=provider,
            request_digest=DIGEST_A,
            asset_id="asset-1",
            expected_cost=20,
            correlation=correlation(provider),
            scenario="ambiguous_recovery",
            crash_point="after_dispatch_before_task_id",
        )
    outcomes = book.recover(provider)
    assert outcomes[0]["state"] == "unresolved"
    assert book.totals(asset_id="asset-1") == {"sessionCredits": "20.000000", "assetCredits": "20.000000"}
    with pytest.raises(ProviderDispatchBlocked, match="Unresolved"):
        book.assert_dispatch_allowed(request_digest=DIGEST_B)


def test_known_task_id_is_authoritative(tmp_path: Path):
    provider = MockProvider(tmp_path / "mock_tasks.json")
    book = ledger(tmp_path)
    reserved = create_reserved(book, provider)
    task = provider.dispatch(correlation(provider), scenario="success")
    book.mark_submitted(reserved["reservationId"], provider_task_id=task.task_id)
    # Add a second correspondence-identical task. Recovery must still use the known ID.
    provider.dispatch(correlation(provider), scenario="success")
    outcome = book.recover(provider)[0]
    assert outcome["state"] == "reconciled"
    assert book.snapshot()["reservations"][0]["correspondenceStatus"] == "known_task_id"


@pytest.mark.parametrize(
    ("scenario", "expected_state", "expected_cost", "last_event"),
    [
        ("failure_refund", "released", "0.000000", "reservation_released"),
        ("delayed", "unresolved", "20.000000", "reservation_unresolved"),
        ("timeout", "unresolved", "20.000000", "reservation_unresolved"),
        ("expiry", "unresolved", "20.000000", "expired_uncaptured"),
        ("capture_failure", "unresolved", "20.000000", "capture_failed_unresolved"),
    ],
)
def test_mock_fault_states_fail_closed(
    tmp_path: Path, scenario: str, expected_state: str, expected_cost: str, last_event: str
):
    provider = MockProvider(tmp_path / f"mock_{scenario}.json")
    book = ProviderCreditLedger(
        tmp_path / f"ledger_{scenario}.json",
        session_id="session-1",
        caps=CreditCaps.from_values(per_request=20, per_asset=40, per_session=60),
    )
    result = execute_mock_operation(
        ledger=book,
        provider=provider,
        request_digest=DIGEST_A,
        asset_id="asset-1",
        expected_cost=20,
        correlation=correlation(provider),
        scenario=scenario,
    )
    assert result.reservation["state"] == expected_state
    assert book.totals(asset_id="asset-1")["assetCredits"] == expected_cost
    assert book.snapshot()["events"][-1]["eventType"] == last_event


def test_manual_adjudication_appends_event_without_editing_prior_history(tmp_path: Path):
    provider = MockProvider(tmp_path / "mock_tasks.json")
    book = ledger(tmp_path)
    reserved = create_reserved(book, provider)
    book.mark_unresolved(reserved["reservationId"], reason="multiple_matches_unresolved", match_count=2)
    before = book.snapshot()["events"]
    result = book.manual_adjudicate(
        reserved["reservationId"], decision="not_charged", consumed_cost=0, rationale="provider evidence proves no charge"
    )
    after = book.snapshot()["events"]
    assert after[: len(before)] == before
    assert after[-1]["eventType"] == "manual_adjudication"
    assert result["state"] == "released"


def test_duplicate_submit_is_rejected_before_transport_under_concurrency(tmp_path: Path):
    provider = MockProvider(tmp_path / "mock_tasks.json")
    path = tmp_path / "provider_credit_ledger.json"
    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def worker(pid: int) -> None:
        book = ProviderCreditLedger(
            path,
            session_id="session-1",
            caps=CreditCaps.from_values(per_request=20, per_asset=40, per_session=60),
            process_id=pid,
            pid_alive=lambda _pid: True,
            lock_timeout_seconds=2,
        )
        barrier.wait()
        try:
            execute_mock_operation(
                ledger=book,
                provider=provider,
                request_digest=DIGEST_A,
                asset_id="asset-1",
                expected_cost=20,
                correlation=correlation(provider),
                scenario="success",
            )
        except ProviderDispatchBlocked:
            outcome = "blocked"
        else:
            outcome = "dispatched"
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=(2001,)), threading.Thread(target=worker, args=(2002,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["blocked", "dispatched"]
    assert provider.dispatch_count() == 1


def test_stale_lock_recovery_uses_pid_and_heartbeat_and_preserves_history(tmp_path: Path):
    clock = Clock()
    book = ledger(tmp_path, clock=clock, pid=3002)
    book.lock_path.parent.mkdir(parents=True, exist_ok=True)
    book.lock_path.write_text(
        json.dumps({"pid": 3001, "heartbeatAt": (clock.value - timedelta(seconds=10)).isoformat()}) + "\n",
        encoding="utf-8",
    )
    snapshot = book.snapshot()
    assert snapshot["events"][0]["eventType"] == "stale_lock_recovered"
    assert snapshot["events"][0]["details"]["priorOwner"]["pid"] == 3001


def test_release_of_consumed_credits_is_forbidden(tmp_path: Path):
    provider = MockProvider(tmp_path / "mock_tasks.json")
    book = ledger(tmp_path)
    result = execute_mock_operation(
        ledger=book,
        provider=provider,
        request_digest=DIGEST_A,
        asset_id="asset-1",
        expected_cost=20,
        correlation=correlation(provider),
        scenario="success",
    )
    with pytest.raises(ProviderStateError, match="Consumed credits"):
        book.release(result.reservation["reservationId"], reason="not allowed")


def test_frozen_reservation_and_task_record_projections_validate(tmp_path: Path):
    from common.schema_validation import validate_document

    provider = MockProvider(tmp_path / "mock_tasks.json")
    book = ledger(tmp_path)
    result = execute_mock_operation(
        ledger=book,
        provider=provider,
        request_digest=DIGEST_A,
        asset_id="asset-1",
        expected_cost=20,
        correlation=correlation(provider),
        scenario="success",
    )
    validate_document(
        "provider_spend_reservation.schema.json",
        book.reservation_contract(result.reservation["reservationId"]),
    )
    validate_document(
        "provider_task_record.schema.json",
        book.task_record_contract(result.reservation["reservationId"]),
    )


def test_recovery_correlation_has_exact_mbs136_field_set(tmp_path: Path):
    provider = MockProvider(tmp_path / "mock_tasks.json")
    payload = correlation(provider).as_json()
    assert set(payload) == {
        "requestDigest",
        "providerId",
        "providerModel",
        "resolvedProviderOptionsDigest",
        "authoritySetSha256",
        "accountIdentityDigest",
        "dispatchWindowStart",
        "dispatchWindowEnd",
        "expectedCost",
    }


def test_mock_provider_history_is_sanitized_and_no_charge_classified(tmp_path: Path):
    provider = MockProvider(tmp_path / "mock_tasks.json")
    task = provider.dispatch(correlation(provider), scenario="success")
    assert all(event["sanitized"] is True for event in task.history)
    assert provider.PROVIDER_ID == "mock_provider"
    assert not any("credential" in json.dumps(event).lower() for event in task.history)
