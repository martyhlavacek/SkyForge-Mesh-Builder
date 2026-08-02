# MBS-CR-0003 — Verification Review: SkyForge Mesh Builder Sidecar v0.2.1

**Artifacts under review:**
- `SkyForge_Mesh_Builder_Sidecar_v0_2_1.zip` (33 files, 2 053 lines of Python)
- `MBS-RES-0002_v0.2.1_Review_Resolution.md`
- `docs/EXPERIMENT_PROTOCOL.md` v0.2.1
- `docs/BUILD_VERIFICATION_v0.2.1.md`

**Author:** Sol (external)
**Reviewer:** Claude (independent verification of resolution claims)
**Predecessors:** MBS-CR-0001 (25 findings), MBS-CR-0002 (19 findings)
**Date:** 2026-07-30

**Verdict:** **HOLD on Experiment 00 — one more revision required.**

MBS-26 is genuinely closed and I can confirm it numerically. Seventeen of the nineteen CR-0002 findings are closed, several to a higher standard than requested. But three defects will stop the calibration run before it produces evidence:

1. **The bomber job fails at the clipping validator** at the protocol's own settings (pitch 20°, thrusters on). Experiment 00 run #1 aborts.
2. **`normalized.glb` is exported at the original imported coordinates.** The MBS-36 fix bakes the normalization into vertex data and then undoes it via a transform-ordering error.
3. **`scripts/run_tests.command` fails before pytest runs.** The green preflight documented in the build verification cannot be achieved as shipped.

None is conceptually hard. All three are ordering or calibration errors rather than design errors, and the v0.2.1 architecture is sound enough that each is a localized fix.

---

## 1. Verification method

Same standard as CR-0002: every falsifiable claim executed, Blender-dependent claims verified by reimplementing the script's own math and by simulating Blender's parenting semantics. Findings tagged **[probe]** (executed) or **[read]** (source analysis).

New capability this round: **Ruff installed successfully in the audit sandbox**, so I was able to run the lint gate the build sandbox could not.

### 1.1 Independent confirmation of `BUILD_VERIFICATION_v0.2.1.md`

| Claim | Independent result |
|---|---|
| Pure-Python and source-contract tests: 18 passed | Confirmed |
| Flask endpoint module skipped in the build sandbox | Confirmed as an environment limitation |
| Expected dependency-backed local suite: **21 passed, zero skipped** | **Confirmed — `21 passed in 0.78s`** |
| Pinned-camera projected-scale ordering: PASS | **Confirmed independently** (§3, MBS-26) |
| Render/post-process contract split: PASS | Confirmed |
| Settings-observation and live-evidence source contract: PASS | Confirmed, with one surviving literal (MBS-50) |
| Ruff "could not be installed or executed in this sandbox… Local setup must produce a successful Ruff run" | **Ruff runs here. It fails: 9 errors.** → MBS-46 |

The build verification document is again honest and its stated limits are accurate. Flagging Ruff as an unverified local gate was the right call — the gate simply does not pass.

---

## 2. Disposition of MBS-CR-0002

