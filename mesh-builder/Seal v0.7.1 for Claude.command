#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PARENT="$(dirname "$ROOT")"
PROBE_ROOT="${SKYFORGE_IMPORT_PROBE_ROOT:-$PARENT/SkyForge_Sprite_Foundry_Import_Probe_v0.1.1}"
if [ -n "${SKYFORGE_V071_HANDOFF_ROOT:-}" ]; then
  HANDOFF_ROOT="$SKYFORGE_V071_HANDOFF_ROOT"
elif [ -d "$PARENT/SkyForge_Mesh_Builder_v0.7.1_Implementation_Handoff" ]; then
  HANDOFF_ROOT="$PARENT/SkyForge_Mesh_Builder_v0.7.1_Implementation_Handoff"
else
  HANDOFF_ROOT="$(dirname "$PARENT")/SkyForge_Mesh_Builder_v0.7.1_Implementation_Handoff"
fi
BASELINE_ZIP="$HANDOFF_ROOT/BASELINE/SkyForge_Mesh_Builder_Sidecar_v0.7.0_SOURCE.zip"
REVIEWED_BASELINE_CANDIDATE="$HANDOFF_ROOT/BASELINE/SkyForge_Mesh_Builder_v0.7.0_EXACT_CANDIDATE_FOR_CLAUDE.zip"
MBS155_DEFECT_PACKAGE="$HANDOFF_ROOT/FIELD_EVIDENCE/enemy.military.gunship.01-e759b3b9_review_package.zip"
WORK="$PARENT/SkyForge_v0.7.1_EXACT_CANDIDATE_WORK"
OUTPUT="$PARENT/SkyForge_v0.7.1_EXACT_CANDIDATE_OUTPUT"
PRODUCER_RELEASES="$WORK/producer_releases"
PROBE_RELEASES="$WORK/probe_releases"
EVIDENCE="$WORK/EVIDENCE"

finish() {
  status=$?
  if [ "$status" -ne 0 ]; then
    printf '\nCandidate seal stopped safely. No exact review candidate was created.\n'
  fi
  printf '\nPress Return to close...'
  read -r _
  trap - EXIT
  exit "$status"
}
trap finish EXIT

for path in "$PROBE_ROOT" "$HANDOFF_ROOT" "$BASELINE_ZIP" "$REVIEWED_BASELINE_CANDIDATE" "$MBS155_DEFECT_PACKAGE"; do
  if [ ! -e "$path" ]; then
    echo "Required path is missing: $path"
    echo "Set SKYFORGE_IMPORT_PROBE_ROOT or SKYFORGE_V071_HANDOFF_ROOT when using a different layout."
    exit 1
  fi
done
if [ -e "$WORK" ] || [ -e "$OUTPUT" ]; then
  echo "A prior seal work/output directory exists. Move or delete it before retrying:"
  echo "$WORK"
  echo "$OUTPUT"
  exit 1
fi
mkdir -p "$WORK" "$OUTPUT" "$PRODUCER_RELEASES" "$PROBE_RELEASES" "$EVIDENCE"

printf '[1/8] Creating exact clean producer and Import Probe environments...\n'
PRODUCER_VENV="$WORK/producer_clean_env"
PROBE_VENV="$WORK/import_probe_clean_env"
python3 -m venv "$PRODUCER_VENV"
"$PRODUCER_VENV/bin/python" -m pip install --upgrade pip
"$PRODUCER_VENV/bin/python" -m pip install -r "$ROOT/requirements.txt"
python3 -m venv "$PROBE_VENV"
"$PROBE_VENV/bin/python" -m pip install --upgrade pip
"$PROBE_VENV/bin/python" -m pip install -r "$PROBE_ROOT/requirements.txt"

cd "$ROOT"
printf '[2/8] Running producer Ruff, complete zero-skip tests, binding checks and deterministic release seal...\n'
env -u PYTHONPATH PYTHONNOUSERSITE=1 "$PRODUCER_VENV/bin/python" scripts/seal_release.py --package-root "$ROOT" --output-dir "$PRODUCER_RELEASES"
printf '[3/8] Running independent Import Probe Ruff, complete tests, binding checks and release seal...\n'
(
  cd "$PROBE_ROOT"
  env -u PYTHONPATH PYTHONNOUSERSITE=1 "$PROBE_VENV/bin/python" scripts/seal_probe_release.py --probe-root "$PROBE_ROOT" --output-dir "$PROBE_RELEASES"
)

