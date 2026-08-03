from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from app.providers.mock_operation import SimulatedProcessCrash, execute_mock_operation  # noqa: E402
from app.providers.mock_provider import MockProvider  # noqa: E402
from common.provider_credit_ledger import CreditCaps, ProviderCreditLedger  # noqa: E402


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def build_correlation(provider: MockProvider, request_digest: str):
    return provider.correlation(
        request_digest=request_digest,
        authority_sha256=digest("authority"),
        options_digest=digest("options"),
        account_identity_digest=digest("mock-account"),
        dispatch_window_start="2026-08-01T12:00:00+00:00",
        dispatch_window_end="2026-08-01T12:05:00+00:00",
        expected_cost=20,
    )


def run(output_dir: Path) -> Path:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    cases: list[dict] = []
    definitions = [
        ("success", None),
        ("failure_refund", None),
        ("delayed", None),
        ("timeout", None),
        ("expiry", None),
        ("capture_failure", None),
        ("crash_after_intent", "after_intent"),
        ("crash_after_reserve", "after_reserve"),
        ("orphan_unique", "after_dispatch_before_task_id"),
        ("orphan_ambiguous", "after_dispatch_before_task_id"),
    ]
    for ordinal, (name, crash_point) in enumerate(definitions, start=1):
        case_dir = output_dir / f"{ordinal:02d}_{name}"
        provider = MockProvider(case_dir / "mock_provider_tasks.json")
        book = ProviderCreditLedger(
            case_dir / "provider_credit_ledger.json",
            session_id=f"fault-matrix-{ordinal}",
            caps=CreditCaps.from_values(per_request=20, per_asset=40, per_session=60),
        )
        scenario = "ambiguous_recovery" if name == "orphan_ambiguous" else "success" if crash_point else name
        request_digest = digest(name)
        crashed = False
        try:
            result = execute_mock_operation(
                ledger=book,
                provider=provider,
                request_digest=request_digest,
                asset_id=f"asset-{ordinal}",
                expected_cost=Decimal("20"),
                correlation=build_correlation(provider, request_digest),
                scenario=scenario,
                crash_point=crash_point,
            )
            final = result.reservation
        except SimulatedProcessCrash:
            crashed = True
            recovered = book.recover(provider)
            final = recovered[-1]
        snapshot = book.snapshot()
        cases.append(
            {
                "case": name,
                "simulatedCrash": crashed,
                "finalReservationState": final["state"],
                "providerDispatchCount": provider.dispatch_count(),
                "chargedCredits": book.totals(asset_id=f"asset-{ordinal}")["assetCredits"],
                "eventTypes": [event["eventType"] for event in snapshot["events"]],
            }
        )
    report = {
        "schemaVersion": "skyforge.mock-provider-fault-matrix.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "evidenceClass": "mock_provider",
        "monetaryCharge": {"amount": 0, "unit": "usd"},
        "productionCredentialsUsed": False,
        "paidDispatchEnabled": False,
        "mbs136RealProviderStatus": "open",
        "cases": cases,
    }
    target = output_dir / "mock_provider_fault_matrix_report.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(run(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
