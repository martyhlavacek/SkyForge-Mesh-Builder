from __future__ import annotations

import json
from pathlib import Path

from common.mesh_equivalence import compare_mesh_semantics

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MESH = PACKAGE_ROOT / "docs/SELF_TEST_EVIDENCE_v0.6.0/field_gunship/authority_generated_mesh.glb"
REPORT = PACKAGE_ROOT / "docs/SELF_TEST_EVIDENCE_v0.6.0/field_gunship/authority_mesh_generation_report.json"


def test_identical_mesh_and_report_satisfy_frozen_wp2_semantic_contract():
    result = compare_mesh_semantics(MESH, MESH, REPORT, REPORT)
    assert result["passed"] is True
    assert all(result["checks"].values())
    assert result["metrics"]["yMaxAbsoluteDelta"] == 0.0
    assert result["metrics"]["yRmsDelta"] == 0.0


def test_gate_evidence_difference_fails_semantic_contract(tmp_path: Path):
    changed = json.loads(REPORT.read_text(encoding="utf-8"))
    changed["gateResults"]["checks"]["silhouetteIoU"] = False
    changed["gateResults"]["passed"] = False
    changed_report = tmp_path / "changed-report.json"
    changed_report.write_text(json.dumps(changed), encoding="utf-8")
    result = compare_mesh_semantics(MESH, MESH, REPORT, changed_report)
    assert result["passed"] is False
    assert result["checks"]["gateResultsExact"] is False
    assert result["checks"]["gateResultsPassed"] is False