| ID | Claimed | Verified | Evidence |
|---|---|---|---|
| MBS-26 | Closed | **Closed** [probe] | Pixel ordering exactly matches the protocol's required order (§3) |
| MBS-27 | Closed | **Closed** | `RecordingSettings` is real; export evidence is measured; `verify_required_outputs` now re-checks pose and rig evidence. One literal survives → MBS-50 |
| MBS-28 | Closed | **Closed in source** [read] | `set_effect_visibility` walks `[effect_root, *descendants(effect_root)]`; names recorded in `frameEvidence`. Render-verification still requires Blender |
| MBS-29 | Closed | **Closed** | Three-stage contract: `RENDER` → postprocess → `POSTPROCESS` → complete |
| MBS-30 | Closed | **Closed** | `remove_object_preserve_descendants` reparents before removal, and is reused in `clean_scene_for_export` |
| MBS-31 | Closed | **Closed, one field vacuous** [probe] | Structured record with invariants, canvas, margin, resample. `theoreticalCeiling` → MBS-48 |
| MBS-32 | Closed | **Closed** [probe] | Measured tile spans: authority 69×83 px vs neutral 70×80 px (was ~25–30% mismatched) |
| MBS-33 / MBS-17 | Closed | **Closed** | `taa_render_samples = 64` pinned server-side, `look = 'None'`, `renderState` read back from the live scene. MBS-17 finally has a disposition |
| MBS-34 | Closed | **Closed** | `ImageChops`-vectorized, threshold named as `OPAQUE_BG_DISTANCE_THRESHOLD`, `authority_mask.png` emitted and recorded |
| MBS-35 | Closed | **Closed** | `masterResolution` (256–512) throughout UI, schema and script; no `frameSize` references remain outside historical docs |
| MBS-36 | Closed | **NOT CLOSED — regressed** [probe] | → **MBS-45** |
| MBS-37 | Closed | **Closed** | `anchor_record` declares `method: bounding_box_heuristic` and `units: blender_world_units`; pivot and collision both declare source and units |
| MBS-38 | Closed | **Closed** | `conftest.py` fixes path resolution; traversal tests require exactly 404 for both vectors; source tests use AST plus negative assertions on the removed literals |
| MBS-39 | Closed | **Half closed** | Ruff pinned and wired, but the gate fails → **MBS-46** |
| MBS-40 | Closed | **Closed** | Single assignment per render-state property |
| MBS-41 | Closed | **Closed** | `BoundedSemaphore(1)`, `_ACTIVE_PROCESSES` registry, `atexit` termination |
| MBS-42 | Closed | **Closed** [probe] | Three-colour overlay: authority-only blue, render-only orange, intersection green |
| MBS-43 | Closed | **Closed** | `_STATUS_LOCK` RLock around read-modify-write |
| MBS-44 | Closed | **Closed** | `pivot` now carries `source`, `units`, `value` |

**17 closed, 1 half-closed, 1 regressed.**

---

## 3. MBS-26 is closed — confirmed independently

The mechanism is right: `canonical_ortho_scale()` derives one frame from the largest governed profile, the server writes it into every manifest, and `projected_required_scale` was demoted to `validate_canonical_frame`. Running the shipped fixture through all five profiles at the pinned frame (7.77975) at pitch 20°:

| profile | scale | px W @96 | px H @96 |
|---|---:|---:|---:|
| enemy_bomber | 1.15 | 75.08 | 77.79 |
| enemy_gunship | 1.00 | 65.28 | 67.64 |
| player_fighter | 0.82 | 53.53 | 55.47 |
| enemy_interceptor | 0.72 | 47.00 | 48.70 |
| enemy_drone | 0.55 | 35.91 | 37.20 |

Bomber > gunship > fighter > interceptor > drone — exactly the order Experiment 00 gate 4 now specifies. A drone at 36 px against a bomber at 75 px is a real readability signal. **This finding is properly closed, and the protocol gate that tests it is well-written.**

The correct instinct is also visible in the protocol text: *"The canonical orthographic scale… must never be refitted to an individual craft."* That sentence is the durable form of the fix.

---

## 4. New findings

### HIGH

---

#### MBS-45 — `bake_static_mesh_transforms` bakes the normalization and then cancels it; the export lands at original imported coordinates **[probe]**

`build_asset.py:430-452`. The mesh loop runs first, then the root is reset:

```python
world_matrices = {obj: obj.matrix_world.copy() for obj in meshes}
for obj in meshes:
    ...
    obj.data.transform(world_matrices[obj])
    obj.parent = craft_root
    obj.matrix_world = Matrix.Identity(4)      # craft_root is still N here
...
craft_root.matrix_world = Matrix.Identity(4)   # line 450 — after the loop
```

Blender computes `matrix_world = parent.matrix_world @ matrix_parent_inverse @ matrix_basis`, and assigning `matrix_world` sets `matrix_basis = (parent.matrix_world @ mpi)⁻¹ @ value`. At the moment of the assignment, `craft_root.matrix_world` is still the normalization matrix **N** = `Scale(s) @ Translation(-center) @ orientation`. So each mesh receives `matrix_basis = N⁻¹`. Line 450 then changes the parent from **N** to identity — which does not re-derive the children's bases, so every mesh ends at `matrix_world = N⁻¹`.

