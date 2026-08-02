from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.authority_validation import (
    AuthoritySuitabilityError,
    analyze_authority_suitability,
    require_authority_suitability,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_all_cleared_authority_fixtures_pass_suitability_gate():
    fixtures = [
        "approved_gunship_authority.png",
        "v060_field_gunship_authority.png",
        "interceptor_openai_authority_regression.png",
        "user_test_gunship_authority.png",
    ]
    for filename in fixtures:
        report = require_authority_suitability(
            PACKAGE_ROOT / "samples" / filename,
            source_kind="cleared_fixture",
        )
        assert report["passed"] is True
        assert report["checks"]["bilateralPlanform"] is True
        assert report["checks"]["noseUpPlanformOrientation"] is True
        assert report["validatorVersion"] == "0.7.1"


def test_exact_mbs155_three_quarter_beauty_is_rejected():
    path = PACKAGE_ROOT / "samples" / "rejected_three_quarter_beauty_mbs155.png"
    report = analyze_authority_suitability(path, source_kind="fixture")

    assert report["passed"] is False
    failure_codes = {item["code"] for item in report["failures"]}
    assert "perspective_or_asymmetric_planform" in failure_codes
    assert "unstable_centerline" in failure_codes
    assert "not_nose_up" in failure_codes
    assert report["metrics"]["bilateralSilhouetteIoU"] < 0.5


def test_ninety_degree_rotated_authority_is_rejected_as_not_nose_up(tmp_path: Path):
    source = PACKAGE_ROOT / "samples" / "approved_gunship_authority.png"
    rotated = tmp_path / "rotated.png"
    with Image.open(source) as image:
        image.rotate(90, expand=False).save(rotated)

    report = analyze_authority_suitability(rotated, source_kind="fixture")
    assert report["passed"] is False
    assert report["checks"]["noseUpPlanformOrientation"] is False
    assert any(item["code"] == "not_nose_up" for item in report["failures"])


def test_require_raises_with_machine_readable_report_for_invalid_authority():
    path = PACKAGE_ROOT / "samples" / "rejected_three_quarter_beauty_mbs155.png"
    try:
        require_authority_suitability(path, source_kind="fixture")
    except AuthoritySuitabilityError as exc:
        assert exc.report["passed"] is False
        assert exc.report["schemaVersion"] == "skyforge.authority-suitability.v1"
    else:  # pragma: no cover - explicit fail message is clearer than pytest.raises here
        raise AssertionError("Three-quarter beauty unexpectedly passed the authority gate")


def test_report_is_deterministic_for_same_authority():
    path = PACKAGE_ROOT / "samples" / "approved_gunship_authority.png"
    first = analyze_authority_suitability(path, source_kind="fixture")
    second = analyze_authority_suitability(path, source_kind="fixture")
    assert first == second
