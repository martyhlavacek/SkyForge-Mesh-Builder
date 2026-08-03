# MBS-CR-0002 — Verification Review: SkyForge Mesh Builder Sidecar v0.2.0

**Artifacts under review:**
- `SkyForge_Mesh_Builder_Sidecar_v0_2_0.zip` (24 files, 1 623 lines of Python)
- `MBS-RES-0001_v0.2.0_Review_Resolution.md`
- `BUILD_VERIFICATION_v0.2.0.md`

**Author:** Sol (external)
**Reviewer:** Claude (independent verification of resolution claims)
**Predecessor:** MBS-CR-0001 (25 findings)
**Date:** 2026-07-30

**Verdict:** **CONDITIONAL GO for v0.2.1 — HOLD on Experiment 00.**
21 of 25 findings verified closed. One P0 (MBS-4) is **not closed**: it was fixed in world units and then cancelled by a new mechanism introduced in the same revision. One finding (MBS-17) has no disposition in the resolution document. The output contract is real; the settings-consumption contract is vacuous.

Experiment 00 should not be run until MBS-26, MBS-27 and MBS-28 are closed, because **Experiment 00's own calibration gate 4 will fail deterministically** on MBS-26 — and it will fail as a harness defect, which is the exact failure mode the two-experiment split was designed to prevent.

---

## 1. Verification method

Every closure claim in `MBS-RES-0001` was checked against the code, and the falsifiable ones were executed. Blender is not available in the audit sandbox, so Blender-dependent claims were verified by **numerically reimplementing the script's own math in pure Python/NumPy** and running it against the shipped profile data — that is what produced the MBS-26 result below. Findings are tagged **[probe]** (executed) or **[read]** (source analysis).

### 1.1 Independent confirmation of `BUILD_VERIFICATION_v0.2.0.md`

| Claim | Independent result |
|---|---|
| Pipeline/contract/packaging/post-processing/source-security tests: 13 passed | Confirmed |
| Flask endpoint tests skipped — Flask/Werkzeug unavailable in the build sandbox | Confirmed as a sandbox limitation, not a defect |
| — | **With Flask 3.1.1 present, the full suite is `16 passed in 0.85s`.** The three skipped tests pass. |

The build verification document is accurate and its stated limitations are honest. The `importorskip` guard is the right call; it is worth noting in the README that a green local run must show **16**, not 13, or a missing-dependency skip will read as a pass.

---

## 2. Disposition of MBS-CR-0001

