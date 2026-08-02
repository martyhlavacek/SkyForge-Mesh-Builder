# MBS-CR-0011 — SkyForge Mesh Builder Sidecar v0.6.0

## Independent Adversarial Code, Geometry and Release Review

**Reviewer:** Claude (independent adversarial reviewer)
**Candidate:** SkyForge Mesh Builder Sidecar v0.6.0
**Baseline:** sealed v0.5.3, cleared in MBS-CR-0010
**Review date:** 2026-07-31
**Finding namespace:** continues after MBS-84; new findings MBS-85 … MBS-95
**Verdict:** **CONDITIONAL — NOT CLEARED FOR USER TESTING**

---

## 0. Identity Gate — PASS

All eight identity assertions verified before any content was read.

| # | Assertion | Result |
|---|---|---|
| 1 | Outer ZIP SHA-256 = `10d3ca4d…32c787` | **MATCH** |
| 2 | Outer ZIP extracted | OK |
| 3–4 | `SOURCE/…v0.6.0.zip` = `c6dd2d46…1ffe61` | **MATCH** |
| 5 | Confirmed against `.sha256` sidecar | **MATCH** |
| 5 | Confirmed against `CLAUDE_REVIEW_BINDING_v0.6.0.json` | **MATCH** |
| 6 | v0.5.3 baseline = `db7d55a4…586d3` | **MATCH** |
| 7 | `sha256sum -c SHA256SUMS.txt` — 40 files | **40/40 OK** |
| 8 | Field baseline review package = `1f42d8bf…525b` | **MATCH** |

The identity gate is clean. An MBS-CR number is therefore consumed rather than an MBS-GATE.

---

## 1. Executive Assessment

v0.6.0 does what its central claim says. The flat belly and vertical extrusion walls that defined the v0.5.3 representation are **genuinely gone**, and the improvement is large, measured and reproducible: on the same field authority, combined construction-artifact fraction falls from **0.636282 to 0.017681** — a 36× reduction that I reproduced independently to the sixth decimal. Every geometry figure in every narrated report and in `FIELD_FIXTURE_COMPARISON.json` reproduced **exactly** against my own trimesh measurements. That is unusual and it is creditable.

The release is nonetheless not clearable today, for two narrow reasons and one substantive one:

- **Ruff is red** at the pinned version (one import-ordering error in a test file). The stated clearance rule is unconditional on this point.
- **Blender gates could not be executed** anywhere — not in Sol's build environment (`liveBlenderTest: false`) and not in mine.
- **The headline "independent underside" claim is not supported by measurement.** The lower surface is a near-uniform scaled mirror of the upper surface (Pearson r = 0.99989, best-fit scale k = 0.4642 ± 0.0002 across all three craft, residual 1.05–1.09%). This is a framing mismatch of the kind that has recurred across this project, not a geometry defect.

The remaining findings are real but mechanically closeable. Nothing I measured suggests the geometry path is unsound.

---

## 2. Mandated Verification Results

| # | Required check | Result |
|---|---|---|
| 1 | Exact dependency verification | **PASS** — all 9 pins exact |
| 2 | `ruff check .` | **FAIL** — 1 × I001 (MBS-85) |
| 3 | Complete pytest, zero skips | **PASS** — 90 executed / 90 passed / **0 skipped** / 0 failed / 0 errors |
| 4 | Archive hygiene + transactional sealer | **PASS** |
| 5 | Independent source diff vs sealed v0.5.3 | **PASS** |
| 6 | Controlled v0.5.3 vs v0.6.0 measurement | **PASS** |
| 7 | Independent geometry measurements | **PASS** — all reproduce exactly |
| 8 | Source/reload agreement + failure probe | **PARTIAL** — gate works; no in-suite probe (MBS-88) |
| 9 | glTF→Blender reconstruction + bounds delta | **PASS** |
| 10 | Blender neutral/banked renders + gates | **UNAVAILABLE** (MBS-95) |
| 11 | Identical alpha planform, different albedo → identical geometry | **PASS — proven** |
| 12 | No paid OpenAI transport in geometry tests | **PASS — proven** |

### 2.1 Dependencies (exact)

