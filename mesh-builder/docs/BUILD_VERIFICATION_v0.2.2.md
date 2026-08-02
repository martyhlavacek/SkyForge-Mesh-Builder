# Build Verification — SkyForge Mesh Builder Sidecar v0.2.2

**Date:** 30 July 2026  
**Candidate:** `SkyForge_Mesh_Builder_Sidecar_v0.2.2`

## Verification performed in the build sandbox

| Check | Result |
|---|---|
| Python compilation (`python -m compileall -q app blender common tests`) | PASS |
| Pure-Python/source regression suite (`python -m pytest -q`) | **19 passed, 1 module skipped** |
| CR-0003 transform-order probe | PASS — corrected ordering lands geometry at the normalized pose |
| CR-0003 canonical-frame sweep | PASS as calibration evidence — measured maximum `8.364180`, minimum margin `1.322400` |
| Governed v0.2.2 frame calculation | PASS — margin `1.400000`, canonical scale `8.855000`, positive fixture headroom |
| AST parse of Blender/server/pipeline/tests | PASS |
| Unused-import and import-block manual inspection | PASS |
| Archive hygiene/integrity | PASS — ZIP test clean; no virtualenv, caches, bytecode or workspace jobs included |

## Environment-limited checks

### Flask endpoint suite

The sandbox does not contain Flask or Werkzeug and its configured package index cannot provide them. The endpoint test module therefore skips at import. Four endpoint tests are present. With the pinned requirements installed, the expected local result is:

```text
23 passed, 0 skipped
```

A local skip is not a green result.

### Ruff

Ruff `0.15.22` is pinned, configured and invoked by `scripts/run_tests.command`. The sandbox could not install or execute the Ruff binary because its package source was unavailable. The v0.2.2 source applies the exact review correction:

- exclude `docs`, `workspace` and `.venv`;
- declare `app` and `common` as first-party packages;
- normalize the production and endpoint-test import blocks;
- run `ruff check .` without source mutation.

A successful local Ruff run remains mandatory before Experiment 00.

### Blender

Blender is unavailable in the build sandbox. The following require the Mac-side Blender 4.2+ run:

- real GLB/FBX/OBJ import behaviour;
- EEVEE render output;
- parent/child matrix behaviour in the live Blender data model;
- clean GLB export and node inventory;
- silhouette exclusion of actual thruster objects;
- five-profile native-pixel ordering;
- bomber completion under the calibrated frame.

## Source contracts added in v0.2.2

- `craft_root` identity reset occurs after world-matrix capture and before child mutation.
- Every mesh receives identity `matrix_parent_inverse` and `matrix_basis` after its world transform is baked into mesh data.
- Every exported mesh matrix is measured.
- World bounds are measured before and after baking.
- Normalization booleans are comparison results, not assertions.
- The canonical-frame constant is backed by the retained sweep evidence.
- Experiment identity is explicit.
- Armatures fail before rendering.
- Silhouette measurement no longer reports a vacuous theoretical ceiling.
- SIGTERM invokes child-process cleanup.

## Local acceptance command

```bash
scripts/setup.command
scripts/configure_blender.command
scripts/run_tests.command
```

Do not proceed to Experiment 00 unless the last command reports Ruff success and **23 passed, zero skipped**.
