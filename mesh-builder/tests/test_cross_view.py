from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.reconstruction_v1 import bundle as bundle_module
from app.reconstruction_v1.bundle import (
    BundleError,
    approve_bundle,
    build_bundle,
    content_digest,
    sha256_file,
    validate_bundle,
)
from app.reconstruction_v1.cross_view import (
    CAMERA_DECLARATION_PASS,
    CROSS_VIEW_ASPECT_TOLERANCE_PPM,
    CrossViewError,
    aspect_mismatch_ppm,
    classify_measurement,
    measure_cross_view,
    require_cross_view_consistency,
)
from app.reconstruction_v1.pilot import PilotError, PilotRuntime

PACKAGE_ROOT = Path(__file__).parents[1]
ROLES = ("top", "front", "right")
GOOD_DIMS = {"top": (600, 800), "front": (600, 400), "right": (800, 400)}
MBS195_DIMS = {"top": (549, 760), "front": (1217, 949), "right": (1183, 291)}


def image_payload(bbox_size: tuple[int, int], *, offset=(0, 0), canvas=(1400, 1400)) -> bytes:
    image = Image.new("RGBA", canvas, (0, 0, 0, 0))
    width, height = bbox_size
    left = (canvas[0] - width) // 2 + offset[0]
    top = (canvas[1] - height) // 2 + offset[1]
    ImageDraw.Draw(image).rectangle((left, top, left + width - 1, top + height - 1), fill=(80, 120, 160, 255))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def uniform_payload(value: int, *, mode: str = "RGB") -> bytes:
    stream = io.BytesIO()
    color = value if mode == "L" else (value, value, value, value) if mode == "RGBA" else (value, value, value)
    Image.new(mode, (64, 64), color).save(stream, format="PNG")
    return stream.getvalue()


def write_set(root: Path, dimensions: dict[str, tuple[int, int]], *, offset_role=None) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    paths = {}
    for role in ROLES:
        path = root / f"{role}.png"
        path.write_bytes(image_payload(dimensions[role], offset=(100, 0) if role == offset_role else (0, 0)))
        paths[role] = path
    return paths


def built_bundle(root: Path) -> dict:
    paths = write_set(root, GOOD_DIMS)
    bundle = build_bundle(
        root,
        asset_id="synthetic.ship",
        profile_id="enemy_gunship",
        source_commit="a" * 40,
        created_at="2026-08-10T00:00:00Z",
        views=list(paths.items()),
    )
    return approve_bundle(root, bundle, approved_at="2026-08-10T00:01:00Z", workflow_id="test")


def runtime(root: Path) -> PilotRuntime:
    return PilotRuntime(PACKAGE_ROOT, root, object())


def uploads(dimensions: dict[str, tuple[int, int]], names=None):
    names = names or {role: f"gunship_{role}.png" for role in ROLES}
    return [
        (role, names[role], image_payload(dimensions[role]), "human_authority_candidate")
        for role in ROLES
    ]


def test_consistent_synthetic_set_passes_with_exact_integer_metrics(tmp_path: Path):
    record = require_cross_view_consistency(write_set(tmp_path, GOOD_DIMS))
    assert record["result"] == "PASS"
    assert record["measuredAspectMismatchPpm"] == 0
    assert record["minAspectMismatchPpm"] == record["maxAspectMismatchPpm"] == 0
    assert record["thresholdsUsed"] == [8, 16, 24, 40, 60, 80]


def test_mbs195_synthetic_dimensions_fail_by_large_margin(tmp_path: Path):
    paths = write_set(tmp_path, MBS195_DIMS)
    record = measure_cross_view(paths)
    assert 1_280_000 <= record["measuredAspectMismatchPpm"] <= 1_300_000
    assert record["result"] == "FAIL"
    with pytest.raises(CrossViewError, match="consistency failed"):
        require_cross_view_consistency(paths)


def test_inconsistent_import_fails_before_prepared_or_approved(tmp_path: Path):
    active = runtime(tmp_path)
    with pytest.raises(BundleError, match="consistency failed"):
        active.import_bundle(profile_id="enemy_gunship", asset_id="x", uploads=uploads(MBS195_DIMS))
    assert active.task_log.events() == []
    assert not active.bundle_path.exists()


def test_threshold_ensemble_and_record_are_deterministic(tmp_path: Path):
    paths = write_set(tmp_path, GOOD_DIMS)
    assert measure_cross_view(paths) == measure_cross_view(paths)


