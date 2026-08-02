# MBS-CR-0001 — Code Review: SkyForge Mesh Builder Sidecar v0.1.0

**Artifact under review:** `SkyForge_Mesh_Builder_Sidecar_v0_1_0.zip` (26 files, 25 KB)
**Author:** Sol (external)
**Reviewer:** Claude (independent audit)
**Date:** 2026-07-29
**Verdict:** **CONDITIONAL GO** — harness is structurally sound; experiment must not be run until P0 items are closed.

> **Numbering note:** This document uses the `MBS-N` finding namespace deliberately so it does not collide with the SFAS `CF-N` series (CF-1..CF-4 are currently open against Epoch 6A). It also does not consume an `SFAS-CR-####` number, since the sidecar is outside the SFAS tree. Renumber if you'd rather fold it into the main sequence.

---

## 1. Mechanical verification performed

| Check | Result |
|---|---|
| Extract, file inventory | 26 files, clean layout, no stray artifacts |
| `pytest -q` (Python 3.12.3, Flask 3.1.1) | **3 passed** in 0.03 s |
| Flask endpoints exercised via `test_client` | `/api/health`, `/api/jobs`, `/api/jobs/<id>/download` all reachable |
| Empirical probes | 4 constructed (see MBS-5, MBS-13, MBS-18) |
| Blender path | **Not executed** — no Blender in the audit sandbox. All `build_asset.py` findings are from source read and are labelled as such. |

Findings marked **[probe]** were confirmed by execution. Findings marked **[read]** are from source analysis and should be confirmed on Marty's machine before Sol spends effort on them.

---

## 2. What is good, and worth preserving

Before the findings, the parts that should not be changed:

- **The `## Boundaries` section of the README is excellent discipline.** Explicitly stating "does not modify SkyForge Studio / does not train a model / does not silently approve generated concepts / does not claim semantic part detection beyond imported object boundaries" is exactly the right posture for a quarantined sidecar. Keep this pattern for every future sidecar.
- **`EXPERIMENT_PROTOCOL.md` is written as a falsifiable experiment**, with a stated hypothesis, named pass gates, and — critically — **stop conditions**. Most tooling proposals omit the stop condition. This one names it.
- **Honesty about the fallback.** "It is not an aesthetic candidate" is the correct label for four scaled cubes, and it prevents the fallback from being mistaken for a result.
- **Content-addressed inputs.** Hashing both the authority and the mesh into the manifest is the right foundation for reproducibility.
- **Job-scoped filesystem layout** (`source/`, `output/`, `logs/`, `job.json`, `manifest.json`) with a declared `requiredOutputs` contract. The contract is not yet *enforced* (MBS-5b), but declaring it is the harder half.
- **`safe_name()` is genuinely safe** for the upload path: every path separator is collapsed to `_`, and a bare `..` is rejected downstream because its suffix is empty and fails the allowlist. I tried to break it and could not.

---

## 3. Findings

### HIGH

---

#### MBS-1 — `normalized.blend` and `normalized.glb` are saved in a **banked** pose, and contain the review rig **[read]**

`blender/build_asset.py`, `main()`, lines 62–64:

```python
render(root,out,'preview_neutral.png',0)
render(root,out,'preview_bank_left.png',-bank)
render(root,out,'preview_bank_right.png',bank)     # root.rotation_euler[1] = +18°
bpy.ops.wm.save_as_mainfile(filepath=str(out/'normalized.blend'))
bpy.ops.export_scene.gltf(filepath=str(out/'normalized.glb'), export_format='GLB', use_selection=False)
```

`render()` mutates `root.rotation_euler[1]` and never restores it. Both "normalized" outputs are therefore written with `craft_root` rolled to `+bankDegrees` (18° by default). An asset named `normalized.glb` that is not in a neutral pose is worse than no asset, because downstream consumers will trust the name.

Compounding: `use_selection=False` exports the **entire scene**, which at that point includes the orthographic camera and both area lights added by `scene_setup()`. The shipped `normalized.glb` is a review rig with a ship in it.

