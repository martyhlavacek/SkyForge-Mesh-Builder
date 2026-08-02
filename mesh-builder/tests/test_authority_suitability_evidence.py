from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from PIL import Image

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_prior_field_defect_artifact_binds_decoded_pixels_across_png_reencoding(
    tmp_path: Path, monkeypatch,
):
    from scripts import run_authority_suitability_evidence as evidence

    rejected_fixture = PACKAGE_ROOT / "samples/rejected_three_quarter_beauty_mbs155.png"
    original_bytes = rejected_fixture.read_bytes()
    with Image.open(io.BytesIO(original_bytes)) as image:
        encoded = io.BytesIO()
        image.save(encoded, format="PNG", compress_level=0)
    embedded_bytes = encoded.getvalue()
    embedded_sha = hashlib.sha256(embedded_bytes).hexdigest()
    assert embedded_sha != hashlib.sha256(original_bytes).hexdigest()

    package = tmp_path / "v070_field_defect.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("source/01_primary_authoritative.png", embedded_bytes)
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "authority": {
                        "sha256": embedded_sha,
                        "role": "approved_top_down_authority",
                    }
                }
            ),
        )
        archive.writestr("job.json", json.dumps({"status": "rendered"}))
        archive.writestr(
            "output/asset.json",
            json.dumps({"measurements": {"silhouetteIoU": {"value": 0.972942}}}),
        )

    monkeypatch.setattr(evidence, "V070_DEFECT_REVIEW_PACKAGE_SHA256", evidence.sha256(package))
    monkeypatch.setattr(evidence, "V070_EMBEDDED_AUTHORITY_SHA256", embedded_sha)
    report = evidence._inspect_v070_defect_artifact(package, rejected_fixture)

    assert report["rejectedFixtureSha256"] == evidence.REJECTED_FIXTURE_SHA256
    assert report["embeddedAuthoritySha256"] == embedded_sha
    assert report["embeddedAuthorityPixelsMatchRejectedFixture"] is True
    assert report["demonstratesDownstreamGatesCouldNotEstablishCameraSuitability"] is True
    assert report["passed"] is True
