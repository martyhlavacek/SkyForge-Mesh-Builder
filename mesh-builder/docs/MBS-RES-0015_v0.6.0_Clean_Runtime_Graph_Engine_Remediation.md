# MBS-RES-0015 — v0.6.0 clean-runtime graph-engine remediation

## Trigger

The automated macOS live-Blender preflight created a genuinely clean Python 3.11 virtual environment from the reviewed candidate's `requirements.txt`. Candidate extraction and source binding passed, but deterministic mesh generation stopped before Blender with:

`ImportError: no graph engines available!`

The failing path was `generate_authority_mesh` → `reloaded_glb.split` → `trimesh.graph.connected_components`.

## Root cause

`trimesh==4.11.1` treats graph backends as optional. The candidate called `Trimesh.split()` in two release-critical paths but declared neither NetworkX nor SciPy. Claude's review environment already contained a graph backend, so the undeclared runtime dependency was masked. The clean venv correctly exposed the packaging defect.

## Resolution

- Pin `networkx==3.6.1` in `requirements.txt`.
- Add NetworkX to the exact dependency contract enforced by `scripts/seal_release.py`.
- Add a runtime-contract test that creates a Trimesh object and executes `split()` using the clean pinned environment.
- Correct the live-preflight profile lookup to the registered `enemy_gunship` identifier.
- Enforce Claude's 0.94 Blender silhouette-IoU threshold in the source preflight.
- Bind each live fixture to Claude's independently reproduced deterministic mesh SHA-256.
- Normalize source-ZIP modes to 0644 for ordinary files and 0755 for `.command` launchers.
- Add direct regression guards for reloaded-target-frame geometry metrics and asymmetric non-mirrored fields.
- Report a stronger binned-function lower-field residual alongside the scalar anti-rescaling gate.

## Scope

This is a no-charge runtime, verification and release-integrity remediation. No geometry formula, authority identity rule, provider path, cost control, Keychain behavior, Blender coordinate contract, thruster, animation or fallback geometry behavior is expanded.

## User-testing posture

User testing remains withheld until Claude reviews the new exact candidate and a live Blender preflight succeeds from a clean environment.