| ID | Claimed | Verified | Evidence |
|---|---|---|---|
| MBS-1 | Closed | **Closed, with caveat** | Neutral pose restored; `clean_scene_for_export` genuinely asserts no camera/light survives (`build_asset.py:360`). Caveats → MBS-27, MBS-36 |
| MBS-2 | Closed | **Closed** | Authority read at `pipeline.py:463`; 4 contact sheets + IoU produced. Caveats → MBS-31, MBS-32 |
| MBS-3 | Closed | **Closed** [probe] | Ran `postprocess_outputs`; 96/64 Lanczos **and** nearest emitted, 24 output files |
| MBS-4 | Closed | **NOT CLOSED** [probe] | → **MBS-26**. Applied in world units, cancelled in the render |
| MBS-5a | Closed | **Closed** [probe] | All six traversal vectors → 404 |
| MBS-5b | Closed | **Half closed** | Output contract real and correct; settings contract vacuous → **MBS-27** |
| MBS-6 | Closed | **Closed** [probe] | No token → 403; `blenderPath` absent from form path; `SameSite=Strict` |
| MBS-7 | Closed | **Closed at one site** | `parent_preserve_world` is correct; the class recurs → **MBS-30** |
| MBS-8 | Closed | **Closed** | Axes are explicit, validated, orthogonality-checked; `orientation_matrix` verified right-handed for all 24 valid pairs; protocol amended with the retest requirement |
| MBS-9 | Closed | **Closed for destruction; caveated for thrusters** | Destruction correctly recorded as requested=false/implemented=false. Thrusters implemented but leak → **MBS-28**, **MBS-37** |
| MBS-10 | Closed | **Closed** [probe] | Pivot = alpha centroid, collision = alpha bounds × 0.72, both measured. Caveat → MBS-37 |
| MBS-11 | Closed | **Closed** [probe] | Each of provider/providerVersion/license blank → 400 with a named message |
| MBS-12 | Closed | **Closed** | `Popen` + streaming file handles + `try/except TimeoutExpired` with kill; logs survive timeout; background thread + `/api/jobs/<id>` polling |
| MBS-13 | Closed | **Closed** [probe] | `frameSize=99999 → 128`, `bankDegrees=-5 → 0` |
| MBS-14 | Closed | **Closed** | `require_supported_blender()` asserts ≥4.2; `principled_node` matches on `node.type` |
| MBS-15 | Closed | **Closed** | `projected_fit_scale` evaluates all bound corners in camera space across ±bank and neutral. But see MBS-26 |
| MBS-16 | Closed | **Closed** | Pitch is a clamped job setting; protocol mandates the 0°/20°/36° sweep |
| **MBS-17** | **Not mentioned** | **No disposition** | → **MBS-33**. Absent from every table in the resolution document |
| MBS-18 | Closed | **Closed** [probe] | Named errors; generic 500 for unexpected faults |
| MBS-19 | Closed | **Materially improved** | 3 → 16 tests. Weaknesses → MBS-38 |
| MBS-20 | Closed | **Closed** | Archive reuse via mtime, `_archives` outside job root, rendered-only packaging, 20-job retention |
| MBS-21 | Closed | **Closed** | `integrationStatus` field states pre-schema explicitly |
| MBS-22 | Closed | **Closed** | `load_profiles` called per request |
| MBS-23 | Closed | **Closed** [probe] | `verify()` + dimension bounds; `b'not a png'` rejected |
| MBS-24 | Closed | **Closed** | `review.json` with five gates + `cleanupMinutes` |
| MBS-25 | Closed | **Closed** | `--factory-startup` **and** `read_factory_settings(use_empty=True)` |

**21 closed, 2 half-closed, 1 not closed, 1 undispositioned.**

---

## 3. What improved, and is worth keeping

This is a serious revision, not a patch. Several things deserve explicit credit because they should be reused rather than re-litigated:

- **The experiment protocol rewrite is the strongest artifact in the package.** The Experiment 00 / 01 split, the mandatory orientation retest before provider rejection, and the stop condition clause — *"A harness failure, missing output, unconsumed setting or incomplete provenance invalidates the run rather than failing the provider"* — is exactly right. That last sentence is the one that protects the project from a confident wrong answer, and it should be copied into every future evaluation protocol in SkyForge.
- **Refusing to invent an IoU threshold.** "The first experiment establishes a baseline; it does not invent an acceptance threshold without observed provider data" directly addresses the standing project lesson that gates set by assertion rather than calibration are unreliable. This is the correct instinct, applied unprompted.
- **`parent_preserve_world` is the right primitive**, and its use in `create_bank_root` — isolating bank on a separate parent rather than mutating the craft — is a clean structural fix to MBS-1 rather than a defensive reset.
- **`clean_scene_for_export` asserts rather than assumes** (`build_asset.py:360`). This is a genuine transactional-core check.
- **CSRF via a custom request header** is the correct choice: a cross-origin form POST cannot set `X-SkyForge-CSRF` without a preflight, so the drive-by vector from MBS-6 is properly closed rather than papered over.
- **Provenance blocks job creation.** Making it a hard precondition rather than a warning is stronger than what MBS-11 asked for.
- **Both docs are honest about what was not verified.** The "Remaining local validation" list in the resolution document is accurate and complete for what it covers.

---

## 4. New findings

### HIGH

---