**Fix:** reset `root.rotation_euler = (0,0,0)` after the render sequence; export with an explicit selection or collection filter containing only `craft_root` and its descendants. Add an assertion that the exported GLB node count matches the mesh count + 1.

---

#### MBS-2 — The approved authority image is **never read** by the pipeline; the stated hypothesis is currently untestable **[probe]**

`grep -n authority blender/build_asset.py` → no matches.

The manifest records `authority.path` and `authority.sha256`, and the README describes the tool as "image-to-mesh conditioning." But the authority image is only ever hashed and copied. It is not used as a texture source, not used for scale reference, not used for silhouette comparison, and not composited into any review output.

This matters because it makes the protocol's own hypothesis unmeasurable:

> "A generated GLB conditioned by the existing Blender pipeline can preserve the approved gunship identity…"

Nothing in the pipeline conditions on the authority, and nothing measures preservation. Pass gate 1 ("Recognizable as the approved gunship in all three frames") reduces to an unaided human impression formed by opening three PNGs in separate windows and remembering what the authority looked like.

**Fix, in ascending order of effort — the first is cheap and I'd insist on it:**

1. **Contact sheet.** Emit `review_sheet.png`: authority (scaled to matched span) | neutral | bank-L | bank-R, at both review sizes, on a neutral mid-tone and on a canyon-tile sample. This is a dozen lines of Pillow and turns review from recall into comparison.
2. **Silhouette IoU.** Render one extra orthographic straight-down pass, threshold its alpha, threshold the authority's alpha, report intersection-over-union in `asset.json`. This converts gate 1 into a number you can regression-test across providers.
3. Only after (1) and (2): consider whether "conditioning" should mean anything stronger, and say so explicitly in the protocol rather than in the README prose.

---

#### MBS-3 — No 96 px or 64 px renders are produced, though the review gate requires both **[read]**

`scene_setup()` sets `resolution_x = resolution_y = frame_size * 4` and nothing downsamples. With the default `frameSize=96`, the only images produced are 384 × 384.

The UI's own experiment gate says: *"Review at native 96 px and 64 px."* `EXPERIMENT_PROTOCOL.md` says *"fixed 96 px review size."* Neither is satisfiable from the package as delivered.

This is the finding I'd fix first, because readability-at-gameplay-size **is the experiment**. A mesh that reads beautifully at 384 px and turns to mud at 64 px is a failed candidate, and the current outputs cannot reveal that.

Related: **Pillow 11.3.0 is a declared dependency and is imported nowhere in the package** (`grep -rn "PIL\|Image" app blender tests` → no matches). I assume it was added in anticipation of exactly this step. Use it: emit `preview_*_96.png` and `preview_*_64.png` alongside the 4× masters, and **document the resampling filter explicitly** — Lanczos vs. area vs. nearest is not a detail at these sizes, it's a large fraction of the perceived result. Consider emitting two filters for the first experiment and letting Marty pick.

---

#### MBS-4 — `profile.scale` is never applied; all craft classes normalize to an identical span **[read]**

`profiles/craft_profiles.json` defines per-class scale: gunship 1.0, interceptor 0.72, bomber 1.15, drone 0.55, player fighter 0.82. `normalize()` hardcodes:

```python
center=(mins+maxs)/2; span=max(maxs.x-mins.x,maxs.y-mins.y,1e-5); scale=5.5/span
```

`profile` is read exactly once in the entire Blender script — to copy `profile['id']` into `asset.json` (line 65). The scale field is inert.

Consequence: a drone and a bomber come out the same size on screen. For a vertical shmup, relative silhouette scale between classes is a primary readability channel (PDR §5.1) — the bomber *must* read as bigger than the drone before either is recognizable as itself. The one piece of per-class data in the profile is the piece being discarded.

**Fix:** `scale = (5.5 * profile['scale']) / span`, and re-derive the ortho fit so the largest class still fits the frame with bank margin (see MBS-15).

---

#### MBS-5 — Path traversal in the download endpoint, and no verification of the output contract **[probe]**

**5a — traversal.** `app/server.py:50-56`:

```python
job_root = WORKSPACE / job_id
if not job_root.is_dir(): return jsonify(...),404
archive = package_job(JobPaths(job_root, ...))
return send_file(archive, as_attachment=True)
```

Confirmed by probe:

```
GET /api/jobs/../download      -> 200
GET /api/jobs/%2e%2e/download  -> 200
```

The 200 response served a 44 KB ZIP containing the **entire package root** — all app source, all `profiles/`, and critically `workspace/` in full, i.e. every prior job's uploaded authority images and meshes, manifests, and logs. It also wrote that ZIP to disk as `workspace/.._review_package.zip` as a side effect of an unauthenticated GET.

Two further wrinkles worth knowing:
- Deeper traversal (`..%2f..%2fetc`) returns 404, because Werkzeug decodes `%2F` before routing and the `<string>` converter rejects slashes. So the reach is **one level**, not arbitrary. I'm stating that plainly rather than inflating the severity.
- Because the produced archive includes `workspace/`, and the archive is *written into* `workspace/`, repeated calls nest each prior archive inside the next. Archive size grows on every invocation.

Severity is High rather than Critical because the service binds `127.0.0.1` and the reach is bounded — but it should not survive to v0.2.0. **Fix:** resolve and containment-check before use:

```python
job_root = (WORKSPACE / job_id).resolve()
if not job_root.is_relative_to(WORKSPACE.resolve()) or not job_root.is_dir():
    return jsonify({'ok': False, 'error': 'Job not found'}), 404
```

Additionally, validate `job_id` against the known job-id shape (`^[A-Za-z0-9._-]+-[0-9a-f]{8}$`), and write archives outside the directory being archived.

**5b — unverified output contract.** `write_manifest()` declares six `requiredOutputs`. Nothing ever checks that they exist. `status` flips to `'rendered'` purely on Blender's exit code, and `package_job()` runs unconditionally — so a partial Blender run that returns 0 produces a ZIP labelled "rendered" with missing renders, and a run with no Blender at all produces a "review package" containing no renders whatsoever.

This is the same shape as the recurring SFAS finding: **the contract is declared at one layer and enforced at none.** Assert the six outputs exist and are non-empty before packaging; fail the job otherwise.

---

#### MBS-6 — Arbitrary executable invocation via a form field, with no CSRF protection **[read]**

`blenderPath` arrives from the HTML form and becomes `argv[0]` of a `subprocess.run` with no validation:

```python
blender = request.form.get('blenderPath','').strip()
if blender: run_blender(Path(blender), ROOT, job, manifest)
```

There is no CSRF token and no origin check. A `multipart/form-data` POST is a CORS "simple request," so any web page Marty visits while the sidecar is running can submit this form cross-origin. The attacker cannot read the response, but the side effect executes: an arbitrary local binary of their choosing, invoked with partially attacker-influenced `--manifest` / `--job-root` paths.

For a tool whose install instructions are "double-click these four `.command` files," I'd treat this as worth closing now rather than in v0.2.

**Fix:** take the Blender path from a config file or environment variable rather than a form field; validate it exists, is a regular file, and is executable; check `Sec-Fetch-Site: same-origin` (or add a CSRF token) on all mutating routes.

---

### MEDIUM

---

#### MBS-7 — Reparenting mesh leaves discards existing parent transforms **[read]**

`normalize()` collects `mesh_objects()` — MESH-type objects only — and assigns `o.parent = root` for each. Direct `.parent` assignment leaves `matrix_parent_inverse` as identity, so each object's local matrix is now interpreted relative to `craft_root` instead of its former parent.

For a flat scene this is correct (and it is correct for `fallback_ship()`). But the glTF importer routinely produces **hierarchies** — a root node with transformed child nodes, often with non-identity rotations from the exporter's axis conversion. For any such mesh, every object whose world position derives from a parent node transform will jump. The failure is silent and looks exactly like a bad generation.

Given that hierarchical output is common from Hunyuan3D / TRELLIS / Meshy, this is likely to fire on the first real experiment.