`Flask 3.1.1 · Werkzeug 3.1.7 · blinker 1.9.0 · Pillow 11.3.0 · numpy 2.3.5 · trimesh 4.11.1 · pytest 8.4.1 · ruff 0.15.22 · requests 2.32.3` — every pin matched exactly via `importlib.metadata`.

### 2.2 Ruff — RED

```
I001 Import block is un-sorted or un-formatted
   --> tests/test_authority_mesh.py:192:5
Found 1 error. [*] 1 fixable with the `--fix` option.
```

`BUILD_INFO.json` records `ruff_0_15_22: UNAVAILABLE_IN_CURRENT_BUILD_ENVIRONMENT`. It was available to me, and it is red. See MBS-85.

### 2.3 Pytest — zero skips confirmed

90 collected, 90 passed, **0 skipped**, 0 failed, 0 errors, 152s.
Per module: authority_mesh 11 · concept_workflow 2 · image_governance 11 · image_pricing 5 · macos_keychain_runtime 3 · openai_client 4 · pipeline 17 · release_sealing 4 · server 10 · server_source 17 · settings_store 6.

`BUILD_INFO.json` claims `executed 78 / unavailable 12` and `completePinnedPytestSuite: UNAVAILABLE`. In a correctly pinned environment the complete suite runs and passes with zero skips. The zero-skip requirement is met.

### 2.4 Independent geometry measurement — all figures reproduce

Measured directly from the shipped GLBs with trimesh, reconstructing the target frame via `GLTF_TO_BLENDER`:

| Metric | approved_gunship | field_gunship | interceptor |
|---|---:|---:|---:|
| Triangles | 83,180 | 108,440 | 88,176 |
| Vertices | 41,592 | 54,208 | 44,090 |
| Unique edges | 124,770 | 162,660 | 132,264 |
| Boundary edges | 0 | 0 | 0 |
| Non-manifold edges | 0 | 0 | 0 |
| Watertight | true | true | true |
| Winding consistent | true | true | true |
| Components | 1 | 1 | 1 |
| Euler number | 2 | −12 | 2 |
| Genus | 0 | **7** | 0 |
| Flat-belly fraction | 0.002941 | 0.010549 | 0.003344 |
| Vertical-wall fraction | 0.007098 | 0.007132 | 0.008118 |
| Combined artifact fraction | 0.010039 | 0.017681 | 0.011461 |
| Degenerate faces (area ≤ 1e-12) | 0 | 0 | 0 |
| Min face area | 6.445e-05 | 6.445e-05 | 6.445e-05 |
| Height/planform | 0.167978 | 0.168191 | 0.168782 |

**Every one of these matches the narrated report exactly.** Volume is positive on all three (outward winding). Section-thickness distributions and root-to-tip falloff also reproduce (e.g. field gunship tipToRootRatio 0.193109 vs gate ≤ 0.72).

### 2.5 Controlled v0.5.3 vs v0.6.0 — the core claim holds

Same field authority, both meshes measured by me under identical code:

| | v0.5.3 | v0.6.0 | Gate |
|---|---:|---:|---|
| Triangles | 39,460 | 108,440 | ≤ 180,000 |
| Flat-belly fraction | **0.323049** | **0.010549** | ≤ 0.18 |
| Vertical-wall fraction | **0.313233** | **0.007132** | ≤ 0.08 |
| Combined artifact fraction | **0.636282** | **0.017681** | ≤ 0.25 |
| Genus | 6 | 7 | *(ungated)* |

I confirmed by direct gate invocation that v0.5.3's values fail all three artifact gates and v0.6.0's pass. The representation change is real, not cosmetic.

### 2.6 Coordinate contract — exact

`GLTF_TO_BLENDER @ TARGET_TO_GLTF = I₄` exactly. `det = +1.0` on both (no handedness flip). Encoding verified: target (1,2,3) → glTF (1,3,−2) → Blender (1,2,3). Measured `blenderImportBoundsDelta` 2.5e-08 … 5e-08, against a 1e-05 gate. The contract is preserved and correct.

### 2.7 Seam integrity (adversarial Q2) — clean