#### MBS-26 — `projected_fit_scale` cancels `profileScale`; MBS-4 is not closed, and Experiment 00 gate 4 will fail **[probe]**

This is the finding that gates the experiment.

`build_normalized_hierarchy` correctly applies the profile scale in world units (`build_asset.py:155-156`):

```python
target_span = 5.5 * profile_scale
scale = target_span / span
```

Then `render_review_set` immediately discards it (`build_asset.py:330-332`):

```python
camera.data.ortho_scale = projected_fit_scale(
    bank_root, visible_objects, camera, [-bank_degrees, 0, bank_degrees]
)
```

`projected_fit_scale` returns `max_extent × 2 × 1.14`, where `max_extent` is measured from *this craft after normalization*. Since the craft's extent is proportional to `profileScale`, and the ortho frame is set proportional to that extent, **the ratio is invariant and every craft renders at the same pixel size.**

I reimplemented `build_normalized_hierarchy`, `set_camera_pitch`, `set_bank` and `projected_fit_scale` in NumPy and ran the shipped fallback fixture through all five shipped profiles at pitch 20°, bank ±18°:

| profile | scale | world span | ortho_scale | rendered px @96 |
|---|---:|---:|---:|---:|
| enemy_gunship | 1.00 | 5.500 | 6.7622 | **75.11 × 77.82** |
| enemy_interceptor | 0.72 | 3.960 | 4.8688 | **75.11 × 77.82** |
| enemy_bomber | 1.15 | 6.325 | 7.7765 | **75.11 × 77.82** |
| enemy_drone | 0.55 | 3.025 | 3.7192 | **75.11 × 77.82** |
| player_fighter | 0.82 | 4.510 | 5.5450 | **75.11 × 77.82** |

The world span column confirms the fix Sol implemented is correct — `target_span()` works exactly as specified, and its unit test passes. The rendered column shows it never reaches the output. Identical to two decimal places across a 2.09× range of profile scales.

`docs/EXPERIMENT_PROTOCOL.md`, Experiment 00, calibration gate 4:

> "The bomber, gunship, fighter, interceptor and drone profile scales remain visibly different when the same fixture is used."

That gate cannot pass. And per the protocol's own rule, *"Any failure is a harness defect and must not be attributed to a provider"* — so the protocol will correctly catch this, but only after a full calibration run has been spent discovering it.

**Fix.** `ortho_scale` must be a **constant across jobs**, derived once from the largest profile scale plus bank and effect margin — not refitted per craft. Keep `projected_fit_scale` but demote it from *setter* to *validator*: compute the required extent, compare it against the pinned canonical `ortho_scale`, and fail the job with an explicit clipping error if it exceeds it. That preserves the MBS-15 fix while restoring MBS-4.

With `ortho_scale` pinned to the bomber's fit (7.7765):

| profile | scale | per-job ortho (v0.2.0) | pinned ortho (proposed) |
|---|---:|---:|---:|
| enemy_gunship | 1.00 | 75.1 × 77.8 px | 65.3 × 67.7 px |
| enemy_interceptor | 0.72 | 75.1 × 77.8 px | 47.0 × 48.7 px |
| enemy_bomber | 1.15 | 75.1 × 77.8 px | 75.1 × 77.8 px |
| enemy_drone | 0.55 | 75.1 × 77.8 px | 35.9 × 37.2 px |
| player_fighter | 0.82 | 75.1 × 77.8 px | 53.6 × 55.5 px |

A drone at 36 px against a bomber at 75 px is the readability signal the profile table was written to encode.

Note the secondary consequence: because `visible_objects` includes the thruster preview cones, the auto-fit currently also shrinks the craft when thrusters are enabled. Pinning `ortho_scale` removes that coupling too.

---

#### MBS-27 — `run_report.json` reports asserted constants, not measurements; the settings-consumption contract cannot fail **[probe]**

`MBS-RES-0001` states MBS-5b is closed because "every required setting appears in `run_report.json` as consumed." It does. It appears there because it is typed there.