**Fix:** either apply transforms recursively before normalizing (`bpy.ops.object.transform_apply` after selecting all, with hierarchy flattened), or parent the existing scene *roots* rather than the mesh leaves, or set `o.matrix_parent_inverse = root.matrix_world.inverted()` and preserve `matrix_world` explicitly. Add a test mesh with a two-level hierarchy to the samples directory so this stays covered.

---

#### MBS-8 — No orientation normalization; the stop condition can wrongly reject a viable provider **[read]**

There is no step that determines or corrects the mesh's forward axis or up axis. `render()` banks around **Y**, which is correct for `fallback_ship()` (built with forward = +Y), and usually correct for glTF (the importer maps glTF −Z forward to Blender +Y). It is **not** guaranteed for OBJ or FBX, both of which are in `ALLOWED_MESH`, and it is not guaranteed for generator output derived from a single top-down image, where the inferred orientation is frequently arbitrary.

The methodological risk is what concerns me more than the bug. `EXPERIMENT_PROTOCOL.md` says:

> "Reject the provider route when repeated outputs require remodelling, not cleanup…"

Pass gates 3 and 4 (unstable pivot, clipping, texture swimming under bank) will fail loudly and repeatedly if the craft is banking around the wrong axis — and the protocol's stop condition will attribute that to the provider. **The experiment as currently designed can produce a confident false negative and eliminate a good provider for a defect in our own harness.**

**Fix before running Experiment 01:** add an explicit orientation step — either a manifest-declared `forwardAxis` / `upAxis` per job, or PCA on the vertex cloud to find the long axis with a human confirmation step. Then add to the protocol an explicit instruction: *any gate-3 or gate-4 failure must be re-tested after manual orientation correction before it counts toward the stop condition.*

---

#### MBS-9 — `thrusters` and `destruction` are recorded but unimplemented — silent no-op **[probe]**

`grep -n "settings\[" blender/build_asset.py` returns exactly two lines: `frameSize` and `bankDegrees`. The other two settings are collected by the UI, validated, written into the manifest, packaged into the review ZIP — and never read.

The UI checkbox reads "Add restrained emissive thrusters" and is **checked by default**. It does nothing. `material()` even accepts an `emission` parameter, and is only ever called without it. `destruction` reaches the manifest and does not reach `asset.json`.

This is the same failure class as the SFAS **CF-1 erosion no-op**: a feature that is plumbed end-to-end through configuration and metadata while the implementation is absent, so the artifact *documents* behaviour that did not occur. It is worth naming as a recurring pattern rather than a one-off, because the review ZIP is evidence — and evidence that asserts `"thrusters": true` about a render with no thrusters is actively misleading.

**Fix:** implement, or remove from the UI and the manifest, or mark explicitly as `"thrusters": {"requested": true, "implemented": false}`. Any of the three is acceptable; the current state is not.

---

#### MBS-10 — `asset.json` presents hardcoded constants as measured data **[read]**

```python
'pivot':[0.5,0.5], 'anchors':{}, 'collision':{'type':'ellipse','rx':0.34,'ry':0.42}
```

None of these are derived from the mesh. Every craft, of every class, at every scale, gets `rx=0.34, ry=0.42`. A downstream consumer reading `asset.json` has no way to know these are placeholders — and per PDR §8.2 and the collision-category work in Epoch 2, hitbox geometry is gameplay-critical.

**Fix:** derive `collision` from the normalized bounding box (with a documented inset factor, since a shmup hitbox should be smaller than the silhouette); derive `pivot` from the actual render framing; and until `anchors` means something, emit `"anchors": null` rather than `{}` so its absence is legible.

---

#### MBS-11 — No generator provenance or licensing metadata **[read]**

The manifest records the mesh's filename and SHA-256, but not which provider produced it, under what terms, from what input, or whether it is approved for distribution.

This is a direct gap against the project's own standard. The level-editor addendum §21 specifies an asset provenance record with `sourceType`, `creator`, `license`, `generationModel`, `generationDate`, and `approvedForDistribution`, and states "the build should warn when distribution approval is missing." §13 goes further on treating source licensing as a primary design constraint.