Reconstructed every corner vertex at the 256 export grid:

| | approved | field | interceptor |
|---|---:|---:|---:|
| Boundary / interior corners | 1,180 / 19,616 | 1,474 / 25,630 | 1,374 / 20,671 |
| Min vertical thickness | 0.006000 | 0.006000 | 0.006000 |
| Count thickness ≤ 0 | **0** | **0** | **0** |
| Interior top below seam height | **0** | **0** | **0** |
| Seam / median section | 2.26% | 2.77% | 2.62% |

No self-intersection, no inversion, no lip, no pinch, no degenerate faces. The 0.006-world-unit seam removes the tall walls without introducing pathology. **Answer to Q2: yes, cleanly.**

### 2.8 Albedo independence (Q7, Q11) — proven for the alpha path

Four variants of one authority, alpha channel byte-identical, RGB varied to extremes (original / heavy orange cast / fully inverted / flat mid-grey):

```
variant        vertexSHA[:16]     faceSHA[:16]       albedoSHA[:16]     tris  genus
original       3cd549ef0fca49fa   45fbfd1a7b0dabe6   419a338084e3070a   83180 0.0
orange_cast    3cd549ef0fca49fa   45fbfd1a7b0dabe6   fece932f38de5e34   83180 0.0
inverted       3cd549ef0fca49fa   45fbfd1a7b0dabe6   94490731c5d15d25   83180 0.0
flat_grey      3cd549ef0fca49fa   45fbfd1a7b0dabe6   a1181a31b6eed6a9   83180 0.0

distinct VERTEX hashes: 1  -> geometry byte-identical
distinct FACE   hashes: 1  -> topology byte-identical
distinct ALBEDO hashes: 4  -> texture correctly preserved
```

Luminance and orange influence are fully removed from geometry while the texture remains intact. **This is a genuine closure of MBS-72 — for alpha authorities.** See MBS-89 for the opaque path.

### 2.9 No paid transport (Q12) — proven

Re-ran the 28 geometry and pipeline tests with `socket.socket.connect`, `connect_ex`, `create_connection` and `getaddrinfo` all replaced by raising stubs. **28 passed** with every outbound primitive hard-blocked. `app/authority_mesh.py` contains zero reference to OpenAI (the sole textual match is a *sample filename*). The only real transport call sites in the codebase are three `requests` calls in `app/openai_client.py`, none reachable from the geometry path.

### 2.10 Gates are not vacuous — probed

I invoked `_gate_results` and `_edge_audit` directly with adversarial inputs:

- `_edge_audit` correctly distinguishes closed (0 boundary / 0 non-manifold), open (3 boundary), and finned (1 non-manifold) topology.
- Source/reload **disagreement flips `sourceReloadEdgeAuditAgreement` to False and overall `passed` to False**. The agreement gate can fail. *(Q8 satisfied at the code level — but see MBS-88.)*
- 3 boundary edges → fail. 1 non-manifold edge → fail.
- v0.5.3-level artifact fractions → all three artifact gates fail.

The gates work. Generation also fails closed at the top level: `RuntimeError` is raised on gate failure, and I triggered this genuinely twice during probing.

### 2.11 Source diff and governance (Q9) — no weakening

Files changed outside `docs/`: `BUILD_INFO.json`, `README.md`, `MAC_SEALING_KIT_NOTICE.md`, sealing command, `app/authority_mesh.py` (383 lines), `app/server.py` (8 lines), `app/templates/index.html`, `scripts/seal_release.py` (13 lines), `scripts/setup.command`, two test files, two new samples.

**Byte-identical (zero changed lines):** `app/openai_client.py`, `app/macos_keychain.py`, `common/spend_ledger.py`, `common/image_pricing.py`, `app/image_governance.py`, `app/settings_store.py`, `app/concept_workflow.py`, `app/pipeline.py`, `common/mesh_math.py`, `profiles/craft_profiles.json`, `requirements.txt`.

`server.py` changes are the version string plus three cosmetic label strings. `seal_release.py` changes are the version, the v0.6.0 document manifest, and the temp-dir prefix. **No cost, privacy, Keychain, cache, coordinate, Blender or release guarantee is weakened.** No provider adapter, multiview, neural reconstruction, thruster, fallback, destruction or animation code is present. Prohibited scope is respected.