`build_asset.py:488-496`:

```python
'consumedSettings': [
    'bankDegrees', 'frameSize', 'cameraPitchDegrees',
    'forwardAxis', 'upAxis', 'thrusters', 'profileScale',
],
```

This is a hardcoded literal, and it is character-for-character the `requiredConsumedSettings` list written by `write_manifest` (`pipeline.py:217-225`). `verify_required_outputs` compares one constant against the other. **The settings-consumption contract has no failure mode.** Deleting every use of `cameraPitchDegrees` from the script would not trip it.

The same applies to the two evidence booleans at `build_asset.py:499-500`:

```python
'cleanExportContainsReviewRig': False,
'neutralPoseRestoredBeforeExport': True,
```

Neither is measured. `clean_scene_for_export` *does* perform a real camera/light assertion, but the field that reports it is a constant that would still read `False` if that assertion were removed. Nothing anywhere reads `bank_root.rotation_euler` before export, so `neutralPoseRestoredBeforeExport` is an unverified claim about the single defect that motivated MBS-1.

And `tests/test_server_source.py:16` closes the loop:

```python
assert "'neutralPoseRestoredBeforeExport': True" in source
```

The test asserts that the literal is present in the file. This is the MBS-9 pattern — metadata attesting to behaviour rather than recording it — reappearing inside the very machinery built to prevent it. It matters more here than it did in v0.1.0, because the review ZIP is now the formal evidence artifact for a provider decision.

**Fix.** Make consumption observable rather than declared:

```python
class RecordingSettings(dict):
    def __init__(self, source): super().__init__(source); self.observed = set()
    def __getitem__(self, key): self.observed.add(key); return super().__getitem__(key)
```

Wrap `manifest['settings']`, and emit `sorted(settings.observed)`. For the pose, capture and write the actual values immediately before export:

```python
rotation = tuple(round(v, 9) for v in bank_root.rotation_euler)
run_report['bankRootRotationAtExport'] = rotation
if any(abs(v) > 1e-6 for v in rotation):
    raise RuntimeError(f'Neutral pose was not restored before export: {rotation}')
run_report['sceneObjectTypesAtExport'] = sorted({o.type for o in bpy.context.scene.objects})
```

Then rewrite `test_server_source.py` to assert behaviour rather than substrings.

---

#### MBS-28 — `hide_render` on the effects parent does not hide the thruster cones; they contaminate the silhouette render and the IoU **[read]**

`render_review_set:342-348` hides thrusters before the straight-down silhouette pass:

```python
if effect_root is not None:
    effect_root.hide_render = True
...
render(scene, output_dir, 'silhouette_top_master.png')
```

`effect_root` is an **Empty**. In Blender, `Object.hide_render` is per-object and **does not propagate through parenting** — only *collection* visibility inherits. The `ThrusterPreview_1/2` cone meshes are separate objects parented to `effect_root`, each with its own `hide_render = False`. Setting the flag on the parent has no effect on them.

Two consequences, both landing on the metric that MBS-2 was raised to create:

1. `silhouette_top_master.png` includes two emissive exhaust cones extending rearward. That image is the sole input to `_silhouette_iou` against the top-down authority — so the IoU is measured against a silhouette the authority does not contain, and is depressed by an amount that varies with craft depth (`exhaust_length = max(0.45, depth × 0.16)`).
2. `projected_fit_scale` skips objects where `obj.hide_render` is true — but the cones' own flag is false, so they are also included in the silhouette pass fit, shrinking the craft further.

Because thrusters default to **on** in the UI, this is the default path, not an edge case.

**Fix.** Put review-only geometry in a dedicated collection and toggle `collection.hide_render`, or set the flag on every descendant:

```python
for obj in [effect_root, *descendants(effect_root)]:
    obj.hide_render = True
```

