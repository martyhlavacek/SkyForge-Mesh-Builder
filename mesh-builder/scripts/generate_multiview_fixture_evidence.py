from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from app.authority_mesh import generate_authority_mesh  # noqa: E402
from app.geometry_v2.evidence import render_components  # noqa: E402
from app.reconstruction_v1.bundle import (  # noqa: E402
    approve_bundle,
    build_bundle,
    render_contact_sheet,
)
from app.reconstruction_v1.evidence import (  # noqa: E402
    save_silhouettes,
    validate_glb,
    write_manifest,
)
from app.reconstruction_v1.orientation import rasterize, resolve_orientation  # noqa: E402
from app.reconstruction_v1.provider import MeshyMultiImageProvider  # noqa: E402
from app.reconstruction_v1.state import TaskLog  # noqa: E402


class NoNetworkTransport:
    def request(self, method, url, **kwargs):
        raise RuntimeError("Fixture evidence forbids network transport")


def fixture_mesh() -> trimesh.Trimesh:
    hull = trimesh.creation.box((2.0, 1.1, 0.35))
    nose = trimesh.creation.cone(radius=0.32, height=0.9, sections=11)
    nose.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (1, 0, 0)))
    nose.apply_translation((0.19, 0.92, 0.08))
    canopy = trimesh.creation.icosphere(subdivisions=2, radius=0.23)
    canopy.apply_scale((1.3, 0.8, 0.7))
    canopy.apply_translation((-0.28, 0.23, 0.32))
    return trimesh.util.concatenate([hull, nose, canopy])


def save_mask(mask: np.ndarray, path: Path) -> None:
    Image.fromarray(np.where(mask, 255, 0).astype(np.uint8)).save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic no-spend provider-fixture evidence")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    authority = fixture_mesh()
    views = []
    masks = {}
    for role in ("top", "front", "right"):
        mask = rasterize(authority, role)
        masks[role] = mask
        path = output / f"authority_{role}.png"
        save_mask(mask, path)
        views.append((role, path))
    contact = output / "multiview_contact_sheet.png"
    bundle = build_bundle(output, asset_id="fixture-gunship-no-spend", profile_id="enemy_gunship", source_commit="FIXTURE_ONLY_NO_PROVIDER", created_at="2026-08-03T00:00:00Z", views=views)
    render_contact_sheet(output, bundle, contact)
    bundle["contactSheet"] = {"path": contact.name, "sha256": __import__("hashlib").sha256(contact.read_bytes()).hexdigest()}
    bundle["bundleDigest"] = __import__("app.reconstruction_v1.bundle", fromlist=["content_digest"]).content_digest(bundle)
    bundle = approve_bundle(output, bundle, approved_at="2026-08-03T00:00:01Z", workflow_id="deterministic-fixture")
    (output / "MultiviewAuthorityBundleV1.json").write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")

    provider = MeshyMultiImageProvider(NoNetworkTransport(), environ={"SKYFORGE_PROVIDER_NETWORK_DISABLED": "1"})
    request = provider.prepare_request(output, bundle)
    (output / "redacted_request_preview.json").write_text(json.dumps(provider.redact_for_evidence(request), indent=2, sort_keys=True) + "\n")
    (output / "cost_estimate.json").write_text(json.dumps(provider.estimate_cost(), indent=2, sort_keys=True) + "\n")
    authorization = {
        "fixture": True,
        "authorized": False,
        "reason": "No paid operation is authorized for implementation, CI, or review",
        "paidOperationPerformed": False,
        "maximumCredits": 0,
        "bundleDigest": bundle["bundleDigest"],
    }
    (output / "submission_authorization_fixture.json").write_text(
        json.dumps(authorization, indent=2, sort_keys=True) + "\n"
    )
    response = {"fixture": True, "provider": "meshy_multi_image", "status": "SUCCEEDED", "result": "fixture-task-no-network", "paidOperationPerformed": False, "model_urls": {"glb": "fixture://raw_provider_fixture.glb"}}
    (output / "raw_provider_response_fixture.json").write_text(json.dumps(response, indent=2, sort_keys=True) + "\n")
    log = TaskLog(output / "provider_task_state_fixture.jsonl")
    for index, state in enumerate(("PREPARED", "BUNDLE_APPROVED", "COST_APPROVED", "SUBMITTING", "SUBMITTED", "POLLING", "SUCCEEDED", "DOWNLOADED", "VALIDATED")):
        log.append(state, timestamp=f"2026-08-03T00:00:{index:02d}Z", details={"fixture": True, "paidOperationPerformed": False})

    rotated = authority.copy()
    rotated.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (0, 0, 1)))
    raw_path = output / "raw_provider_fixture.glb"
    raw_path.write_bytes(trimesh.exchange.gltf.export_glb(trimesh.Scene(rotated)))
    raw_before = raw_path.read_bytes()
    canonical, orientation = resolve_orientation(rotated, masks)
    canonical_path = output / "canonical_review_fixture.glb"
    canonical_path.write_bytes(trimesh.exchange.gltf.export_glb(trimesh.Scene(canonical)))
    if raw_path.read_bytes() != raw_before:
        raise RuntimeError("Raw provider fixture was mutated")
    save_silhouettes(canonical, output)
    render_components({"canonical_fixture": canonical}, output / "canonical_oblique.png", "bank_left")
    legacy = generate_authority_mesh(output / "authority_top.png", output / "unchanged_v0.7.1_fixture")
    comparison = Image.new("RGB", (384, 192), "#111820")
    with Image.open(legacy.preview_paths[0]) as legacy_top, Image.open(output / "canonical_top_silhouette.png") as canonical_top:
        comparison.paste(legacy_top.convert("RGB").resize((192, 192)), (0, 0))
        comparison.paste(canonical_top.convert("RGB").resize((192, 192)), (192, 0))
    comparison.save(output / "v0.7.1_canonical_comparison.png")
    overlay = Image.new("RGB", (384, 128), "#111820")
    draw = ImageDraw.Draw(overlay)
    for index, role in enumerate(("top", "front", "right")):
        authority_image = Image.fromarray(np.where(masks[role], 255, 0).astype(np.uint8)).convert("RGB")
        canonical_image = Image.fromarray(np.where(rasterize(canonical, role), 0, 255).astype(np.uint8)).convert("RGB")
        blended = Image.blend(authority_image, canonical_image, 0.5)
        overlay.paste(blended, (index * 128, 0))
        draw.text((index * 128 + 4, 4), role, fill="red")
    overlay.save(output / "silhouette_overlays.png")
    (output / "orientation_report.json").write_text(json.dumps(orientation, indent=2, sort_keys=True) + "\n")
    validation = {"evidenceClass": "DETERMINISTIC_FIXTURE_NOT_LIVE_PROVIDER", "paidOperationPerformed": False, "raw": validate_glb(raw_path), "canonical": validate_glb(canonical_path), "rawBytesPreserved": True, "limitations": ["Fixture geometry is not a Meshy result", "Silhouette scores are not semantic-quality proof"]}
    (output / "structural_validation.json").write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n")
    write_manifest(output, output / "SHA256_MANIFEST.json")
    print(json.dumps({"passed": True, "paidOperationPerformed": False, "evidenceClass": validation["evidenceClass"]}, indent=2))


if __name__ == "__main__":
    main()