printf '[4/8] Proving three-fixture legacy-direct versus local-adapter semantic equivalence...\n'
mkdir -p \
  "$EVIDENCE/local_adapter" \
  "$EVIDENCE/authority_suitability" \
  "$EVIDENCE/migration" \
  "$EVIDENCE/governance" \
  "$EVIDENCE/mock_provider" \
  "$EVIDENCE/meshy_test_mode" \
  "$EVIDENCE/blender"
"$PRODUCER_VENV/bin/python" scripts/run_local_adapter_evidence.py "$EVIDENCE/local_adapter"

printf '[5/8] Capturing MBS-155, migration, governance and mock-provider recovery evidence...\n'
env -u PYTHONPATH PYTHONNOUSERSITE=1 "$PRODUCER_VENV/bin/python" scripts/run_authority_suitability_evidence.py \
  "$EVIDENCE/authority_suitability/authority_suitability_evidence.json" \
  --v070-defect-review-package "$MBS155_DEFECT_PACKAGE"
cp "$ROOT/samples/rejected_three_quarter_beauty_mbs155.png" \
  "$EVIDENCE/authority_suitability/rejected_three_quarter_beauty_mbs155.png"
cp "$MBS155_DEFECT_PACKAGE" \
  "$EVIDENCE/authority_suitability/v0.7.0_mbs155_field_defect_review_package.zip"
"$PRODUCER_VENV/bin/python" scripts/run_migration_evidence.py "$EVIDENCE/migration"
"$PRODUCER_VENV/bin/python" scripts/run_governance_identity.py "$EVIDENCE/governance/governance_byte_identity.json"
"$PRODUCER_VENV/bin/python" scripts/run_mock_provider_fault_matrix.py "$EVIDENCE/mock_provider"

printf '[6/8] Running isolated zero-credit Meshy public test-mode lifecycle diagnostic...\n'
"$PRODUCER_VENV/bin/python" scripts/run_meshy_test_mode_diagnostic.py \
  samples/approved_gunship_authority.png "$EVIDENCE/meshy_test_mode" --allow-network

printf '[7/8] Running all three mandatory live Blender, VMP and independent Import Probe regressions...\n'
LIVE_ZIP="$WORK/SkyForge_v0.7.1_LIVE_BLENDER_PREFLIGHT.zip"
env -u PYTHONPATH PYTHONNOUSERSITE=1 "$PRODUCER_VENV/bin/python" scripts/run_live_blender_preflight.py \
  --output "$LIVE_ZIP" --probe-root "$PROBE_ROOT" --probe-python "$PROBE_VENV/bin/python"
"$PRODUCER_VENV/bin/python" - "$LIVE_ZIP" "$EVIDENCE/blender" <<'PY'
from pathlib import Path
import sys, zipfile
source, destination = Path(sys.argv[1]), Path(sys.argv[2])
with zipfile.ZipFile(source) as archive:
    archive.extractall(destination)
PY
cp "$LIVE_ZIP" "$EVIDENCE/blender/"
cp "$LIVE_ZIP.sha256" "$EVIDENCE/blender/"

printf '[8/8] Verifying all evidence and assembling the exact Claude review candidate...\n'
PRODUCER_SET="$(find "$PRODUCER_RELEASES" -maxdepth 1 -type d -name '*_RELEASE_SET' -print -quit)"
PROBE_SET="$(find "$PROBE_RELEASES" -maxdepth 1 -type d -name '*_RELEASE_SET' -print -quit)"
"$PRODUCER_VENV/bin/python" scripts/assemble_claude_candidate.py \
  --baseline-zip "$BASELINE_ZIP" \
  --reviewed-baseline-candidate "$REVIEWED_BASELINE_CANDIDATE" \
  --producer-release-set "$PRODUCER_SET" \
  --probe-release-set "$PROBE_SET" \
  --evidence-root "$EVIDENCE" \
  --handoff-root "$HANDOFF_ROOT" \
  --output-dir "$OUTPUT"

printf '\nEXACT CANDIDATE CREATED. USER TESTING REMAINS WITHHELD PENDING CLAUDE REVIEW:\n%s\n' "$OUTPUT"
open "$OUTPUT" || true
