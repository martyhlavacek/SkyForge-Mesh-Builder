#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from app.authority_mesh import generate_authority_mesh  # noqa: E402
from app.providers import ProviderRequest, resolve_provider  # noqa: E402
from common.mesh_equivalence import compare_mesh_semantics  # noqa: E402
from common.source_binding import PRODUCER_SCOPE, verify_binding  # noqa: E402

FIXTURES = (
    ("approved_gunship", "approved_gunship_authority.png", "2e2f5f68dfa91ac2611113c35b1b08d90dfdecc2d593f897d40963dd46a2705a"),
    ("field_gunship", "v060_field_gunship_authority.png", "f4761acd9a1f7c78c4bedc3b9616b162e4a57c2d47a756eb29ad0446952d0e91"),
    ("interceptor", "interceptor_openai_authority_regression.png", "97617de238dc451d4ca374e1c0b05461ab71e18cfd82643e0dd2358bf1a8f118"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(output_dir: Path) -> Path:
    binding = verify_binding(PACKAGE_ROOT, PRODUCER_SCOPE)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    provider = resolve_provider("local_deterministic")
    results: list[dict[str, object]] = []
    for label, authority_name, expected_mesh in FIXTURES:
        fixture_dir = output_dir / label
        baseline_dir = fixture_dir / "legacy_direct"
        adapter_dir = fixture_dir / "local_adapter"
        baseline_dir.mkdir(parents=True)
        adapter_dir.mkdir(parents=True)
        authority = PACKAGE_ROOT / "samples" / authority_name
        baseline = generate_authority_mesh(authority, baseline_dir)
        capture = provider.execute(
            ProviderRequest(
                request_id=f"v071-local-adapter-{label}",
                operation="authority_to_mesh",
                asset_id=f"preflight.{label}",
                asset_role="air_moving",
                authority_path=authority,
                output_dir=adapter_dir,
            )
        )
        baseline_sha = sha256_file(baseline.mesh_path)
        actual = sha256_file(capture.mesh_path)
        semantic = compare_mesh_semantics(
            baseline.mesh_path,
            capture.mesh_path,
            baseline.report_path,
            capture.report_path,
        )
        events = [
            json.loads(line)
            for line in (adapter_dir / "provider_events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        result = {
            "fixture": label,
            "authorityFile": authority_name,
            "authoritySha256": sha256_file(authority),
            "reviewedCandidateMeshSha256": expected_mesh,
            "legacyDirectMeshSha256": baseline_sha,
            "adapterMeshSha256": actual,
            "adapterTransportHashMatchesLegacy": actual == baseline_sha,
            "reviewedCandidateTransportHashMatch": actual == expected_mesh,
            "semanticComparison": semantic,
            "providerId": capture.task.provider_id,
            "providerModel": capture.task.provider_model,
            "providerCostZero": all(
                event.get("expectedCost") == "0" and event.get("consumedCost") == "0"
                for event in events
            ),
            "providerEvents": events,
            "generationGatesPassed": bool(capture.evidence.get("gateResults", {}).get("passed")),
        }
        results.append(result)
    report = {
        "schemaVersion": "skyforge.local-adapter-three-fixture-evidence.v2",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceBinding": binding,
        "networkUsed": False,
        "paidOperationPerformed": False,
        "fixtures": results,
        "passed": all(
            bool(item["adapterTransportHashMatchesLegacy"])
            and bool(item["semanticComparison"]["passed"])
            and bool(item["providerCostZero"])
            and bool(item["generationGatesPassed"])
            for item in results
        ),
    }
    target = output_dir / "local_adapter_three_fixture.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not report["passed"]:
        raise RuntimeError("Local adapter evidence did not reproduce every cleared fixture")
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(run(args.output_dir.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
