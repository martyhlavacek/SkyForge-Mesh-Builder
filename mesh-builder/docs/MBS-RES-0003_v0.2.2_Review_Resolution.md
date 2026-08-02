# MBS-RES-0003 — SkyForge Mesh Builder Sidecar v0.2.2 Review Resolution

**Artifact:** SkyForge Mesh Builder Sidecar v0.2.2  
**Responds to:** `MBS-CR-0003_v0_2_1_Verification_Review.md`  
**Date:** 30 July 2026  
**Disposition:** Candidate ready for local preflight and Experiment 00. Experiment 00 is not yet accepted.

## Decision

The review's **HOLD on Experiment 00** is accepted. Version 0.2.1 must not be used for calibration or provider scoring. Version 0.2.2 corrects the transform-bake ordering, calibrates the canonical frame from the supplied sweep, repairs the lint configuration and closes every item identified as P1 before Experiment 01.

The experiment remains gated on a real Blender 4.2+ calibration run on Marty's Mac. Source closure is not represented as a passed Blender experiment.

## Finding disposition

| ID | Disposition | v0.2.2 resolution |
|---|---|---|
| MBS-45 | Closed in source and independent math probe; Blender acceptance pending | Every mesh world matrix and the normalized world bounds are captured before hierarchy mutation. `craft_root` is reset to identity before the bake loop. Mesh data receives the captured world transform, then each mesh is parented under the identity root with identity parent inverse and basis. Residual mesh matrices and world-bound drift are measured and fail the job. |
| MBS-46 | Source/configuration closure; local Ruff execution required | `docs`, `workspace` and `.venv` are excluded from Ruff. `common` and `app` are declared first-party packages. The production and test import blocks were normalized. `run_tests.command` uses non-mutating `ruff check .` before pytest. Ruff could not be installed in the build sandbox, so a zero-exit Ruff run remains an explicit local preflight gate. |
| MBS-47 | Closed by measured calibration | The supplied sweep's maximum requirement (`8.364180`) and minimum viable margin (`1.322400`) are retained as evidence. The governed margin is `1.400000`, producing one canonical orthographic scale of `8.855000` and approximately 5.5% fallback-fixture headroom. The live clipping validator remains active. |
| MBS-50 | Closed | Normalization evidence is derived at export time from root identity, every mesh matrix, and before/after world bounds. `bakedIntoMeshData` and `rootTransformMustBeHonoured` in `asset.json` are copied from that measured evidence rather than typed literals. |
| MBS-48 | Closed | The structurally constant `theoreticalCeiling` field is removed. The useful round-trip measurement is retained as `achievableCeilingAtRenderResolution`. |
| MBS-49 | Closed | Experiment identity is an explicit UI and manifest field (`experiment_00` or `experiment_01`) and is copied into `review.json`. It is never inferred from mesh presence. Experiment 01 is rejected without a mesh. |
| MBS-51 | Closed | Armatures are rejected immediately after import sanitation, before normalization, materials, rendering or export. The static-mesh boundary is stated beside the upload control and in the protocol. |
| MBS-55 | Closed opportunistically | A SIGTERM handler terminates registered Blender child processes before interpreter exit. Normal exit retains the existing `atexit` cleanup. |
| MBS-52 | Deferred P2 | The one-process semaphore is retained. A bounded queue with queue-position reporting is outside this corrective revision. |
| MBS-53 | Partially superseded | The source-order regression test now checks capture → root reset → child mutation, and the supplied executable transform-order probe is retained. A true Blender behavioural test still belongs in the local calibration evidence. |
| MBS-54 | Deferred P2 | The 96×96 centroid loop is bounded and negligible. It is not on the critical experiment path. |

## Transform-bake contract

A successful export now requires all of the following observed conditions:

1. The review bank root is neutral before export.
2. The review camera, lights, bank root and effect geometry have been removed.
3. `craft_root.matrix_world` is identity.
4. Every exported mesh matrix is identity within `1e-6`.
5. Mesh world bounds before and after baking agree within `1e-5`.
6. `normalizationBakedIntoMeshData` is derived true.
7. `rootTransformMustBeHonoured` is derived false.

The job cannot reach `rendered` status or become downloadable if any condition fails.

## Canonical-frame contract

The frame is pinned globally, not fitted per craft:

```text
base span                 5.500000
largest governed profile  1.150000
measured minimum margin   1.322400
selected governed margin  1.400000
canonical ortho scale     8.855000
measured fixture maximum  8.364180
fixture headroom          0.490820 world units (~5.5%)
```

The calibration source is retained under `docs/MBS-CR-0003_evidence/`. The historical probe prints the v0.2.1 configured margin (`1.23`) deliberately; v0.2.2 consumes its measured maximum and governs the replacement value in `common/mesh_math.py`.

## Required acceptance sequence

1. Run `scripts/setup.command`.
2. Run `scripts/configure_blender.command` against Blender 4.2+.
3. Run `scripts/run_tests.command`; accept only Ruff exit 0 and **23 passed, zero skipped**.
4. Run Experiment 00 for all five profiles using the protocol controls.
5. Inspect the exported GLB in Blender and verify identity transforms and normalized coordinates.
6. Accept Experiment 00 only after all calibration gates are recorded.
7. Only then run Experiment 01 with a provider mesh.

## Remaining boundary

This resolution does not claim that Blender was executed in the build sandbox. It closes the reviewed defects in source and in pure-Python evidence, then deliberately leaves the final calibration verdict to the environment that will actually render and export the asset.