It matters concretely here: Hunyuan3D, TRELLIS, and Meshy have materially different terms regarding commercial use and rights in outputs, and those terms change. A review package that identifies a mesh only by hash cannot answer "may we ship this?" six months from now.

**Fix:** add a required `generator` block to the manifest — `provider`, `providerVersion`, `license`, `licenseUrl`, `retrievedDate`, `inputAuthoritySha256`, `approvedForDistribution: false` — and refuse to build without it. This is the finding I'd rank highest among the Mediums, because it is cheap now and expensive later.

---

#### MBS-12 — Blocking 900-second subprocess inside the request handler **[read]**

`run_blender` calls `subprocess.run(..., timeout=900)` synchronously in the POST handler, on Flask's single-threaded development server. Consequences:

- The UI shows "Building…" with no progress for up to fifteen minutes, and browsers will generally give up first.
- `/api/health` is unresponsive for the duration, so there is no way to tell a working job from a hung one.
- Logs are written *after* `subprocess.run` returns. On `TimeoutExpired` the exception propagates before either log file is written, so **the logs from a hung Blender — the single most diagnostically valuable artifact — are the ones guaranteed to be lost.**

**Fix:** run the job on a background thread, persist status transitions into `job.json`, add `GET /api/jobs/<id>` for polling, and stream Blender's stdout/stderr to the log files incrementally with `Popen` so a timeout still yields partial logs. Wrap the timeout path in `try/finally` at minimum.

---

#### MBS-13 — No server-side clamping of numeric settings **[probe]**

The HTML declares `min`/`max` on `bankDegrees` and `frameSize`; the server applies neither. Probe:

```
POST /api/jobs  frameSize=99999  ->  200 {"status":"prepared"}
manifest settings: {"bankDegrees": 18.0, "frameSize": 99999, ...}
```

That manifest, handed to Blender, requests a 399 996 × 399 996 render — roughly 640 GB of framebuffer. The job will consume the full 900 s timeout and take the machine's memory with it.

`bankDegrees=abc` yields a 400 with `could not convert string to float: 'abc'` — functional, but the parse should be deliberate rather than incidental.

**Fix:** clamp server-side to the declared ranges, reject non-numeric input with a field-named message, and add a hard resolution ceiling independent of `frameSize`.

---

#### MBS-14 — Blender API and version fragility, with no version guard **[read]**

Three version-sensitive constructs, no documented minimum version, and no runtime check:

| Construct | Constraint |
|---|---|
| `sc.render.engine='BLENDER_EEVEE_NEXT'` | Blender ≥ 4.2 only |
| `bs.inputs['Emission Color']` | 4.x naming; 3.x is `'Emission'` |
| `m.node_tree.nodes.get('Principled BSDF')` | Lookup by **name**, which varies by version and is localised in some builds |

The README tells the user to point at `/Applications/Blender.app/…` with no version stated. A user on 4.1 gets an opaque traceback in a log file they have to go find.

**Fix:** assert `bpy.app.version >= (4, 2)` at the top of `main()` with an explicit message; find the BSDF by `node.type == 'BSDF_PRINCIPLED'` rather than by name; state the supported Blender range in the README and in `requirements.txt` as a comment.

---

#### MBS-15 — Frame fit ignores Z extent and bank widening **[read]**

`span` is computed from X and Y only, fitted to 5.5 units against `ortho_scale=7.2` — about 76% frame width at neutral. Two ways that clips:

- The camera sits at 36° pitch, so the mesh's **Z** extent projects into screen Y. A tall craft (antenna, dorsal fin, raised cockpit) can exceed the vertical frame while X/Y fit comfortably.
- Rolling ±18° about the long axis widens the projected silhouette. A wide-winged craft that just fits at neutral can clip at bank — and clipping at bank is indistinguishable, in the output PNG, from pass gate 3's "clipping" defect.

**Fix:** compute the fit from projected bounds evaluated at all three bank angles and take the maximum, including Z; add an explicit margin constant; assert the final projected bounds sit inside the frame and fail the job with a clear message if not.

---

#### MBS-16 — 36° camera pitch against a top-down authority: needs justification **[read]**