### 2.12 Archive hygiene and sealer — pass

The sealed candidate archive contains **no** `workspace/`, `__pycache__`, `.ruff_cache`, `.pytest_cache`, `.venv`, `.git`, `.DS_Store`, `.pyc` or `config.json` entries. The sealer stages into a `TemporaryDirectory` and publishes via a single atomic `os.replace`; `test_preflight_failure_leaves_no_release_set` covers the rollback path. All 4 sealing tests pass.

---

## 3. Dispositions — MBS-70 through MBS-75

| Finding | Sol's claim | My verdict |
|---|---|---|
| **MBS-70** asserted component count | Closed | **HONEST — verified.** `component_count = len(reloaded_glb.split(...))` genuinely reads the independently reloaded GLB; `componentCountSource` is recorded truthfully. Caveat in MBS-92; regression exposure in MBS-88. |
| **MBS-71** quantified 2.5D ceiling | Addressed | **HONEST — verified.** 0.636282 → 0.017681 reproduced exactly. Correctly worded "Addressed", not "Closed": the representation remains single-valued per planform coordinate. `GEOMETRY_ARCHITECTURE_v0.6.0.md` §37 states this limitation explicitly and accurately. |
| **MBS-72** albedo-derived geometry | Closed | **SUBSTANTIALLY HONEST, INCOMPLETE.** Proven byte-identical for alpha authorities. Not true for opaque authorities, where the mask itself is RGB-derived. See MBS-89. |
| **MBS-73** height gate not binding | Accepted | **HONEST.** Gate is 0.45; measured 0.168–0.169. Still non-binding at ~2.7× headroom, and the disposition says so plainly. |
| **MBS-74** low work grid / Python scan | Closed | **HONEST — verified.** 384 work grid, 256 export grid. I verified the separable Felzenszwalb–Huttenlocher EDT against brute force on 12 random masks: **max error 0.000e+00 — exact.** |
| **MBS-75** image-centre mirroring | Partially addressed | **HONEST.** The wording is precise: row-relative span centre *before* final bilateral stabilization. The `np.fliplr` stabilization is genuine residual image-centre mirroring and the disposition does not hide it. Magnitude quantified in MBS-93. |

**MBS-75 specifically:** the partial disposition is fair. `_row_relative_lateral_coordinate` does use per-row occupied span, but `upper = (upper + np.fliplr(upper)) * 0.5` mirrors about the image centre column. Because `_fit_authority` centres the crop bbox, this is harmless for symmetric axis-aligned craft and measurably small here (median deviation 0.06–1.15% of section thickness). It is **not** harmless in general — see MBS-93.

---

## 4. New Findings

### MBS-85 — Ruff fails at the pinned version — **HIGH**

`ruff check .` at pinned 0.15.22 returns one `I001` at `tests/test_authority_mesh.py:192`. `BUILD_INFO.json` records Ruff as unavailable in the build environment; it is available and red. Under the stated clearance rule this alone blocks user testing.

**Remedy:** `ruff check --fix .`, or hoist the two function-local imports to module scope. One-line change; re-seal required.

### MBS-86 — The underside is a scaled mirror, not an independent field — **HIGH**

`GEOMETRY_ARCHITECTURE_v0.6.0.md`: *"The top and bottom therefore are not mirrors."*
`MBS-RES-0013`: *"Independent upper/lower fields; lower surface is not constant or mirrored."*
Allowed scope: *"independent upper and lower planform fields."*

Measured, on the occupied cells of all three craft:

| | approved | field | interceptor |
|---|---:|---:|---:|
| Best-fit scale k (lower ≈ k·upper) | 0.464191 | 0.463890 | 0.464282 |
| Pearson r(upper, lower) | 0.999900 | 0.999914 | 0.999885 |
| Relative residual ‖lower − k·upper‖/‖lower‖ | **1.085%** | **1.065%** | **1.051%** |
| Camber max / median section | 3.2% | 4.0% | 3.7% |