def test_empty_and_malformed_images_fail_closed(tmp_path: Path):
    paths = write_set(tmp_path, GOOD_DIMS)
    Image.new("RGBA", (1400, 1400), (0, 0, 0, 0)).save(paths["front"])
    with pytest.raises(CrossViewError, match="empty foreground"):
        measure_cross_view(paths)


@pytest.mark.parametrize("value,label", [(0, "black"), (127, "mid-grey"), (255, "white")])
def test_uniform_authority_images_fail_closed(tmp_path: Path, value: int, label: str):
    paths = {}
    for role in ROLES:
        path = tmp_path / f"{role}-{label}.png"
        path.write_bytes(uniform_payload(value))
        paths[role] = path
    with pytest.raises(CrossViewError, match="Uniform authority image"):
        measure_cross_view(paths)


def test_uniform_blank_images_cannot_build_bundle_or_camera_declaration(tmp_path: Path):
    paths = {}
    for role, mode in zip(ROLES, ("L", "RGB", "RGBA"), strict=True):
        path = tmp_path / f"{role}.png"
        path.write_bytes(uniform_payload(0, mode=mode))
        paths[role] = path
    with pytest.raises(BundleError, match="Uniform authority image"):
        build_bundle(
            tmp_path,
            asset_id="blank",
            profile_id="enemy_gunship",
            source_commit="x",
            created_at="x",
            views=list(paths.items()),
        )


def test_full_canvas_foreground_fails_plausibility_guard(tmp_path: Path):
    paths = write_set(tmp_path, GOOD_DIMS)
    full = Image.new("RGBA", (1400, 1400), (20, 30, 40, 255))
    full.putpixel((0, 0), (20, 30, 40, 254))
    full.save(paths["top"])
    with pytest.raises(CrossViewError, match="degenerate full-canvas"):
        measure_cross_view(paths)
    paths["front"].write_bytes(b"not-an-image")
    with pytest.raises(CrossViewError, match="Malformed front"):
        measure_cross_view(paths)


def test_excessive_center_offset_fails(tmp_path: Path):
    record = measure_cross_view(write_set(tmp_path, GOOD_DIMS, offset_role="front"))
    assert record["maximumCenterOffsetPpm"] > 50_000
    assert record["result"] == "FAIL"


def test_measurement_record_and_camera_declaration_are_digest_bound(tmp_path: Path):
    bundle = built_bundle(tmp_path)
    assert bundle["cameraDeclaration"] == CAMERA_DECLARATION_PASS
    original_digest = bundle["bundleDigest"]
    changed = json.loads(json.dumps(bundle))
    changed["crossViewConsistency"]["measuredAspectMismatchPpm"] += 1
    assert content_digest(changed) != original_digest
    with pytest.raises(BundleError, match="measurement record mismatch"):
        validate_bundle(tmp_path, changed, require_approved=False)
    changed = json.loads(json.dumps(bundle))
    changed["cameraDeclaration"] = "unmeasured_claim"
    with pytest.raises(BundleError, match="Camera declaration"):
        validate_bundle(tmp_path, changed, require_approved=False)


def test_silhouette_change_invalidates_approved_reload(tmp_path: Path):
    bundle = built_bundle(tmp_path)
    (tmp_path / "top.png").write_bytes(image_payload((620, 800)))
    with pytest.raises(BundleError, match="mutated"):
        validate_bundle(tmp_path, bundle)


def test_approved_reload_remeasures_instead_of_trusting_record(tmp_path: Path, monkeypatch):
    bundle = built_bundle(tmp_path)
    original = bundle_module.require_cross_view_consistency
    calls = []

    def measured(paths):
        calls.append(paths)
        record = original(paths)
        record["measuredAspectMismatchPpm"] += 1
        return record

    monkeypatch.setattr(bundle_module, "require_cross_view_consistency", measured)
    with pytest.raises(BundleError, match="measurement record mismatch"):
        validate_bundle(tmp_path, bundle)
    assert len(calls) == 1


def test_forged_pass_record_and_refreshed_digest_cannot_bypass_remeasurement(tmp_path: Path):
    bundle = built_bundle(tmp_path)
    bad_paths = write_set(tmp_path / "bad", MBS195_DIMS)
    for item in bundle["views"]:
        source = bad_paths[item["role"]]
        target = tmp_path / item["path"]
        target.write_bytes(source.read_bytes())
        with Image.open(target) as image:
            item["dimensions"] = [image.width, image.height]
            item["mode"] = image.mode
            item["hasAlpha"] = "A" in image.getbands()
        item["sha256"] = sha256_file(target)
    bundle["bundleDigest"] = content_digest(bundle)
    bundle["approval"]["bundleDigest"] = bundle["bundleDigest"]
    with pytest.raises(BundleError, match="consistency failed"):
        validate_bundle(tmp_path, bundle)