Net result: vertex data holds `N @ local @ v`, the object transform contributes `N⁻¹`, and the geometry renders at `local @ v` — **the original imported coordinates, unnormalized, unoriented and unscaled.**

I modelled Blender's parenting semantics and ran both orderings:

```
Target (normalized world position):        [1.9578  2.2590  0.3163]

v0.2.1 as written (root reset after loop):
  craft_root.matrix_world  : identity  (True)
  mesh.matrix_world        : uniform scale 0.664 + offset   == inverse(N)  (True)
  geometry lands at        : [1.4  1.7  0.35]      <- original imported coords
  matches normalized pose  : False

Counterfactual (root reset before loop):
  mesh.matrix_world identity : True
  geometry lands at          : [1.9578  2.2590  0.3163]
  matches normalized pose    : True
```

`0.664 = 1/1.506` — the exact inverse of the normalization scale used in the model.

Two things make this worse than a plain bug:

- **The evidence looks clean.** `craftRootMatrixAtExport` is measured, and it correctly reports identity — because the defect migrated from the root to the children, which are not measured. This is the third time in this series that adding a measurement at one location moved the defect to an adjacent unmeasured one.
- **MBS-36 is regressed rather than unfixed.** In v0.2.0 the normalization was correct but expressed as a root transform. In v0.2.1 it is baked into vertices and then algebraically undone. v0.2.0's `normalized.glb` was usable if you honoured the root transform; v0.2.1's is not usable either way.

**Fix.** Reset the root before the loop, and assign the basis rather than the world:

```python
craft_root.matrix_world = Matrix.Identity(4)
for obj in meshes:
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    obj.data.transform(world_matrices[obj])
    obj.parent = craft_root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = Matrix.Identity(4)
```

Then **measure it**, per the MBS-27 principle:

```python
non_identity = [o.name for o in mesh_descendants(craft_root)
                if (o.matrix_world - Matrix.Identity(4)).to_4x4()
                and max(abs(v) for row in (o.matrix_world - Matrix.Identity(4)) for v in row) > 1e-6]
if non_identity:
    raise RuntimeError('Normalization was not baked; residual mesh transforms: ' + ', '.join(non_identity))
run_report['meshMatricesIdentityAtExport'] = not non_identity
```

Local acceptance check for Marty, after the fix — in the Blender console with `normalized.blend` open:

```python
import bpy
for o in bpy.data.objects:
    print(o.name, o.type, [round(v, 6) for v in o.matrix_world.to_translation()],
          [round(v, 6) for v in o.matrix_world.to_scale()])
# every mesh must print translation (0,0,0) and scale (1,1,1)
```

---

#### MBS-46 — `scripts/run_tests.command` aborts at the lint gate; the documented green preflight is unattainable **[probe]**

`scripts/run_tests.command` is `set -e` followed by `ruff check .` then `python -m pytest -q`. Ruff was unavailable in Sol's build sandbox but installs cleanly here:

```
$ ruff check .
Found 9 errors.
[*] 4 fixable with the `--fix` option.

$ (simulating set -e)
ruff FAIL (exit 1) -> set -e aborts; pytest NEVER RUNS
```

Breakdown:

| Source | Count | Rules |
|---|---:|---|
| `docs/MBS-CR-0002_evidence/probe_ortho_scale_cancellation.py` | 7 | E702, E401, I001 |
| `app/server.py` | 1 | I001 |
| `tests/test_server.py` | 1 | I001 |

Seven of the nine come from the evidence probe I supplied with CR-0002, which Sol vendored into `docs/` — reasonable for provenance, but `pyproject.toml` excludes only `workspace` and `.venv`, so a throwaway audit script is now linted as production source. That one is my fault as much as Sol's; the fix is to add `docs` to the exclude list.

The remaining two are genuine and auto-fixable:

```
$ ruff check app tests --fix
All checks passed!   (exit 0)
```

So `BUILD_VERIFICATION_v0.2.1.md`'s stated green preflight —

```
Ruff: pass
Pytest: 21 passed, 0 skipped
```

