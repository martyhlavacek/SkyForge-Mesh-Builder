# Build Verification — SkyForge Mesh Builder Sidecar v0.2.1

**Date:** 30 July 2026  
**Purpose:** Record what was mechanically verified in the build sandbox and what remains dependent on Marty's local Blender installation.

## Verified in this sandbox

| Check | Result |
|---|---|
| Python compilation (`compileall`) | PASS |
| Blender script Python syntax / AST parse | PASS |
| Pure-Python and source-contract tests | **18 passed** |
| Flask endpoint tests | **1 module skipped** because Flask/Werkzeug are unavailable in this sandbox |
| Expected dependency-backed local suite | **21 passed, zero skipped** |
| Pinned-camera projected-scale ordering | PASS |
| Render/post-process contract split | PASS |
| Settings-observation and live-evidence source contract | PASS |
| Thruster descendant exclusion source contract | PASS |
| Authority mask, contact sheet, IoU metadata and asset measurements | PASS with synthetic Pillow fixtures |
| Traversal containment helper tests | PASS |
| Package compilation after hierarchy-bake correction | PASS |

## Lint status

Ruff is pinned in `requirements.txt`, configured in `pyproject.toml`, and invoked by `scripts/run_tests.command`. Ruff could not be installed or executed in this sandbox because its package index does not provide it and public package downloads are unavailable. Local setup must therefore produce a successful Ruff run before the Mac calibration is considered green.

## Not verified in this sandbox

Blender is unavailable here. The following claims are implemented and asserted in source but require Blender 4.2+ execution:

- EEVEE Next engine and render-sample property compatibility;
- five-profile visual scale ordering in actual PNG renders;
- camera-fit validation at 0°, 20° and 36° pitch;
- descendant thruster exclusion from the real silhouette render;
- preservation of imported GLB/GLTF/OBJ/FBX hierarchies;
- neutral-pose `.blend` and GLB export;
- removal of all review-rig objects from exported files;
- baking normalization into rigid mesh vertex data;
- actual `run_report.json` scene evidence.

## Release gate

The source package is suitable for **Experiment 00 only**. It must not be used to score a mesh provider until a five-profile calibration run passes the protocol in `docs/EXPERIMENT_PROTOCOL.md`.

## Local commands

```bash
./scripts/setup.command
./scripts/configure_blender.command
./scripts/run_tests.command
./scripts/run.command
```

A green local preflight must report:

```text
Ruff: pass
Pytest: 21 passed, 0 skipped
```