Then add to `run_report`: `'silhouettePassExcludedObjects': [names]`, measured — which MBS-27's instrumentation would surface automatically. Worth also extending the Experiment 00 gate 3 assertion to name the thruster objects explicitly, not just cameras and lights.

---

### MEDIUM

---

#### MBS-29 — Post-processing runs before the output contract, so a missing Blender output surfaces as a raw traceback **[probe]**

`run_job:518-523` orders the steps: `run_blender` → `postprocess_outputs` → `verify_required_outputs`. But post-processing consumes the very files the contract is meant to guarantee. Probe with an empty output directory:

```
postprocess (runs first)  -> FileNotFoundError: .../output/preview_neutral_master.png
contract check (runs 2nd) -> RuntimeError: Output contract failed: missing=preview_neutral_master.png
```

The second message is the one that belongs in `job.json['error']`; the first is what the user actually gets. Split the contract: verify `RENDER_REQUIRED_OUTPUTS` immediately after Blender exits, then post-process, then verify `POSTPROCESS_REQUIRED_OUTPUTS`. The two constants are already separated at `pipeline.py:26` and `:37` — the split is available, just unused.

---

#### MBS-30 — `sanitize_imported_objects` reintroduces the MBS-7 defect at a second site **[read]**

`parent_preserve_world` is correct and `build_normalized_hierarchy` uses it properly. But `sanitize_imported_objects:76-78` deletes unsupported object types outright:

```python
for obj in list(bpy.context.scene.objects):
    if obj.type not in supported:
        bpy.data.objects.remove(obj, do_unlink=True)
```

When a removed object is an intermediate node with mesh children — a glTF hierarchy where a light or curve node sits between the root and a mesh — `bpy.data.objects.remove` clears the child's `parent` but leaves `matrix_local` intact. The child silently loses the parent's transform and jumps. This is the same failure mode MBS-7 described, at a site the fix did not cover.

It is rarer than the original, but the consequence is identical and it manifests as an implausible mesh that looks like a provider defect.

**Fix.** Before removal, re-parent the doomed object's children to its parent with world preserved (or convert unsupported nodes to Empties rather than deleting them). The general principle is worth stating in the code: *no object is ever removed or reparented without preserving the world transforms of its descendants.*

---

#### MBS-31 — Silhouette IoU is scale- and translation-invariant by construction, and its ceiling is 0.993, not 1.0 **[probe]**

`_fit_mask` independently crops each mask to its bounding box, rescales it to a 512 px canvas with a 28 px margin, and centres it. This deliberately discards absolute scale and position, leaving aspect ratio and shape as the signal.

That is a defensible metric — but it is not what a reader will assume from the name, particularly in a package where MBS-4 made scale fidelity a headline concern. As it stands, the IoU is **structurally incapable of detecting MBS-26**, because both are scale-erasing transforms.

I calibrated the ceiling by feeding a pixel-identical silhouette through the real code path:

```
IoU for a pixel-identical silhouette: 0.993436
```

The 0.66% shortfall comes from the `Image.Resampling.NEAREST` step inside `_fit_mask`. So **1.0 is unreachable, and a reviewer told "IoU 0.93" has no way to know whether that is near-perfect or mediocre.**

**Fix.** Record the metric's own properties alongside the number, in `asset.json` and in the protocol:

```json
"silhouetteIoU": { "value": 0.9312, "ceiling": 0.9934,
  "invariantTo": ["scale", "translation"], "sensitiveTo": ["aspect", "shape", "rotation"],
  "fitCanvas": 512, "fitMargin": 28, "resample": "NEAREST" }
```

Emitting the ceiling per run (by IoU-ing the authority against itself) costs one extra call and makes every future number interpretable. The `512`/`28`/`NEAREST` constants are also currently undocumented and silently determine the value.

---

#### MBS-32 — Contact sheets compare the authority and the renders at different sizes **[probe]**

`_make_review_sheet:386` fits the authority with `ImageOps.contain(authority, (tile, tile))` — scaling the whole authority *canvas*, including its transparent margin, to the tile. The render tiles are exactly `tile × tile` with the craft filling ~88% of the frame.