The cause is structural, not incidental:

```python
upper       = hull * (0.44 + 0.18 * centreline)
lower_depth = hull * (0.20 + 0.09 * centreline)
```

Both consume the **same** `hull` and the **same** `centreline`. Their ratio varies only from 2.200 (centreline = 0) to 2.138 (centreline = 1) — a 2.8% span. The recovered k is constant to within 0.08% across three different craft, which demonstrates it is a **generator constant, not a craft-derived quantity**.

The geometry is not wrong and is a large improvement on a constant underside. But "independent" is not what was built. What was built is *a scaled mirror with a 3–4% camber offset and ~1% shape deviation*.

**Remedy — pick one and say which:**
1. Restate the documentation as "asymmetric two-sided section with independent upper/lower coefficients" and drop "independent fields" and "not mirrors"; or
2. Make the belly genuinely independent by giving `lower_depth` its own basis — e.g. a distinct distance exponent and a chine/keel term rather than reusing `hull` and `centreline` — and re-measure k and the residual as an acceptance criterion.

Option 1 is legitimate and cheap. Option 2 is the real feature. Either is fine; asserting option 2 while shipping option 1 is not.

### MBS-87 — Field-gunship genus 7 is threshold speckle, and genus is ungated — **HIGH**

Adversarial Q6 asked whether genus 6 → 7 reflects a real opening. It does not. Enclosed-hole counts through the resampling chain for `v060_field_gunship_authority.png`:

| Stage | Holes | Sizes (px) |
|---|---:|---|
| Raw 1024² mask | **17** | 45, 40, 26, 21, 20, 18, 16, 16, 15, 12, 12, 12, 12, 9, 9, 9, 9 |
| Work grid 384 | **16** | 7, 5, 3, 2×10, 1×3 |
| **Mesh grid 256** | **7** | 2, 2, 1, 1, 1, 1, 1 |
| Preview grid 128 | **5** | 2, 1, 1, 1, 1 |

Genus tracks the mesh-grid hole count exactly (7 holes → genus 7). The count is **monotonically resolution-dependent with no stable value**, and every surviving hole is 1–2 px. These are `corner_colour_distance_28` threshold speckle — interior pixels that happened to land within 28 units of the sampled background colour — not modelled openings. The other two craft, whose masks are clean, both measure genus 0. The v0.5.3 genus of 6 versus v0.6.0's 7 differs only in which speckles survived NEAREST downsampling.

Consequence: the shipped field-gunship GLB carries **seven spurious through-tunnels** in the hull.

Compounding this, **`ACCEPTANCE_GATES` contains no genus or Euler limit.** `_largest_component` removes disconnected foreground islands but never fills enclosed background holes, so arbitrarily many speckle tunnels pass every gate.

**Remedy (P0):**
1. Fill enclosed background holes below an area threshold in `_fit_authority`, immediately after `_largest_component` — a border flood-fill of the background, retaining only holes above a stated pixel area, would remove all 17.
2. Add `genusMax` to `ACCEPTANCE_GATES` (0 is the correct default for these craft) so speckle topology fails loudly rather than shipping.
3. Regenerate the field gunship and re-measure.

### MBS-88 — No negative-control coverage; MBS-70's closure is unprotected — **HIGH**

Item 8 of the review brief asked for a probe proving the agreement gate can fail. **The suite contains none.** I supplied one externally (§2.10) and the gate does fail correctly, so the *current* behaviour is sound. But there is no regression protection, and I demonstrated this by mutation:

| Mutation | Suite result |
|---|---|
| `edge_audits_agree = True` (hardcoded) | **11/11 passed** |
| `component_count` sourced from the OBJ instead of the reloaded GLB | **11/11 passed** |

Both mutants survive the entire geometry suite. The exact defect MBS-70 was raised about — an *asserted* rather than measured component count — could be silently reintroduced and every test would stay green, while `componentCountSource: "independent_reloaded_glb_split"` continued to be emitted.

**Remedy (P0):** add two negative-control tests — one constructing mismatched source/reload audits and asserting the gate fails, one asserting `componentCount` is provably read from the reloaded GLB (e.g. by patching the reloaded object and observing the reported value change).