— cannot be reached on a clean install. Marty will double-click `run_tests.command` and see a lint failure with no test results, before Blender is ever involved.

**Fix.** Add `"docs"` to `[tool.ruff].exclude`, run `ruff check . --fix`, and re-run the gate to confirm exit 0. Worth also considering `ruff check --no-fix` in the script so the preflight never silently rewrites source.

---

#### MBS-47 — The canonical frame is undersized for the largest profile with thrusters; Experiment 00 run #1 fails at the clipping validator **[probe]**

`canonical_ortho_scale` is computed **analytically** from the planform world span:

```python
return round(base_span * maximum_profile_scale * margin, 6)   # 5.5 x 1.15 x 1.23 = 7.77975
```

`validate_canonical_frame` compares that against a **measured** projected extent that includes review-only geometry:

```python
required_review = projected_required_scale(bank_root, visible_objects, camera, [-bank, 0, bank])
validate_canonical_frame(required_review, canonical_ortho_scale, 'review frames')
```

Two different methods, never reconciled. Reimplementing both against the shipped fixture, thruster cone geometry included exactly as `create_thrusters` builds it:

| profile | pitch | thrusters | required | canonical | headroom | verdict |
|---|---:|---|---:|---:|---:|---|
| bomber | 20° | on | 8.3622 | 7.77975 | **−0.5825** | **JOB FAILS** |
| bomber | 36° | on | 7.6303 | 7.77975 | +0.1495 | OK |
| bomber | 20° | off | 7.7765 | 7.77975 | **+0.0032** | OK (0.04% margin) |
| bomber | 0° | off | 7.2105 | 7.77975 | +0.5693 | OK |
| gunship | 20° | on | 7.2715 | 7.77975 | +0.5083 | OK |
| fighter | 20° | on | 5.9626 | 7.77975 | +1.8171 | OK |
| interceptor | 20° | on | 5.2355 | 7.77975 | +2.5443 | OK |
| drone | 20° | on | 3.9993 | 7.77975 | +3.7804 | OK |

The protocol's required five-profile run specifies bank 18°, pitch 20°, **thrusters enabled** — and lists **Enemy — Bomber first**. So Experiment 00 aborts on its first job with `Canonical orthographic frame would clip review frames: required=8.362203, canonical=7.779750`.

The mechanism is that thrusters extend the craft rearward by `depth × 0.08 + exhaust_length/2`, which for the bomber adds roughly 16% to the −Y extent, and `projected_required_scale` measures `abs()` symmetrically about the camera axis, so the whole frame must grow to accommodate a one-sided extension.

The 0.0032 headroom on the craft-only bomber row is the diagnostic detail: **1.23 was reverse-derived from exactly that configuration** (craft only, pitch 20°, bank ±18°, this fixture) and then generalized to conditions it was never measured against. That is the project's standing lesson about thresholds set by assertion rather than calibration, appearing in a new place — and it is the reason the validator, which is correct, fires on our own protocol.

**Fix — calibrate rather than assert.** Add a preflight that sweeps the real geometry and reports the maximum required scale across every configuration the protocol mandates:

- all five profiles × pitches {0°, 20°, 36°} × banks {−18°, 0°, +18°} × thrusters {on, off}

then set `CANONICAL_ORTHO_MARGIN` from that measured maximum plus explicit headroom, and record both the measured maximum and the chosen margin in `run_report`. For this fixture the required margin is `8.3622 / (5.5 × 1.15) = 1.322`; `1.40` would give roughly 6% headroom for provider meshes with taller or wider proportions than the fixture.

Note the trade-off to record deliberately: raising the margin shrinks every craft proportionally (bomber 75.1 px → 65.9 px at margin 1.40). The ordering is preserved, which is what gate 4 tests, but the absolute review size changes and should be stated in the protocol rather than discovered.

A second, cheaper option worth considering: exclude review-only effect geometry from the *review-frame* fit as well as the silhouette fit, and accept that thrusters may extend past the frame edge. I would not recommend it — a clipped exhaust in the review frame is exactly the kind of artifact that wastes a reviewer's attention — but it is a valid choice if made explicitly.

---

### MEDIUM

---