I generated a sheet using the bundled `samples/gunship_authority_placeholder.png` and a synthetic pixel-identical render. In the output the AUTHORITY ship is visibly smaller than the NEUTRAL and BANK ships — roughly a 25–30% mismatch driven purely by how much empty margin the authority PNG happens to have.

For a sheet whose entire purpose is side-by-side identity judgement at 64 px, that is a meaningful handicap, and it varies per authority image rather than being a fixed known offset.

**Fix.** Normalize the authority tile by its **silhouette bounding box**, exactly as `_fit_mask` already does — crop to `_alpha_mask(...).getbbox()`, then scale so its span matches the render's measured span. The helper exists; it just is not used on this path.

---

#### MBS-33 — MBS-17 has no disposition, and colour management was pinned in one place and unpinned in another **[read]**

MBS-17 (golden-image determinism) appears in no table of `MBS-RES-0001` — not P0, not P1, not "Additional closures". It is the only finding from CR-0001 without a stated disposition. Checking the code:

- `taa_render_samples` is **not set** (`grep` count: 0). EEVEE Next's sample count still comes from the scene default, so renders remain non-reproducible across Blender versions and settings.
- `view_transform = 'Standard'` is set — correct, and it avoids the AgX/Filmic trap.
- But `build_asset.py:246-249` then applies a **non-neutral grade**, inside a swallowed exception:

```python
try:
    scene.view_settings.look = 'Medium High Contrast'
except TypeError:
    pass
```

A contrast look alters every pixel of images that are about to be used for identity comparison and silhouette thresholding — and because failure is silent, whether it applies at all depends on the Blender build. That is nondeterminism introduced into exactly the artifact that must be comparable across the three pitch runs and across providers.

**Fix.** Set `scene.eevee.taa_render_samples` to a pinned value and record it in `run_report`; set `look = 'None'`; and if a graded variant is genuinely wanted for aesthetic review, emit it as a clearly-named *additional* output rather than grading the measurement inputs. Record the resolved colour-management state in `run_report` either way. Then give MBS-17 an explicit disposition in the next resolution document.

---

#### MBS-34 — The opaque-authority mask path is a pure-Python per-pixel loop with an undocumented threshold **[probe]**

`_alpha_mask` uses the alpha channel when one is present, and otherwise falls back to corner-sampled background subtraction with a nested Python loop and a hardcoded distance threshold of 28 (`pipeline.py:304-308`).

The package's own sample authority takes that path:

```
sample authority: (768, 768) alpha extrema=(255, 255) -> CORNER-SUBTRACTION fallback
_alpha_mask on 589,824 px took 0.58s
  extrapolated 4096x4096: ~17s
  extrapolated 8192x8192: ~66s
```

8192 is the accepted ceiling from `MAX_IMAGE_DIMENSION`, so a legitimately-sized authority costs a silent minute inside `postprocessing` with no progress signal. More importantly, threshold 28 is an unexplained constant that determines the silhouette: an authority whose hull is dark against a dark background will have holes punched in its mask, and the IoU will drop for reasons unrelated to the mesh.

**Fix.** Vectorize with `ImageChops.difference` + `point()` or NumPy (both dependencies are already present), make the threshold a named constant recorded in `run_report`, and emit the derived authority mask as a review output so a reviewer can see what was actually compared.

---

#### MBS-35 — `frameSize` no longer means frame size **[read]**

`clamp_int(..., 64, 128, 'frameSize')`, then `master_size = frameSize * 4` — so the field now controls master resolution (256–512 px). The actual review sizes are hardcoded `for size in (96, 64)` in `postprocess_outputs`, and the 96/64 filenames are baked into `POSTPROCESS_REQUIRED_OUTPUTS`.

So a user who sets `frameSize = 64` still gets 96 px and 64 px review images — from a 256 px master. The name now describes something it does not control, and it sits in `requiredConsumedSettings` reinforcing the impression that it drives the review size.