### MBS-89 — `albedoInfluencesGeometry: false` is asserted unconditionally but is path-dependent — **MEDIUM**

Both `geometryMetrics.albedoInfluencesGeometry` and `source.albedoGeometryInfluence` are hardcoded `False` regardless of mask method. On the `alpha_threshold_16` path this is true and I proved it byte-identically (§2.8). On the `corner_colour_distance_28` path — which **two of the three shipped evidence craft actually use** — the mask, and therefore the entire planform, section field, thickness and topology, is derived from RGB colour distance to the sampled corner background.

Demonstrated on `v060_field_gunship_authority.png` (opaque): a low-contrast recolour of the *same craft with the same silhouette* changed the geometry so much that generation failed topology validation outright (`Independent GLB export validation rejected the generated OBJ topology`), while the report for the unmodified input still declared `albedoGeometryInfluence: False`.

This is a reporting defect, not a geometry defect — the fail-closed behaviour is correct. But an operator reading the report is told something untrue about how their asset was built.

**Remedy:** make the field conditional on `mask_method` — `False` for `alpha_threshold_16`, `True` (or `"mask_derivation_only"`) for `corner_colour_distance_28` — and state in the architecture document that albedo independence is guaranteed only for alpha-carrying authorities.

### MBS-90 — Triangle budget has no adaptive fallback; wide planforms are unbuildable — **MEDIUM**

At `MESH_GRID_SIZE = 256`, each occupied cell emits at least 4 triangles (top + bottom), so the 180,000 gate is exceeded above roughly **68.7% planform fill**. Measured fills here are 31.7% / 41.4% / 33.6%, so current craft sit at 46–60% of budget.

Verified empirically: a 92%-fill blocky planform produced **248,000 triangles** and was rejected with `triangleCountMaximum`. Failing closed is correct, but there is no adaptive path — a legitimately wide or blocky craft simply cannot be built, and the error message does not tell the operator that reducing the export grid would resolve it.

**Remedy:** select `MESH_GRID_SIZE` adaptively from measured fill (e.g. step to 192 or 160 when projected triangles exceed budget), record the chosen grid in the report, and make the failure message name fill fraction and the suggested grid.

### MBS-91 — Artifact-fraction gates are uncalibrated — **MEDIUM**

| Gate | Threshold | Measured range | Headroom |
|---|---:|---|---:|
| flatBellySurfaceFraction | 0.18 | 0.0029–0.0105 | 17–61× |
| verticalWallSurfaceFraction | 0.08 | 0.0071–0.0081 | 10–11× |
| combinedConstructionArtifactFraction | 0.25 | 0.0100–0.0177 | 14–25× |
| heightToPlanformRatio | 0.45 | 0.168–0.169 | 2.7× |
| tipToRootThicknessRatio | 0.72 | 0.193–0.232 | 3.1–3.7× |

The thresholds do discriminate v0.5.3 (0.32/0.31/0.64) from v0.6.0, which is what they were built for. But at 10–61× headroom they would not catch a ten-fold regression in construction-artifact area. This repeats the project's standing pattern of thresholds set by assertion rather than calibration — the same pattern that produced the lobe gate and IoU floor errors in the enemy pipeline.

**Remedy:** re-derive each threshold from the measured v0.6.0 distribution plus a stated margin (for example 5× the observed maximum), record the derivation in `GEOMETRY_METRICS_BASELINE_v0.6.0.md`, and treat the v0.5.3 values as the discrimination floor rather than the design point.

### MBS-92 — Split provenance between reported topology metrics — **LOW**

`mesh.componentCount` is measured from `reloaded_glb`. But `_geometry_metrics(loaded_mesh, …)` computes `components`, `eulerNumber` and `genus` from `loaded_mesh` — the intermediate OBJ. Two different meshes therefore back adjacent fields in one report under a single "measured" banner. They agree on all three craft today, but a divergence would be invisible and the genus figure does not carry the independence guarantee that `componentCount` advertises.

**Remedy:** compute `_geometry_metrics` from the reloaded GLB (transformed back to target frame), or add an explicit `geometryMetricsSource` field.

