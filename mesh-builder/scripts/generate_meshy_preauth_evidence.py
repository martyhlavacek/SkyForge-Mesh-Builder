from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from app.reconstruction_v1.preflight import preflight_artifact_url  # noqa: E402
from app.reconstruction_v1.provider import (  # noqa: E402
    ARTIFACT_HOST_CONTRACT_VERSION,
    ArtifactHostPolicy,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic no-spend Meshy preauthorization evidence")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--validation-results", required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    staging = output.with_suffix("")
    staging.mkdir(parents=True, exist_ok=True)

    attestation = {
        "evidenceClass": "NO_SPEND_PREAUTHORIZATION_NOT_PROVIDER_OUTPUT",
        "noMeshyTaskCreated": True,
        "noApiKeyReadOrUsed": True,
        "noCreditsConsumed": True,
        "noProviderArtifactDownloaded": True,
        "fixtureResultsAreNotMeshyOutputs": True,
        "humanApprovedAuthorityBundle": "MISSING",
        "remainingPrerequisite": "human-approved top/front/right authority bundle",
        "paidOperationPerformed": False,
        "providerTaskId": None,
    }
    write_json(staging / "NO_SPEND_ATTESTATION.json", attestation)

    fixture_policy = ArtifactHostPolicy(
        ARTIFACT_HOST_CONTRACT_VERSION,
        frozenset({"assets.meshy.ai"}),
        lambda _hostname: ("8.8.8.8", "2606:4700:4700::1111"),
    )
    write_json(
        staging / "OFFLINE_HOST_POLICY_PREFLIGHT.json",
        preflight_artifact_url(
            "https://assets.meshy.ai/<redacted-object>.glb?<redacted>", policy=fixture_policy
        ),
    )

    source_files = {
        "MESHY_CONTRACT_REVERIFICATION_2026-08-04.md": REPOSITORY_ROOT
        / "docs/contracts/MESHY_CONTRACT_REVERIFICATION_2026-08-04.md",
        "MESHY_ARTIFACT_HOST_POLICY.md": REPOSITORY_ROOT / "docs/contracts/MESHY_ARTIFACT_HOST_POLICY.md",
        "MESHY_SMOKE_INPUT_READINESS.md": REPOSITORY_ROOT
        / "docs/testing/V0.8.1_MESHY_SMOKE_INPUT_READINESS.md",
        "MESHY_SMOKE_DRY_RUN_PREVIEW.json": REPOSITORY_ROOT
        / "docs/testing/V0.8.1_MESHY_SMOKE_DRY_RUN_PREVIEW.json",
        "FOCUSED_CLAUDE_REVIEW_REQUEST.md": REPOSITORY_ROOT
        / "docs/reviews/MBS-CR-0027_PRE_SMOKE_SECURITY_REVIEW_REQUEST.md",
        "VALIDATION_RESULTS.json": args.validation_results.resolve(),
    }
    for name, source in source_files.items():
        (staging / name).write_bytes(source.read_bytes())

    records = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(staging.iterdir())
        if path.is_file()
    }
    write_json(staging / "SHA256_MANIFEST.json", {"files": records})

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(staging.iterdir()):
            info = zipfile.ZipInfo(path.name, date_time=(2026, 8, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n", encoding="ascii")
    review_request = output.with_name("MBS-CR-0027_PRE_SMOKE_SECURITY_REVIEW_REQUEST.md")
    template = source_files["FOCUSED_CLAUDE_REVIEW_REQUEST.md"].read_text(encoding="utf-8")
    review_request.write_text(
        template
        + f"\n## Exact review identity\n\n- Candidate commit: `{args.candidate}`\n"
        + f"- Evidence archive: `{output.name}`\n- Evidence SHA-256: `{digest}`\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"evidence": str(output), "sha256": digest, "reviewRequest": str(review_request), **attestation},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
