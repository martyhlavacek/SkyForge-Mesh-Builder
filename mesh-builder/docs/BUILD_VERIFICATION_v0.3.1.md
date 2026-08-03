# SkyForge Mesh Builder Sidecar v0.3.1 — Build Verification

## Executed in the build environment

- Python compilation: PASS
- Pytest available suite: `35 passed, 1 dependency-gated module skipped`
- Total installed test inventory: `41`
- Dual-authority generation self-test: PASS
- Exact failed-run authority emulated Blender-import IoU: `0.955508`
- Blender-import bounds reconstruction delta: `4.8e-08`
- Exact failed-run authority height-to-planform ratio: `0.167919993`
- Independent topology audit: zero boundary and non-manifold edges
- GLB deterministic regeneration: PASS
- Thruster cone creation absent from Blender source: PASS
- Thruster UI and form setting absent: PASS
- Authority axes fixed to +Y forward/+Z up: PASS

## Unavailable in this environment

- Flask/Werkzeug endpoint module: unavailable because the offline package index contains no installable wheels. Six endpoint tests therefore run only after normal setup.
- Ruff executable: unavailable for the same reason; it remains pinned and mandatory in `scripts/run_tests.command`.
- Live Blender: unavailable in the build container.

## Why this still catches the reported defect before user rendering

The failed v0.3.0 run empirically established Blender's import mapping for the generated GLB: raw extents `[4.056, 5.088, 0.854]` became Blender extents `[4.056, 0.854, 5.088]`. v0.3.1 applies that exact conversion in preflight and reconciles the reconstructed mesh with the original target coordinates. A repeat of the v0.3.0 axis error now fails both the local coordinate gate and the live Blender height-ratio gate before review output is accepted.