### MBS-93 — Residual image-centre mirroring is locally large and undocumented — **LOW**

Quantifying the `np.fliplr` stabilization by re-running the field construction with it disabled:

| | approved | field | interceptor |
|---|---:|---:|---:|
| Mask self-mirror IoU | 0.991632 | 0.996869 | 0.973186 |
| Median deviation (% of median section) | 0.34% | 0.06% | 1.15% |
| **Max deviation (% of median section)** | 6.52% | **55.04%** | 8.54% |

Median impact is negligible, but the field gunship shows a **55% local deviation** at its worst point — real local geometry error introduced purely by mirroring about the image centre column rather than the craft's own axis. Tolerable here because these craft are near-symmetric; a genuinely asymmetric craft would be materially distorted, and nothing currently detects that.

**Remedy:** gate on mask self-mirror IoU (reject or skip stabilization below, say, 0.95) and record the max deviation in the report.

### MBS-94 — Sealed archives are not byte-reproducible — **INFO**

`seal_release.py` sorts entries and pins compression, but does not normalise `ZipInfo.date_time`, so two seals of identical content produce different SHA-256 values. Checksum binding is per-artifact so this is not a defect, but byte-reproducibility would strengthen the ceremony at low cost.

### MBS-95 — Blender gates unexecuted in any environment — **INFO / BLOCKING BY RULE**

`BUILD_INFO.json` records `liveBlenderTest: false`. Blender is not installed in my review environment either, so the neutral and banked render gates, the Blender-side silhouette gate and the export gate could not be executed by anyone. The *emulated* glTF→Blender reconstruction is verified exactly (§2.6) and the coordinate algebra is provably correct, but that is not the same as a live Blender import.

---

## 5. Answers to the Adversarial Questions

1. **Underside genuinely independent?** **No.** Near-uniform scaled mirror, k = 0.4642 ± 0.0002, r = 0.9999, ~1% residual, ~3–4% camber. Not constant, not an identical mirror — but not independent. MBS-86.
2. **Does the 0.006 seam create degenerate/self-intersecting/non-manifold/pinched topology?** **No.** Zero inversions, zero sub-seam thicknesses, zero interior-below-seam vertices, zero degenerate faces, min face area 6.4e-05, watertight and winding-consistent on all three. Clean.
3. **384 preserves thin features; 256 stays under 180,000?** **Yes for these craft.** Area delta 384→256 is ≤0.05%; narrowest row run 7px→5px (proportionate to the 0.667 scale). Triangle counts 83k–108k. But the budget is fill-dependent and has no fallback — MBS-90.
4. **Is `componentCount` genuinely measured from the reloaded GLB?** **Yes** — verified in code and by reproduction. But unprotected against regression (MBS-88) and inconsistent with the adjacent genus provenance (MBS-92).
5. **Flat-belly and vertical-wall metrics in the correct frame with area weighting?** **Yes.** Computed on `loaded_mesh` in the target frame (+Z up), weighted by `area_faces`, 3° tolerance. I reproduced all six values exactly by independent computation.
6. **Is genus 6→7 a real opening?** **No — resampling/threshold artifact.** 17→16→7→5 holes as resolution falls; all 1–2 px at mesh grid. And genus is ungated. MBS-87.
7. **All luminance and orange influence removed from geometry, texture intact?** **Yes for alpha authorities** — proven byte-identical across four extreme recolours with texture correctly varying. **Not for opaque authorities**, where the mask is colour-derived. MBS-89.
8. **Are MBS-70…75 dispositioned honestly, especially MBS-75?** **Yes.** All six dispositions are accurate, appropriately hedged, and MBS-75's "Partially addressed" is the correct characterisation — it names the residual rather than concealing it. The one materially overstated claim sits outside that table, in the "Two-sided underside — Implemented" row and the architecture text (MBS-86).
9. **Did anything weaken v0.5.3 guarantees?** **No.** All eleven cost, privacy, Keychain, pricing, governance, settings, pipeline and mesh-math modules are byte-identical. `server.py` and `seal_release.py` changes are version and manifest only.
10. **Honestly represented as deterministic two-sided geometry, not full 3D reconstruction?** **Yes.** `GEOMETRY_ARCHITECTURE_v0.6.0.md` §37 states plainly that the model permits at most one upper and one lower surface per planform coordinate and cannot represent overhangs, undercuts, detached nacelles or overlapping volumes, and names those as the later comparison point for provider routes. That is an honest and well-drawn boundary.