```python
bpy.ops.object.camera_add(location=(0,-8,11), rotation=(math.radians(36),0,0))
```

That is a 36° tilt off vertical — a distinctly three-quarter view, showing a substantial amount of the craft's front and rear faces. The authority is specified as a **top-down** image, and the reference benchmarks (Tyrian 2000, Raptor) use essentially straight-down sprites with tilt suggested by paint rather than by camera.

Two consequences: silhouette comparison against a top-down authority (MBS-2) is geometrically inconsistent at 36°, and the resulting look may simply not match the established canyon-tileset perspective.

I don't think this is necessarily wrong — a modest tilt reads well for banking, and banking is the point of the experiment. But it is a significant art-direction decision currently expressed as an unlabelled constant inside a render function.

**Ask for Sol:** state the intended pitch and the reasoning against the reference benchmarks, move it into `settings` in the manifest so it is per-job and recorded, and for Experiment 01 render at two or three pitches (say 0°, 20°, 36°) so Marty can judge rather than infer. This also directly serves the open question from the last session about whether the graphics match Raptor's quality — perspective consistency between ships and terrain is a large part of that answer.

---

### LOW / INFO

---

**MBS-17 — Golden-image non-determinism.** EEVEE Next's TAA render sample count is unpinned. If these renders are ever to serve as regression baselines — and given the SFAS golden-image work, they will be — pin `scene.eevee.taa_render_samples`, and pin the colour management view transform (the default has changed between Blender versions and will silently shift every pixel).

**MBS-18 — Empty error strings on several failure paths [probe].** An unknown `profileId` reaches `next(p for p in PROFILES if ...)`, raising `StopIteration`, caught by the blanket handler, and `str(StopIteration())` is `''`. Confirmed: `400 {"error": "", "ok": false}` → the UI renders "Failed: ". Use explicit lookup with a named error. Separately, the blanket `except Exception` returns 400 for genuine server faults and leaks absolute filesystem paths into the response body.

**MBS-19 — Test coverage is thin, and one test asserts the wrong thing.** Three tests, all on trivial helpers. Nothing covers `write_manifest`, `save_upload`'s rejection path, any endpoint, or any Blender logic. `test_safe_name` asserts `safe_name('../bad name.glb') == '.._bad_name.glb'` — it pins the *output string* rather than the *safety property*. Assert the property instead: no path separators survive, and the result never escapes its destination directory. The normalize/fit math should be extracted into a `bpy`-free module so it is testable without Blender — that single refactor would make MBS-4, MBS-7, and MBS-15 all regression-coverable.

**MBS-20 — Unbounded workspace growth.** Every POST calls `package_job` whether or not there is anything to package; every download **re-zips** rather than reusing the archive; nothing is ever cleaned up; each job retains source, output, and a full ZIP copy of both. With a 250 MB upload ceiling, a handful of jobs will run to gigabytes. Add retention (keep N most recent), reuse existing archives, and skip packaging for `prepared` jobs.

**MBS-21 — Three new schema namespaces with no counterpart in the main repo.** `skyforge.mesh-job.v1`, `skyforge.mesh-builder.v1`, and `skyforge.asset.v1` have no Zod schemas, no relationship to the `.sfassetpack` / `.sfworkspace` family, and no declared migration path. This is the two-implementation divergence risk in its earliest and cheapest-to-fix form. Either declare the sidecar explicitly pre-schema and *not* integratable until a CR defines the mapping, or align `asset.json` with the existing asset-pack shape now.

**MBS-22 — `PROFILES` is read once at import**, so editing `craft_profiles.json` silently has no effect until restart. Reload per request, or log the load and its mtime.

**MBS-23 — No image content validation.** `save_upload` checks the extension only; a probe with eight PNG magic bytes followed by ASCII zeroes was accepted as an authority image. With Pillow already a dependency, `Image.open(...).verify()` plus a dimension sanity check costs two lines.

**MBS-24 — Pass gate 5 is unmeasured.** "Human cleanup remains below 20 minutes" cannot be evaluated from anything in the package, and nothing records it. Add a `review.json` template to the job so the reviewer records a verdict per gate, the cleanup timer, and free-text notes — then the experiment produces data rather than an impression, and Experiment 02 has a baseline. Given the project's CR/RES convention, Experiment 01 should terminate in a RES document.

