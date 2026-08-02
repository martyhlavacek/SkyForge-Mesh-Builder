# MBS-RES-0002 — Resolution of MBS-CR-0002

**Artifact:** SkyForge Mesh Builder Sidecar v0.2.1  
**Review:** `MBS-CR-0002_v0_2_0_Verification_Review.md`  
**Date:** 30 July 2026  
**Disposition:** Source corrections complete; Experiment 00 remains pending a local Blender 4.2+ calibration run.

## Decision

The review's **HOLD on Experiment 00** was accepted. No provider result should be scored using v0.2.0. Version 0.2.1 changes the calibration instrument before any provider credits are spent.

The three P0 findings are closed in source and regression-covered. Blender is unavailable in the build sandbox, so the hold is lifted only for running the calibration—not for declaring that calibration passed.

## P0 resolutions

| ID | Resolution | Verification |
|---|---|---|
| MBS-26 | Replaced per-craft camera fitting with one `canonicalOrthoScale`, derived from the largest governed profile. Per-craft projected fit is now a clipping validator only. | Pure-Python regression proves bomber > gunship > fighter > interceptor > drone in projected pixels under one frame. Mac Blender five-profile calibration remains required. |
| MBS-27 | Added `RecordingSettings`; `consumedSettings` now comes from settings actually accessed. Export pose, scene object names/types, review-rig presence and root matrix are read from the live Blender scene and asserted before export. | AST/source tests reject the former hardcoded evidence literals. Runtime evidence still requires Blender. |
| MBS-28 | Added descendant-aware effect visibility. The effect root and every thruster-preview descendant are hidden during the silhouette pass and their names are written to the run report. | Source regression checks the descendant operation and evidence field. The resulting alpha pass requires Blender validation. |

## P1 resolutions

| ID | Resolution | Status |
|---|---|---|
| MBS-29 | Split the contract into Blender-render outputs, post-processing outputs and final complete verification. Missing masters fail before Pillow opens them. | Closed and unit-tested. |
| MBS-30 | Unsupported imported nodes are removed only after descendants are reparented while preserving their world transforms. | Closed in source; hierarchical GLB fixture remains a useful local Blender check. |
| MBS-31 | IoU now records translation/uniform-scale invariance, shape/aspect/rotation sensitivity, fit canvas, margin, resampling method, theoretical ceiling and render-resolution round-trip ceiling. | Closed and unit-tested. |
| MBS-32 | Contact sheets crop the authority to its measured silhouette and scale it to the neutral render's silhouette span before comparison. | Closed and unit-tested through post-processing. |
| MBS-33 / prior MBS-17 | EEVEE render samples, Standard view transform, neutral look, exposure, gamma and transparent film are pinned and copied from the live scene into `run_report.json`. | Source closed; exact Blender 4.2+ runtime behaviour remains part of Experiment 00. |
| MBS-36 | Rigid normalization is baked into mesh vertex data before `.blend`/GLB export; the root matrix is reset to identity. Armature-backed inputs are rejected. All mesh world matrices are captured before any parent is changed. | Closed in source; exported GLB must be inspected locally. |

## P2 resolutions

| ID | Resolution |
|---|---|
| MBS-34 | Replaced the opaque-image pixel loop with Pillow image operations; named the threshold and emitted `authority_mask.png`. |
| MBS-35 | Renamed the UI and schema field from `frameSize` to `masterResolution`; 96/64 outputs are fixed protocol sizes. |
| MBS-37 | Renamed anchor evidence as a bounding-box heuristic and declared Blender-world units; pivot/collision each declare normalized-image units and measurement sources. |
| MBS-38 | Tests resolve paths from the package root; traversal tests require exactly 404 for encoded and bare vectors; source tests now target behaviour/evidence structure rather than the former literals. |
| MBS-39 | Added pinned Ruff dependency, `pyproject.toml` and `scripts/lint.command`; local `run_tests.command` runs lint before pytest. |
| MBS-40 | Consolidated render-state assignments in `setup_scene`. |
| MBS-41 | Added a bounded one-job Blender semaphore, active-process registry and shutdown termination handler. |
| MBS-42 | Silhouette overlay now assigns separate colours to authority-only, render-only and intersection pixels. |
| MBS-43 | Guarded job-status read-modify-write operations with a re-entrant lock. |
| MBS-44 | Pivot now records `source`, `units` and `value`, matching collision provenance. |

## Additional corrective finding during implementation

While closing MBS-36, a second hierarchy edge case was found: baking a parent mesh before capturing a child mesh's world matrix could change the child's apparent transform. v0.2.1 captures every mesh world matrix before any mesh is reparented or reset. A source regression test protects this ordering.

## Experiment status

- **Experiment 00:** Ready to run, not yet passed.
- **Experiment 01:** Still blocked until Experiment 00 passes across all five profiles.
- **Provider verdicts:** No verdict may be derived from v0.2.0 output.

## Required local acceptance evidence

A valid v0.2.1 calibration package must show:

1. all five profiles rendered with the same `canonicalOrthoScale`;
2. projected pixel-size order bomber > gunship > fighter > interceptor > drone;
3. no thruster pixels in `silhouette_top_master.png` or `authority_mask.png`;
4. zero bank-root rotation at export;
5. no camera, light, review root or thruster-preview object in the normalized export;
6. identity root transform with normalization baked into rigid mesh data;
7. all declared settings observed and all output stages verified.