---

## 6. Verdict

**CONDITIONAL — Marty may NOT begin user testing yet.**

Against the five stated clearance conditions:

| Condition | Status |
|---|---|
| Candidate identity | **GREEN** |
| Ruff at pinned version | **RED** — MBS-85 |
| Zero-skip pytest | **GREEN** — 90/90, 0 skipped |
| Independent GLB measurements | **GREEN** — all reproduce exactly |
| Blender gates | **UNAVAILABLE** — MBS-95 |

Two conditions are unmet, so clearance is withheld. I want to be clear about proportion: the geometry work in this release is sound, the central claim is true and independently confirmed, and the governance surface is untouched. The blockers are one lint error, one unavailable toolchain, and a set of honesty and coverage gaps that are cheap to close. This is close.

### P0 — required before user testing

1. **MBS-85** — fix the `I001`; re-run `ruff check .` clean at 0.15.22.
2. **MBS-95** — execute the Blender neutral and banked renders, the Blender-side silhouette gate and the export gate on a machine with Blender, and attach the outputs.
3. **MBS-87** — fill sub-threshold enclosed mask holes, add a `genusMax` gate, regenerate the field gunship, re-measure.
4. **MBS-88** — add the two negative-control tests (agreement-can-fail; componentCount-provably-from-GLB).
5. **MBS-86** — either restate the documentation to match what was built, or rebuild the belly on an independent basis. State explicitly which.

### P1 — before the next epoch

6. **MBS-89** — make the albedo-influence report field conditional on mask method.
7. **MBS-91** — recalibrate the five artifact/ratio thresholds from measured distributions with a stated margin.
8. **MBS-90** — adaptive export grid with the chosen grid recorded in the report.

### P2 — opportunistic

9. **MBS-92** — unify topology-metric provenance to the reloaded GLB.
10. **MBS-93** — gate on mask self-mirror IoU; record max mirroring deviation.
11. **MBS-94** — normalise `ZipInfo.date_time` for byte-reproducible seals.

---

## 7. Checksum Binding

| Artifact | SHA-256 |
|---|---|
| Outer review package | `10d3ca4d3b2637ef35d0e43f98031578658b0a375f4c5907f522d402ed32c787` |
| Candidate source v0.6.0 | `c6dd2d463e5f5ab39573877a89aa1325d46e7daec7b416afbe896f5eba1ffe61` |
| Baseline source v0.5.3 | `db7d55a4495bac3f338ddac5de4bca7624997be126c110384f58fc199f4586d3` |
| Field baseline review package | `1f42d8bf89fc6c5658ffb130bf3547b7be1ddd8c2d84275a901003ee6605525b` |
| approved_gunship GLB | `9b13e348daa5ac30a1fbbc2f1e4f566163fc9b7dd6f1b88ac0734343bc8f1238` |
| field_gunship GLB | `a1b5dc3026c4c181ca7ae9c5ce44e13df38dcddd0fe7652ba92b4a4dbb7ad0a5` |
| interceptor GLB | `7998022655fdec1ebd444162b00a21eb7e03cc7c9fb5c2d8b0fc1af8dd38d1f7` |

`sha256sum -c SHA256SUMS.txt` — 40/40 OK.

**Environment:** Python 3.12.3 · Flask 3.1.1 · Werkzeug 3.1.7 · blinker 1.9.0 · Pillow 11.3.0 · numpy 2.3.5 · trimesh 4.11.1 · pytest 8.4.1 · ruff 0.15.22 · requests 2.32.3 · Blender **not available**.

**Findings raised:** MBS-85 … MBS-95 (3 HIGH-blocking, 1 HIGH-coverage, 3 MEDIUM, 2 LOW, 2 INFO).
No testing was requested of Marty during this review.

*— End of MBS-CR-0011 —*