**MBS-25 — `clear()` robustness.** `bpy.ops.object.select_all` / `object.delete` depend on context and mode, and can fail in background mode depending on the startup file. `bpy.ops.wm.read_factory_settings(use_empty=True)` is the deterministic form.

---

## 4. Prioritised action list

### P0 — before Experiment 01 is run at all

| ID | Item | Why it blocks |
|---|---|---|
| MBS-3 | Emit true 96 px and 64 px renders | Readability at gameplay size *is* the experiment |
| MBS-2 | Contact sheet with the authority; silhouette IoU | Gate 1 is otherwise unmeasurable |
| MBS-8 | Orientation normalization + protocol amendment | Prevents a false negative that eliminates a good provider |
| MBS-1 | Neutral-pose reset; export only the craft | The primary deliverable is currently mis-posed |
| MBS-4 | Apply `profile.scale` | Cross-class silhouette scale is a readability channel |
| MBS-9 | Resolve the `thrusters` / `destruction` no-op | The review ZIP must not attest to behaviour that did not occur |
| MBS-5b | Verify `requiredOutputs` before packaging | Enforce the contract at the transactional core, not the label |

### P1 — before v0.2.0 ships

MBS-5a (traversal containment), MBS-6 (Blender path out of the form + CSRF), MBS-7 (hierarchy transforms), MBS-11 (generator provenance — do this now, it is cheap now), MBS-12 (background job + streamed logs), MBS-13 (clamping), MBS-14 (version guard), MBS-15 (bank-aware fit), MBS-10 (derive collision and pivot).

### P2 — housekeeping

MBS-16 (document and parameterise pitch; render a pitch sweep for Experiment 01), MBS-17 (pin sampling and colour management), MBS-19 (extract `bpy`-free math module and test it), MBS-20 (retention), MBS-21 (schema alignment decision), MBS-22, MBS-23, MBS-24 (`review.json` + RES doc), MBS-25.

---

## 5. Note on the experiment design itself

Separate from the code: the protocol conflates two questions that should be answered in sequence.

1. **Does our harness faithfully render a known-good mesh?**
2. **Do generated meshes preserve approved identity?**

Right now Experiment 01 answers them simultaneously, which means any failure is ambiguous — and MBS-1, -4, -7, -8, and -15 are each sufficient to fail a gate on their own. A false verdict is worse than no verdict, because the protocol's stop condition converts it into a permanent decision about a provider.

**Recommendation:** insert **Experiment 00**, using a hand-authored mesh of the approved gunship (or, failing that, the fallback craft with the pass gates rewritten to suit it) as a harness calibration run. Its only purpose is to establish that the pipeline preserves identity for a mesh we already trust. Gate on Experiment 00 before spending provider credits, and only then run Experiment 01 with the provider as the sole variable.

That also gives you the golden-image baseline the SFAS work will want later, and it's a good deal cheaper than the alternative — which is discovering after three provider evaluations that the harness was rolling ships about the wrong axis the whole time.

---

## 6. Summary for Sol

The scaffolding is good and the discipline around boundaries, stop conditions, and content hashing is better than most first drafts — the parts in §2 should be treated as settled and reused.

The gap is that this is currently a **rendering** harness that has been documented as a **conditioning and evaluation** harness. The authority image is hashed but unread, the profile scale is loaded but unapplied, two of four settings are recorded but unimplemented, the declared output contract is unverified, and the review sizes the gate names are never produced. Close those five and the instrument can answer its own hypothesis. Until then, running Experiment 01 risks a confident wrong answer about a provider, which is the one outcome the stop condition makes expensive to reverse.

One structural suggestion for the next revision: the recurring theme across MBS-2, -4, -5b, -9, and -10 is metadata asserting things the pipeline did not do. A single end-of-run validation pass — assert every declared output exists, every recorded setting was consumed, and every derived field was actually derived — would have caught all five, and is maybe forty lines. Worth building before the feature surface grows.
