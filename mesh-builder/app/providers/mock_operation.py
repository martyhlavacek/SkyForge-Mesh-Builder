from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from common.provider_credit_ledger import ProviderCreditLedger, RecoveryCorrelation

from .mock_provider import MockProvider, MockTask


class SimulatedProcessCrash(RuntimeError):
    pass


@dataclass(frozen=True)
class MockOperationResult:
    reservation: dict
    task: MockTask | None


def execute_mock_operation(
    *,
    ledger: ProviderCreditLedger,
    provider: MockProvider,
    request_digest: str,
    asset_id: str,
    expected_cost: Decimal | str | int,
    correlation: RecoveryCorrelation,
    scenario: str,
    crash_point: str | None = None,
    before_dispatch: Callable[[], None] | None = None,
) -> MockOperationResult:
    """Exercise exact reserve-before-dispatch ordering with injectable crash points."""
    reservation = ledger.create_intent(
        request_digest=request_digest,
        provider_id=provider.PROVIDER_ID,
        provider_model=provider.PROVIDER_MODEL,
        asset_id=asset_id,
        estimated_cost=expected_cost,
        correlation=correlation,
    )
    if crash_point == "after_intent":
        raise SimulatedProcessCrash("crash after intent persistence")
    reservation = ledger.mark_reserved(reservation["reservationId"])
    if crash_point == "after_reserve":
        raise SimulatedProcessCrash("crash after reserve before dispatch")
    if before_dispatch is not None:
        before_dispatch()
    task = provider.dispatch(correlation, scenario=scenario)
    if crash_point == "after_dispatch_before_task_id":
        raise SimulatedProcessCrash("crash after provider dispatch before task ID persistence")
    reservation = ledger.mark_submitted(reservation["reservationId"], provider_task_id=task.task_id)
    if task.state == "completed_captured":
        reservation = ledger.reconcile(
            reservation["reservationId"],
            consumed_cost=task.consumed_cost,
            provider_state="completed",
            capture_complete=True,
        )
    elif task.state == "failed_refunded":
        reservation = ledger.reconcile(
            reservation["reservationId"],
            consumed_cost=0,
            provider_state="failed",
            capture_complete=True,
        )
        reservation = ledger.release(reservation["reservationId"], reason="provider_failure_refunded")
    elif task.state == "completed_capture_failed":
        reservation = ledger.reconcile(
            reservation["reservationId"],
            consumed_cost=task.consumed_cost,
            provider_state="completed",
            capture_complete=False,
        )
    elif task.state == "expired_uncaptured":
        reservation = ledger.reconcile(
            reservation["reservationId"],
            consumed_cost=task.consumed_cost,
            provider_state="expired_uncaptured",
            capture_complete=False,
        )
    else:
        reservation = ledger.mark_unresolved(
            reservation["reservationId"], reason=f"provider_nonterminal:{task.state}"
        )
    return MockOperationResult(reservation=reservation, task=task)
