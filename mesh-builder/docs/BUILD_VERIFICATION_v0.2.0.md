# SkyForge Mesh Builder Sidecar v0.2.0 — Build Verification

**Build date:** 2026-07-29  
**Candidate:** SkyForge Mesh Builder Sidecar v0.2.0

## Executed in the build sandbox

| Check | Result |
|---|---|
| Python compile (`app`, `common`, `tests`) | PASS |
| AST parse: `blender/build_asset.py` | PASS |
| AST parse: `app/server.py` | PASS |
| AST parse: `app/pipeline.py` | PASS |
| Pipeline, contract, packaging, post-processing and source-security tests | **13 passed** |
| Flask runtime endpoint tests | **Skipped as one module** — Flask/Werkzeug were unavailable and the sandbox package index could not supply them |
| Blender execution | Not available in the build sandbox |

## What the executable tests cover

- filename/path sanitization;
- job ID shape and containment;
- image content validation;
- SHA-256 hashing;
- profile-scale math and numeric clamping;
- orientation-setting validation;
- provenance-bearing manifest generation;
- required-output and settings-consumption contracts;
- rendered-only packaging;
- native 96/64 post-processing;
- contact-sheet creation;
- silhouette comparison/IoU generation;
- derived pivot and collision measurements;
- source checks for CSRF enforcement, contained job lookup and craft-only GLB export settings.

## Required Mac verification

After `scripts/setup.command` installs the pinned dependencies, `scripts/run_tests.command` should also execute the three Flask endpoint tests. Experiment 00 must then establish the Blender-dependent evidence identified in `MBS-RES-0001` before any provider is scored.
