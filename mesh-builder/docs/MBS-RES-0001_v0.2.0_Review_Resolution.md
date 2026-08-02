# MBS-RES-0001 — Resolution of MBS-CR-0001

**Candidate:** SkyForge Mesh Builder Sidecar v0.2.0  
**Review:** MBS-CR-0001  
**Disposition:** P0 closed in source; Blender-dependent items require local execution evidence.

## P0 resolution

| Finding | Resolution |
|---|---|
| MBS-1 | Banking is isolated on a review parent. The parent is reset, the craft is unparented with world transform preserved, all review objects are removed, and only the craft hierarchy is selected for GLB export. |
| MBS-2 | The authority is now read during post-processing. Four contact sheets, a straight-down silhouette comparison and silhouette IoU are mandatory outputs. |
| MBS-3 | Blender emits 4× masters; Pillow emits true 96 px and 64 px images using both Lanczos and nearest-neighbour filters. |
| MBS-4 | The profile scale multiplies the canonical 5.5-unit target span. |
| MBS-5b | Packaging is blocked until every required output exists and is non-empty and every required setting appears in `run_report.json` as consumed. |
| MBS-8 | Source forward/up axes are explicit manifest settings and are transformed into canonical `+Y` forward / `+Z` up. The protocol requires an orientation retest before provider rejection. |
| MBS-9 | Thrusters are implemented as review-only emissive geometry and excluded from the normalized mesh. Destruction is removed from the UI and explicitly recorded as unimplemented. |

## P1 resolution

| Finding | Resolution |
|---|---|
| MBS-5a | Job IDs are regex-validated, resolved and containment-checked. Archives live under `workspace/_archives`, outside the archived job. |
| MBS-6 | Blender path moved to `config.json`/environment. Mutating requests require a session-bound CSRF token. |
| MBS-7 | Only imported hierarchy roots are reparented and their world transforms are explicitly preserved. Mesh leaves are not flattened by blind parent assignment. |
| MBS-10 | Pivot is derived from the neutral 96 px alpha centroid. Collision is derived from neutral alpha bounds with a documented 0.72 inset. Empty anchors are represented as `null`. |
| MBS-11 | Provider, model/version, licence, URL, retrieval date, input authority hash and distribution approval are recorded. Missing core provenance blocks job creation. |
| MBS-12 | Blender runs in a background thread. Status is persisted and polled; stdout/stderr stream directly to files and survive timeout. |
| MBS-13 | Bank, review-size and camera-pitch values are parsed and clamped server-side. Master resolution is capped at 512 × 512. |
| MBS-14 | Blender 4.2+ is asserted before execution; BSDF lookup uses node type rather than localized name. |
| MBS-15 | Orthographic fit is calculated from projected bounds across neutral and both bank poses, including Z projection and review effects, with margin. |

## Additional closures

- MBS-16: camera pitch is a recorded job setting; the protocol requires 0°/20°/36° comparison runs.
- MBS-18: profile lookup and numeric parse errors now return named messages; unexpected faults return a generic 500 response.
- MBS-19: regression tests now cover path safety, image validation, manifests, contracts, packaging, CSRF, clamping, unknown profiles and traversal.
- MBS-20: archives are reused and only rendered jobs package; the 20 most recent jobs are retained.
- MBS-21: sidecar asset JSON is explicitly marked pre-schema and non-integratable until a mapping CR is approved.
- MBS-22: profiles reload per request.
- MBS-23: authority images are decoded and dimension-checked with Pillow.
- MBS-24: each completed run emits a `review.json` gate template and cleanup timer field.
- MBS-25: Blender launches with `--factory-startup`, and the script also calls `read_factory_settings(use_empty=True)`.

## Remaining local validation

The build environment does not contain Blender. The following claims must therefore be confirmed on Marty's Mac before Experiment 01:

1. Blender 4.2+ completes the background script.
2. GLB/GLTF, OBJ and FBX hierarchy preservation works with real provider samples.
3. The selected camera pitch and NW lighting match the approved SkyForge terrain perspective.
4. Thruster placement is visually correct for the approved gunship.
5. Clean GLB inspection confirms no review rig nodes.
6. Projected-fit calculations prevent clipping at ±18° on a wide real craft.

The correct next action is Experiment 00, not provider scoring.