Rename to `masterScaleFactor` or `masterResolution`, and either promote the review sizes to declared settings or state in the UI that 96/64 are fixed by protocol.

---

#### MBS-36 — Normalization lives in the root node transform, not in vertex data **[read]**

`craft_root.matrix_world = Matrix.Scale(scale, 4) @ Matrix.Translation(-center) @ orientation` is mathematically correct — I verified the composition order centres then scales as intended. But the transform stays on the root node, and `export_scene.gltf` preserves node transforms rather than baking them.

`normalized.glb` therefore contains original-scale vertex data under a root node carrying an arbitrary scale factor (potentially very large or very small, depending on the provider's units). Consumers that flatten hierarchies, ignore root transforms, or import meshes individually will get an unnormalized asset from a file called `normalized.glb`.

Either apply transforms before export (`bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)` on the craft hierarchy) or document in the README and `asset.json` that normalization is expressed as a root node transform and must be honoured. Applying is the safer default; it also removes non-uniform-scale hazards for any downstream rigging.

---

#### MBS-37 — "Measured thruster anchors" are a bounding-box heuristic, and asset.json mixes coordinate conventions **[read]**

The README lists among the produced evidence: *"review-only emissive thruster previews and measured thruster anchors."* The implementation (`create_thrusters:206-209`) is:

```python
anchors = [
    [minimum.x + width * 0.30, minimum.y + depth * 0.08, center_z],
    [maximum.x - width * 0.30, minimum.y + depth * 0.08, center_z],
]
```

Two points placed at fixed fractions of the bounding box. No engine geometry is detected, and the count is always two — the gunship profile's identity markers specify "two separated engine housings," but a bomber ("heavy rear engines") or a drone ("single core") gets the same two anchors at the same proportions. That is a reasonable placeholder; it is not a measurement, and the README should not call it one. This is MBS-10's problem recurring at a new field.

Separately, those anchors are written into `asset.json['anchors']` as **world-space Blender units**, while `pivot` and `collision` in the same file are **normalized 0–1 image fractions**, with no units declared on either. A consumer has no way to tell them apart. Add an explicit `units` field per block, and derive anchors from mesh clustering (or from the profile's declared engine count) before describing them as measured.

---

### LOW

**MBS-38 — Test-suite weaknesses.** `tests/test_server_source.py` reads `Path('app/server.py')` relative to the **working directory**, so the suite only passes when pytest is invoked from the package root; `scripts/run_tests.command` does `cd` there, but a developer running `pytest tests/` from elsewhere gets a confusing failure. All four assertions in that file are substring greps rather than behavioural checks (see MBS-27). `test_download_traversal_is_rejected` accepts `{404, 308}` — a 308 would mean the request was *redirected*, not rejected, so the test would pass on a genuine regression; it also tests only `%2e%2e` and not the bare `..` form that was the actual v0.1.0 vulnerability. Both forms are in fact correctly rejected, so tighten the assertion to `== 404` and add the second vector.

**MBS-39 — Dead code and no linter.** Unused imports: `BinaryIO`, `ImageFont`, `date` (`app/pipeline.py`), `Any` (`app/server.py`). Unused local `histogram = mask.histogram()` (`pipeline.py:402`). Unused parameter `workspace` in `run_job`. None of these are harmful, but `requirements.txt` has no linter, and the project applies flat-config ESLint discipline on the TypeScript side — a `ruff` pin and a `scripts/lint.command` would catch this class automatically and cost nothing.

**MBS-40 — Duplicated assignments in `setup_scene`.** `render.engine` (234, 243), `film_transparent` (240, 244) and `resolution_percentage` (237, 242) are each set twice. Harmless, but it suggests the function was assembled rather than reviewed, and it is the kind of thing that hides a genuine ordering dependency later.

**MBS-41 — No concurrency cap; orphaned subprocess on shutdown.** Nothing limits simultaneous jobs, so two submissions launch two Blender processes at up to 512² each. The worker is a `daemon=True` thread, so stopping the server kills the thread but leaves the Blender child running. Add a single-job lock (or a small bounded queue) and terminate the child in a `finally`.

**MBS-42 — Silhouette overlay lacks a distinct intersection colour.** Two translucent layers are alpha-composited, so the intersection reads as a blend of blue and orange rather than a third identifiable colour. On the near-identical case I generated, the authority layer is entirely hidden beneath the render layer, which makes a perfect match and a badly-offset match harder to distinguish at a glance than they need to be. Compute the three regions explicitly — authority-only, render-only, both — and assign each a flat colour.

**MBS-43 — `job.json` read-modify-write race.** `write_job_status` reads, mutates and rewrites. The request thread writes `'queued'` while the worker thread may already be writing `'rendering'`. `_write_json`'s temp-file-and-replace makes each write atomic, but does not make the read-modify-write sequence atomic, so a status transition can be lost. Narrow in practice; a lock around the sequence closes it.

**MBS-44 — `pivot` lacks the `source` field that `collision` has.** `collision` records `'source': 'neutral_96_alpha_bounds'` and `insetFactor`; `pivot` is a bare pair with no indication that it is an alpha centroid rather than a bbox centre. Add the matching provenance field.

---

## 5. Prioritised action list

### P0 — before Experiment 00 is run

| ID | Item | Why it blocks |
|---|---|---|
| MBS-26 | Pin `ortho_scale`; demote `projected_fit_scale` to a clipping validator | Experiment 00 calibration gate 4 fails deterministically without it |
| MBS-28 | Hide thruster geometry per-object or by collection | Contaminates the silhouette render and therefore the IoU, on the default path |
| MBS-27 | Instrument real consumption and measure the export pose | The evidence artifact must record what happened, not what was intended |

### P1 — before Experiment 01

MBS-29 (contract split around post-processing), MBS-30 (preserve world transforms in `sanitize_imported_objects`), MBS-31 (record the IoU's invariants and per-run ceiling), MBS-32 (normalize the authority tile by silhouette), MBS-33 (pin sampling, drop the look, give MBS-17 a disposition), MBS-36 (bake transforms or document the node-transform contract).

### P2 — housekeeping

MBS-34 (vectorize the mask, name the threshold, emit the mask), MBS-35 (rename `frameSize`), MBS-37 (stop calling heuristic anchors measured; declare units), MBS-38 through MBS-44.

---

## 6. Assessment

v0.2.0 is a substantial and mostly successful revision. The security findings are properly closed rather than mitigated, the provenance gate is stronger than requested, the async job model is correct, and the protocol rewrite is the best document in the package.

The pattern worth naming — because it accounts for the two most serious findings — is this: **v0.2.0 built the measurement machinery and then populated it with constants.** `consumedSettings` is a literal. `neutralPoseRestoredBeforeExport` is a literal. `cleanExportContainsReviewRig` is a literal. A source-grep test asserts one of those literals is present. And the one thing that *is* computed per-job — `ortho_scale` — is computed in a way that cancels the fix it was supposed to preserve.

That is the same shape as the original MBS-9 finding, now operating one level up: instead of a feature that is configured but unimplemented, we have verification that is declared but unperformed. The closing suggestion from MBS-CR-0001 stands and is now more specific: **a value that appears in `run_report.json` should be one that was read from the running scene, not one that was typed into the source.** If every field in that file had to be produced by an observation, MBS-26, MBS-27 and MBS-28 would all have surfaced on the first fixture run instead of in review.

Recommended sequence: ship v0.2.1 with the three P0 items, re-run the suite expecting **16 passed**, then run Experiment 00 against the fallback fixture across all five profiles — gate 4 becomes the acceptance test for MBS-26, and the silhouette output becomes the acceptance test for MBS-28. Only then commit provider credits to Experiment 01.