#### MBS-48 — `theoreticalCeiling` is structurally 1.0 and cannot vary **[probe]**

```python
theoretical_ceiling = _mask_iou(authority, authority.copy())
```

The IoU of a mask with a copy of itself is 1.0 by construction. Verified against the bundled sample and three random masks:

```
_mask_iou(authority, authority.copy()) = 1.0
random mask 0: self-IoU = 1.0
random mask 1: self-IoU = 1.0
random mask 2: self-IoU = 1.0
```

So `asset.json` carries a "measurement" that is a constant wearing a function call. It is a milder form of the MBS-27 pattern — computed rather than typed, but with a structurally fixed result — and it is the field most likely to be misread as "the best score this pipeline can produce."

The genuinely useful number is already there: `roundTripCeilingAtRenderResolution` measured **0.992167** on my identical-silhouette probe, against a `value` of 0.993177. That is the ceiling a reviewer needs.

**Fix.** Drop `theoreticalCeiling`, or replace it with something that can fail — e.g. the IoU of the authority mask against itself after a full save/reload round trip, which would detect mask-serialization drift. Rename the surviving field to make its role obvious (`achievableCeiling`).

---

#### MBS-49 — The experiment label is inferred from whether a mesh was uploaded, which contradicts the protocol **[read]**

```python
_write_review_template(job, silhouette, 'Experiment 00' if manifest.get('mesh') is None else 'Experiment 01')
```

The protocol explicitly permits two inputs for Experiment 00:

> Use either: a known-good hand-authored spacecraft mesh; or the included fallback fixture, with identity-specific gates omitted.

A calibration run using a hand-authored mesh — the *preferred* option, since the fallback requires omitting identity gates — will be labelled `Experiment 01` in `review.json`. Given that `review.json` is the record a provider verdict is eventually traced to, a mislabelled calibration run is a provenance defect.

**Fix.** Add `experiment` as a declared job setting with values `experiment_00` / `experiment_01`, surface it in the UI, and record it in the manifest. Inference is the wrong mechanism for a field that governs how the evidence is later read.

---

#### MBS-50 — Three literals survive in the evidence path, and MBS-45 makes all three false **[read]**

`build_asset.py:502` — `'normalizationBakedIntoMeshData': True`
`build_asset.py:532-533` — `'bakedIntoMeshData': True`, `'rootTransformMustBeHonoured': False`

Every other field in `export_evidence` is now measured. These three are typed, and given MBS-45 each is currently incorrect: the normalization is not effectively baked, and the mesh node transforms *must* be honoured — honouring them un-normalizes the craft.

This is the same field family that MBS-27 was raised about, and it is the field that would have caught MBS-45 had it been derived. Deriving it is three lines (see the fix under MBS-45).

---

#### MBS-51 — The armature rejection fires after the full render set has been produced **[read]**

`bake_static_mesh_transforms:431-433` raises on armature-backed imports. It is called from `export_clean_asset` (line 466), which `main()` calls at line 619 — **after** `render_review_set` at line 606.

So an armature-bearing provider mesh consumes the entire render sequence (four renders at up to 512², plus the fit validation passes), then fails at export with everything discarded. On a 900-second budget that is the most expensive possible place to discover an unsupported input.

**Fix.** Move the check immediately after `sanitize_imported_objects()`, where `ARMATURE` is already in the `supported` set and the objects are available. Fail in the first second, not the last. Worth also stating the limitation in the UI next to the mesh upload field, since a rigged GLB is a plausible thing for a provider to return.

---

### LOW

**MBS-52 — Queued jobs create unbounded blocked threads.** `_JOB_SEMAPHORE = BoundedSemaphore(1)` is acquired inside `run_job`, so the HTTP handler returns 202 immediately and every submission spawns a thread that blocks on the semaphore. Correct behaviour, but N submissions produce N live threads and N jobs sitting at `queued` with no queue-position feedback. Since `prune_workspace` correctly protects `queued` jobs from deletion, nothing is lost — but a bounded work queue with a reported position would be more honest than an unbounded pile of blocked threads.