def test_duplicate_image_hash_guard_remains(tmp_path: Path):
    paths = write_set(tmp_path, GOOD_DIMS)
    paths["front"].write_bytes(paths["top"].read_bytes())
    with pytest.raises(BundleError, match="independently stored"):
        build_bundle(tmp_path, asset_id="x", profile_id="enemy_gunship", source_commit="x", created_at="x", views=list(paths.items()))


@pytest.mark.parametrize(
    "role,filename",
    [
        ("top", "01_front_canonical.png"),
        ("top", "FRONT-VIEW.png"),
        ("top", "render(front).png"),
        ("top", "authority+front.png"),
        ("top", "right,front.png"),
        ("top", "authorityFrontView.png"),
        ("top", "01front.png"),
        ("front", "gunship_right.png"),
        ("right", "top-view.png"),
    ],
)
def test_conflicting_exact_role_filename_is_refused(tmp_path: Path, role: str, filename: str):
    names = {item: f"gunship_{item}.png" for item in ROLES}
    names[role] = filename
    with pytest.raises(PilotError, match="Source filename conflicts.*rename"):
        runtime(tmp_path).import_bundle(profile_id="enemy_gunship", asset_id="x", uploads=uploads(GOOD_DIMS, names))


@pytest.mark.parametrize(
    "filename",
    ["gunship_top_authority.png", "gunship_authority.png", "frontier_concept.png", "neutral-render-01.png"],
)
def test_nonconflicting_and_substring_filename_tokens_are_accepted(tmp_path: Path, filename: str):
    names = {"top": filename, "front": "gunship_front.png", "right": "gunship_right.png"}
    assert runtime(tmp_path).import_bundle(profile_id="enemy_gunship", asset_id="x", uploads=uploads(GOOD_DIMS, names))["views"][0]["originalFilename"] == filename


def test_comparison_operator_boundaries_and_bypass_are_mutation_sensitive(tmp_path: Path, monkeypatch):
    assert classify_measurement(
        mismatch_ppm=CROSS_VIEW_ASPECT_TOLERANCE_PPM,
        min_mismatch_ppm=CROSS_VIEW_ASPECT_TOLERANCE_PPM,
        max_mismatch_ppm=CROSS_VIEW_ASPECT_TOLERANCE_PPM,
        maximum_dimension_spread_ppm=0,
        maximum_center_offset_ppm=0,
    ) == "PASS"
    assert classify_measurement(
        mismatch_ppm=CROSS_VIEW_ASPECT_TOLERANCE_PPM + 1,
        min_mismatch_ppm=CROSS_VIEW_ASPECT_TOLERANCE_PPM + 1,
        max_mismatch_ppm=CROSS_VIEW_ASPECT_TOLERANCE_PPM + 1,
        maximum_dimension_spread_ppm=0,
        maximum_center_offset_ppm=0,
    ) == "FAIL"
    paths = write_set(tmp_path, GOOD_DIMS)
    failed = measure_cross_view(paths)
    failed["result"] = "FAIL"
    monkeypatch.setattr(bundle_module, "require_cross_view_consistency", lambda _paths: failed)
    with pytest.raises(BundleError, match="did not produce a passing"):
        build_bundle(tmp_path, asset_id="x", profile_id="enemy_gunship", source_commit="x", created_at="x", views=list(paths.items()))


def test_published_exemplar_and_headline_sources_are_unambiguous(tmp_path: Path):
    record = measure_cross_view(write_set(tmp_path, MBS195_DIMS))
    samples = record["thresholdSamples"]
    mismatches = sorted(sample["aspectMismatchPpm"] for sample in samples)
    expected_median = (mismatches[2] + mismatches[3]) // 2
    assert record["headlineMetricSource"] == "integer_median_of_thresholdSamples.aspectMismatchPpm"
    assert record["measuredAspectMismatchPpm"] == expected_median
    threshold = record["fixedThresholdExemplarThreshold"]
    sample = next(item for item in samples if item["threshold"] == threshold)
    assert record["fixedThresholdExemplarBoundingBoxes"] == sample["boundingBoxes"]
    assert aspect_mismatch_ppm(record["fixedThresholdExemplarBoundingBoxes"]) == sample["aspectMismatchPpm"]
    assert "perViewBoundingBoxes" not in record and "representativeThreshold" not in record