**MBS-53 — `test_static_transform_bake_captures_all_world_matrices_before_reparenting` validates the second-order fix while the first-order bug is uncovered.** The test asserts that the capture line appears *before* the mutation line in the source text. That ordering is correct and the test passes. But the ordering that is actually wrong — `craft_root.matrix_world = Matrix.Identity(4)` appearing *after* the loop rather than before — is not asserted, and could not be caught by a string-order assertion without knowing to look for it. The lesson is the same one from CR-0002: source-order assertions can only encode the defects you already found. The behavioural check under MBS-45 replaces this test entirely.

**MBS-54 — `_measure_asset` retains a pure-Python double loop.** Two full 96×96 passes for the centroid (about 18 k iterations). Negligible at review size, and correct — but `ImageStat` or a NumPy moment computation would be clearer and would match the vectorization already applied in `_alpha_mask`.

**MBS-55 — `atexit` termination will not fire on `SIGTERM` or `SIGKILL`.** `terminate_active_processes` is registered with `atexit`, which runs on normal interpreter exit and on `SIGINT` (via `KeyboardInterrupt`), but not on `SIGTERM`. Closing the terminal window that `run.command` opened is a plausible path to an orphaned Blender process. Adding a `signal.signal(signal.SIGTERM, ...)` handler alongside the `atexit` hook closes it.

---

## 5. Prioritised action list

### P0 — before Experiment 00 is run

| ID | Item | Why it blocks |
|---|---|---|
| MBS-47 | Calibrate `CANONICAL_ORTHO_MARGIN` from a measured sweep | Bomber job fails at the validator; Experiment 00 run #1 aborts |
| MBS-45 | Reset `craft_root` before the bake loop; assert mesh matrices are identity | `normalized.glb` currently exports at original imported coordinates |
| MBS-46 | Exclude `docs` from Ruff, apply `--fix` | `run_tests.command` never reaches pytest |
| MBS-50 | Derive the three normalization booleans from measurement | These are the fields that would have caught MBS-45 |

### P1 — before Experiment 01

MBS-51 (move the armature check to import time), MBS-49 (declare the experiment rather than infer it), MBS-48 (drop or replace the vacuous ceiling).

### P2 — housekeeping

MBS-52 (bounded queue with reported position), MBS-53 (replace the source-order test with the behavioural check), MBS-54, MBS-55.

---

## 6. Assessment

This is the strongest revision in the series. MBS-26 — the finding that gated the whole experiment — is properly and durably closed, and the protocol now encodes the principle rather than just the patch. The evidence architecture that CR-0002 asked for is largely built: `RecordingSettings` works, export evidence is read from the live scene, and `verify_required_outputs` refuses to pass a job whose own report admits a non-neutral pose or a surviving review rig. The contract split, the three-colour overlay, the authority-tile span matching, the vectorized mask, the process registry and the RLock are all correct. Seventeen closures is a real result.

The pattern that persists is narrower than before but has not gone away. Across MBS-45 and MBS-50, the shape is: **a value that could be measured is instead asserted, and the defect settles precisely where the measurement stops.** `craftRootMatrixAtExport` is measured and correct; the mesh matrices beside it are not measured and are wrong. `normalizationBakedIntoMeshData` is typed as `True` and is false. Three rounds in, this is worth treating as a structural rule rather than a recurring finding: **in this codebase, every boolean in an evidence file should be the result of a comparison performed at the moment of writing, and every threshold should be the output of a sweep rather than an input to one.** MBS-47 is the same rule applied to constants — 1.23 was derived from one configuration and asserted across all of them.

The good news is that all three P0 items are small. MBS-45 is a two-line reordering plus an assertion. MBS-46 is one line of TOML and a `--fix`. MBS-47 is a sweep script and a new constant. The instrument is nearly right; it needs one more pass to stop lying to itself about it.

Recommended sequence: v0.2.2 with the four P0 items, confirm `ruff check .` exits 0 and `pytest -q` reports **21 passed**, then run Experiment 00 across all five profiles. Gate 4 becomes the acceptance test for MBS-26 (already verified in math, needs pixels), gate 3 plus the Blender-console matrix check becomes the acceptance test for MBS-45, and the bomber job completing at all becomes the acceptance test for MBS-47.
