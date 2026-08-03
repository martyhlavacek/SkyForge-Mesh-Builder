# MBS-CR-0025 — SkyForge Mesh Builder v0.8.0 Multivolume Alpha 1: Remediation Re-Review

**Review identifier:** MBS-CR-0025
**Date:** 3 August 2026
**Reviewer:** Claude (independent adversarial reviewer)

| Item | Value |
|---|---|
| Repository | `martyhlavacek/SkyForge-Mesh-Builder` |
| Pull request | #2 (draft) |
| Branch | `feature/v0.8.0-multivolume-alpha1` |
| Prior reviewed commit | `faef403b79c358827dc0a48252917fca40d22de4` (MBS-CR-0024) |
| Remediation candidate | `c5531e37bd2a379e4714e9f4e9904ed149b652c7` |
| Accepted baseline | `d38dd5d1638eae0942929a4ed568edb048220894` (tag `v0.7.1-accepted-baseline`) |
| Producer binding | 303 files / `60e2502434b31d5cc9a8f6006df6ab5eab578bdceec219839162f189b1ca44d9` |
| Import Probe binding | 64 files / `883510570c572ada2166019b356bfbefd3e7053c5074553d1c1dde1234d74ba7` |
| Evidence ZIP | `a49869762bcbb1811694122c9d64af2eee554dd290ab846fbcd272b1b1fa7a3f` |

---

## 6. Executive verdict

> ## **ACCEPT**

All nine findings — **MBS-165 through MBS-173 — are CLOSED**. Every gate that previously asserted
now measures, and I falsified each replacement independently rather than reading the tests. The
attachment measurement correctly separated all six mutation cases I constructed; band counts are
genuinely clustered from reloaded GLB geometry; the legacy gate result is propagated; topology is
computed post-reload; the historical Import Probe control fails loudly when the baseline object is
absent; and the documentation now describes placement accurately.

No regression was introduced. All thirteen legacy and governance files remain byte-identical to
the accepted v0.7.1 archive, both bindings reproduce exactly, output is byte-deterministic across
clean runs, and the diff touches nothing outside `geometry_v2`, its recipes, its tests, CI and
documentation.

**Visual inspection was completed** and the geometry materially demonstrates the intended path
toward MBS-151 through MBS-154 — which remain open, as they must.

Three new findings are raised (**MBS-177 Minor, MBS-178/179 Observations**). None blocks user
testing or merge; MBS-177 is an evidence-packaging defect worth correcting at the next
opportunity.

**The exact candidate `c5531e37…9b652c7` may advance to controlled visual/user testing and to
merge.** I did not merge, tag, release, make paid calls, or conduct user testing, and I did not
modify the repository. **MBS-136 remains open against a real provider; no paid-provider work is
authorized.**

---

## 7. Scope and method

Fresh public clone into an empty directory, detached checkout at the exact remediation commit,
both diffs inspected, and every practical gate re-run independently. The implementer's completion
report was treated as claim throughout. Per the instruction, I did not re-review the architecture
from first principles; I did re-verify the properties MBS-CR-0024 relied on, to confirm no
regression.

**Evidence classification:**

- **Independently reproduced:** all bindings and provenance (§8); Ruff, both suites, focused
  suite, all three fixtures, determinism, both Import Probe controls (§9); the complete diff and
  legacy byte-identity (§10); every MBS-165–173 disposition (§11–19); my own six-case attachment
  mutation matrix, band-clustering inspection, and IoU decomposition (§20).
- **Inspected but not reproduced:** the GitHub Actions runs — I read `GITHUB_GATE_RESULTS.md`,
  which cites push run `30836770796` and pull-request run `30836772352` with Producer and Import
  Probe PASS for the exact commit, but I have no direct GitHub API access and could not open those
  runs. Their substance is nonetheless covered by my own local re-execution.
- **Could not be verified:** the `.sha256` sidecar for the evidence ZIP was not uploaded; I
  verified the ZIP against the digest stated in the review request instead, and both agree.
  Blender-dependent behaviour remains unverifiable in my environment.

**Recorded deviation:** Python 3.11 is unavailable to me; I used clean from-contract-only Python
3.12 environments. `requirements.txt` is byte-identical to the accepted v0.7.1 contract, so no new
dependency was introduced. SciPy is absent from both environments and Flask is absent from the
Import Probe environment.

---

## 8. Provenance and evidence-package verification

| Check | Result |
|---|---|
| PR #2 head | `c5531e37bd2a379e4714e9f4e9904ed149b652c7` — **exact match** |
| Branch resolves to same commit | **match** |
| Tag `v0.7.1-accepted-baseline` | → `d38dd5d1638eae0942929a4ed568edb048220894` — **exact match** |
| Prior head `faef403…` is ancestor | **yes** |
| Baseline `d38dd5d…` is ancestor | **yes** |
| Working tree | **clean** — 0 modified or untracked |
| Evidence ZIP SHA-256 | `a4986976…1fa7a3f` — **match** |
| Evidence `SHA256SUMS.txt` | **106 of 106 verify** |
| Producer binding | **verified: True**, 303, `60e25024…b1ca44d9` |
| Import Probe binding | **verified: True**, 64, `88351057…34d74ba7` |

The evidence package contains no untracked conflict copies; the twenty externally synchronised
files described in the report are absent from both the candidate tree and the package, and both
bindings recompute to the declared values from the committed tree alone — so neither binding
depends on them.

---

## 9. Commands executed and exact results

| Command | Result | Claimed |
|---|---|---|
| Producer `ruff check .` | **All checks passed** | PASS ✔ |
| Producer `pytest -q` | **269 passed, 0 skipped, 0 failed, 0 errors** (348 warnings) | 269/0 ✔ |
| Focused `tests/test_geometry_v2.py` | **25 passed, 0 skipped** | 25/0 ✔ |
| Import Probe `ruff check .` | **All checks passed** | PASS ✔ |
| Import Probe `pytest -q` | **39 passed, 0 skipped** | 39/0 ✔ |
| Producer binding verification | 303 / `60e25024…` | ✔ |
| Import Probe binding verification | 64 / `88351057…` | ✔ |
| `verify_import_probe_baseline.py` (valid tag) | *"Import Probe matches historical baseline"*, exit 0 | PASS ✔ |
| `verify_import_probe_baseline.py` (absent object) | **`CalledProcessError`, non-zero exit** | — |
| Three fixture generations | all gates passed | ✔ |
| Determinism, second clean directory | **byte-identical** across GLB, clay GLB, registry, report, post-reload topology | ✔ |

---

## 10. Diff and regression assessment

**Diff, prior head → remediation candidate:** 13 modified, 1 added, 534 insertions, 117 deletions,
in a single commit `c5531e3 fix: remediate Alpha 1 evidence gates`. Changes confined to
`geometry_v2` (`assembly.py`, `evidence.py`, `metrics.py`, `recipes.py`), the recipe JSON and
schema, the experiment script, the new `scripts/verify_import_probe_baseline.py`, the test module,
`PRODUCER_SOURCE_BINDING.json`, `.github/workflows/ci.yml`, and three documents.

**Diff, accepted baseline → candidate:** grep for `authority_mesh`, `build_asset`, `import-probe/`,
`BASELINE_LOCK`, `app/server`, `app/pipeline`, `app/providers`, `app/vmp` returns **nothing**.

**Legacy and governance byte-identity vs the accepted v0.7.1 archive — all 13 identical:**
`app/authority_mesh.py`, `blender/build_asset.py`, `app/macos_keychain.py`, `app/openai_client.py`,
`app/image_governance.py`, `app/settings_store.py`, `app/concept_workflow.py`,
`common/image_pricing.py`, `common/spend_ledger.py`, `common/mesh_math.py`,
`profiles/craft_profiles.json`, `pyproject.toml`, `requirements.txt`.

Legacy v0.7.1 generation, accepted base-shell identity, deterministic hashes, unsupported-profile
fail-closed behaviour, recipe schema safety, production isolation, paid-provider authorization,
the accepted tag and Import Probe source are therefore **unchanged by construction**, not by
assertion.

---

## 11. MBS-165 disposition — **CLOSED**

`metrics.semantic_height_bands` now clusters measured component peaks:
`bandCount` is `len(clusters)`, derived from `mesh.bounds[1,2]` of each geometry, with an explicit
deterministic rule (sort by peak, start a new cluster when the gap ≥ `minimumSeparation`). No
hardcoded band count remains anywhere in the evidence path.

**Authoritative values come from reloaded GLB geometry** — `assembly.py:209` calls
`semantic_height_bands(reload_audit["targetMeshes"], …)`, so `measurementSource:
"independently reloaded GLB geometry bounds in target XYZ"` is truthful.

**The bands are meaningful, not one-per-component.** Gunship: 9 geometries → **6 bands**, with
mirrored pairs correctly clustering together:

```
band 0  belly                          [-0.0931]
band 1  weapon_left, weapon_right      [ 0.4401, 0.4603]
band 2  engine_left, engine_right      [ 0.5338, 0.5421]
band 3  base_shell                     [ 0.5902]
band 4  fuselage                       [ 0.8449]
band 5  cockpit_left, cockpit_right    [ 1.2543, 1.2738]
```

Interceptor: 7 geometries → **4 bands**, with `engine_left`, `engine_right` and `base_shell`
correctly merging into one band. That merge is itself evidence the clustering is real rather than
cosmetic.

**Collapse fails the gate.** The candidate's
`test_collapsed_height_peaks_fail_measured_band_gate` exercises the real path, and the gate is now
`ordered and bandCount >= minimumRequiredBandCount` where both operands are measured or
recipe-declared rather than constant. A recipe cannot pass by merely declaring three groups —
`ordered` requires each group-peak separation to be ≥ the threshold, measured from geometry.

The 0.025 threshold is in world units on the governed grid and is recipe-declared and published as
`clusteringSeparationThreshold`; realised separations are 0.2235–0.2547, roughly 9–10× the
threshold.

## 12. MBS-166 disposition — **CLOSED**

`gate_results(... legacy_gates_passed)` takes the value as a parameter and publishes
`"baseShellOriginalGates": legacy_gates_passed`. The report block now records
`"allOriginalGatesPassed": legacy_gates_passed`, plus `reportPath` (relative, via
`legacy.report_path.relative_to(output_dir)` — safe, no absolute path leakage) and `reportSha256`
computed from the actual report bytes.

A grep for residual hardcoded truth values in the evidence path
(`= True`, `: True,` excluding `check=True`/`sort_keys=True`) returns **nothing**.

Fail-closed behaviour is belt-and-braces: `generate_multivolume_experiment` raises before any
placement when the nested legacy report fails, so a false value cannot reach the report in
production; and `test_nested_legacy_false_gate_is_propagated_not_hardcoded` proves the gate would
publish `False` and fail if it did.

## 13. MBS-167 disposition — **CLOSED**
## 14. MBS-168 disposition — **CLOSED**

`metrics.attachment_metrics(base_mesh, component_mesh)` measures each component vertex against the
local two-sided base-shell envelope (min/max Z of the 32 XY-nearest base vertices), yielding
embedded fraction, exposed fraction, maximum and representative protrusion, nearest shell-vertex
distance, and the burial/detachment booleans. **The base shell now participates**, which was the
specific MBS-168 defect. No value derives from `attachmentPenetration` or any recipe constant —
I confirmed by reading the data flow and by mutation.

**My independent mutation matrix** (`cockpit_left`, gunship, base shell from the nested legacy GLB):

| Case | embedded | exposed | buried | detached | VALID |
|---|---:|---:|---|---|---|
| A. unmodified component | 0.130 | 0.870 | false | false | **true** |
| B. shrunk and sunk inside the shell | 1.000 | 0.000 | **true** | false | false |
| C. floating 3.0 above | 0.000 | 1.000 | false | **true** | false |
| D. tangent-only, just above the surface | 0.000 | 1.000 | false | **true** | false |
| E. moved far outside the silhouette | 0.000 | 1.000 | false | **true** | false |
| F. moved into an unrelated shell region | 0.000 | 1.000 | false | **true** | false |

All six classify correctly, including the two cases most likely to produce false positives —
tangent-only contact and lateral displacement outside the silhouette. The gates
`measuredEmbeddedAndExposedAttachment` and `noBuriedOrDetachedComponents` consume these measured
values and are therefore genuinely falsifiable.

**Residual noted as MBS-178 (Observation):** the acceptance floors are permissive —
`minimumEmbeddedFraction` and `minimumExposedFraction` are both **0.01**, so a component with only
1 % of vertices embedded would pass. Realised values are far above (0.130 embedded / 0.870 exposed
for `cockpit_left`), so nothing marginal is being admitted today, but the floor does not constrain
much. The method is also a local-envelope approximation using vertex sampling rather than true
solid containment; for the strongly non-convex two-sided shell here it behaved correctly in all six
mutations, but it would be less reliable for a component spanning a concave region or a very thin
shell section. Not blocking.

## 15. MBS-169 disposition — **CLOSED**

`identity_metrics` now publishes a full `iouDecomposition`: `baseOnlyIoU`, `componentsOnlyIoU`,
`assembledIoU`, `assembledMinusBaseIoU`, component projection pixel count, inside/beyond counts and
fractions, and an explicit `normalization` string naming the 384×384 work grid. I recomputed each
value independently and all three fixtures reproduce exactly:

| Fixture | base-only | components-only | assembled | Δ | inside base |
|---|---:|---:|---:|---:|---:|
| approved gunship | 0.981433 | 0.265989 | 0.977487 | **−0.003946** | 98.4871 % |
| interceptor | 0.978337 | 0.238258 | 0.978337 | **0.000000** | 100.0000 % |
| user-test gunship | 0.984308 | 0.239628 | 0.982889 | **−0.001419** | 99.3929 % |

The gate is now `silhouetteIoUDegradationBudget: assembledMinusBaseIoU >= -0.005`, retaining
`assembledSilhouetteFloor >= 0.94` separately for silhouette preservation. This is the correct
split: the delta constrains degradation, the floor constrains absolute silhouette, and neither is
presented as semantic evidence. The gunship's realised −0.003946 sits at 79 % of the −0.005 budget,
which is tight but explicit and published.

`test_misplaced_component_fails_iou_decomposition_gate` translates real component meshes by 2.0 and
re-runs `identity_metrics`, asserting the delta breaches the budget — a real measurement path.

**On whether a positive delta could conceal bad placement:** it could, in principle — the delta
gate is silhouette-only by design. That is precisely why it must not be read as semantic evidence,
and the documentation does not do so. Semantic correctness rests on the attachment, burial and
height-band gates, which are now independently measured.

## 16. MBS-170 disposition — **CLOSED**

`_reload_audit` loads the exported GLB as a scene, transforms each geometry by `GLTF_TO_BLENDER`,
and computes `topology_record(name, mesh)` **from those reloaded meshes** — watertightness, winding
consistency, boundary and non-manifold edge counts, finite coordinates and degenerate-face counts.
It also reports `componentCountBefore/After`, `geometryNamesAfter`, `geometryNamesMatch`,
`coordinateBoundsDelta` and `topologyPassed`. Pre-export records remain separately in
`component_record`, and a `post_reload_topology.json` artefact is emitted.

Name matching is by sorted set comparison, so ordering cannot mask a missing or duplicated
component. `test_post_reload_topology_rejects_corrupt_geometry` builds a genuinely corrupt GLB
(a face removed), exports it, and asserts `topologyPassed is False` with
`boundaryEdgeCount > 0`, then asserts a renamed expectation fails `geometryNamesMatch` — real
export/reload paths, not dictionary edits. Coordinate bounds delta remains 5.2e-08.

## 17. MBS-171 disposition — **CLOSED**

`recipes.load_recipe` now validates an explicit `heightBandModel` contract and raises the named
`HeightBandContractError` when `groups` is not exactly `{shell, body, semanticPeak}` or references
unknown component names — before any geometry work or partial evidence. The opaque `max()` failure
is gone.

Importantly, group membership is **declared by component name in the recipe**, not hardcoded in
code, so the previous literal matching on `fuselage`/`engine_*`/`cockpit*`/`weapon_*` no longer
constrains future recipes. A recipe may name its components freely provided it assigns them to the
three required groups.

## 18. MBS-172 disposition — **CLOSED**

`docs/architecture/V0.8.0_MULTIVOLUME_ALPHA1.md` now states: authority images provide silhouette
extents and occupied-row-span constraints; recipes provide semantic identities and approximate
normalized positions; *"Alpha 1 does not detect cockpit, engine, weapon, or belly features directly
from pixels"*; *"Row-span fitting constrains placement but does not infer semantic landmarks"*; and
RGB is used only for planar texture projection. This is accurate against the code I read. I found
no remaining overstatement in the architecture, remediation-plan or evidence documents.

## 19. MBS-173 disposition — **CLOSED**

Both controls now exist and I exercised both:

1. **Historical.** `scripts/verify_import_probe_baseline.py` runs `git cat-file -e <baseline>^{commit}`
   with `check=True` — so a **missing baseline object raises `CalledProcessError` and does not
   silently succeed**, which I confirmed by passing a nonexistent SHA — then
   `git diff --exit-code <baseline> -- import-probe`. My own run against the real tag printed
   *"Import Probe matches historical baseline"* and exited 0.
2. **Content.** `test_import_probe_content_binding_rejects_mutation` plus the probe's own
   `verify_binding` against the producer-held digest constant.

`.github/workflows/ci.yml` sets `fetch-depth: 0` on **both** jobs, and the producer job invokes the
historical script (line 39). The MBS-CR-0024 concern — that probe source, binding JSON and producer
constant could be changed together — is now covered, because the historical Git comparison would
fail regardless of what those three files say.

**Residual noted as MBS-179 (Observation):** the baseline is passed as the mutable tag
`v0.7.1-accepted-baseline` rather than the immutable commit SHA. If the tag were ever moved, the
historical check would compare against the new target and still pass. The tag currently resolves
correctly and `BASELINE_LOCK.json` records the commit, so this is a hardening point, not a defect.

---

## 20. Mutation-test assessment

The candidate contains meaningful tests for all ten required cases, and they exercise real
measurement paths rather than mutating report dictionaries after generation:

| Required case | Test | Real path? |
|---|---|---|
| collapsed semantic bands | `test_collapsed_height_peaks_fail_measured_band_gate` | yes |
| false nested legacy gate | `test_nested_legacy_false_gate_is_propagated_not_hardcoded` | parameter-level; real source verified separately |
| fully buried component | `test_attachment_measurement_rejects_buried_detached_and_tangent_components` | yes — real mesh transforms |
| detached component | same | yes |
| tangent-only component | same | yes |
| excessive silhouette degradation | `test_misplaced_component_fails_iou_decomposition_gate` | yes — real translation + re-measure |
| corrupted reloaded topology | `test_post_reload_topology_rejects_corrupt_geometry` | yes — real GLB export/reload |
| corrupted reloaded name/count | same | yes |
| missing semantic group | `test_missing_height_semantic_group_has_named_error` | yes |
| historical probe mismatch | `test_import_probe_historical_diff_gate_rejects_mutation` | yes — real temp repository |
| content-binding mismatch | `test_import_probe_content_binding_rejects_mutation` | yes |
| zero-area faces | `test_topology_record_rejects_zero_area_faces` | yes |

I did not rely on these: the six-case attachment matrix, the band-collapse behaviour, the IoU
decomposition and the historical-control failure mode in §11–19 are my own independent
constructions, and they agree with the candidate's tests.

---

## 21. Fixture and visual-evidence assessment

**Visual inspection was completed.** Files inspected:
`fixtures/approved_gunship/multivolume_preview_top.png`,
`multivolume_preview_side.png`, `attachment_exposure_diagnostic.png`, and
`fixtures/interceptor/multivolume_preview_top.png`. The package contains 54 PNGs across the three
fixtures, all covered by the verified `SHA256SUMS.txt`.

**Approved gunship, clay top view.** The grey v0.7.1 planform is clearly distinguishable from the
coloured semantic volumes. Orange fuselage runs along the centreline; two blue cockpit ellipsoids
sit side by side forward of centre — a credible split-canopy reading, which speaks directly to the
"lost split-canopy character" limitation; two yellow weapon boxes align with the forward prongs;
two red engine capsules sit laterally, inboard of the large grey wing nacelles.

**Approved gunship, side view.** The most informative image. The base shell's thin flattened profile
is plainly visible — MBS-150/151 are visibly unaddressed, exactly as declared. Against it: the
orange fuselage forms a genuine dorsal spine; the blue cockpit is a prominent bubble standing well
proud of the shell; the purple belly is unmistakably a separate underside volume; the yellow weapon
box has real extent; the red engine capsule is mostly embedded and protrudes only modestly.

**Interceptor, clay top view.** Notably stronger. The base shell reads as a swept delta fighter with
tail. The single blue cockpit sits just aft of the nose; two yellow weapons bracket the centreline
at the nose like cannons; two red engine capsules flank the rear fuselage where a twin-engine
fighter's engines would actually be.

**Assessment against the required questions:**

- **Cockpits read as cockpit volumes** — yes, in both profiles, prominently.
- **Engine capsules read as housings** — **partially**. On the interceptor the placement is
  convincing. On the gunship the capsules sit inboard of the visually obvious nacelles and protrude
  little, so they read more as bulges than housings. This is the recipe-led limitation (MBS-172)
  showing in practice, and it is why MBS-152 must stay open.
- **Weapons have meaningful three-dimensional extent** — yes, though still plainly axis-aligned
  boxes.
- **The gunship belly reads as an underside volume** — yes, clearly.
- **Components appear attached rather than floating** — yes, consistent with the measured
  embedded/exposed fractions.
- **Severe seams, z-fighting or implausible silhouettes** — none visible at these view scales.
  Interpenetration is present by design and the intersections are plausible; the flat-shaded clay
  renders would not reveal shading artefacts, so this assessment is bounded.

**The geometry materially demonstrates the intended path toward MBS-151 through MBS-154.**
None of those findings is closed by this remediation, and none should be.

---

## 22. Findings table

| ID | Severity | Area | Blocks |
|---|---|---|---|
| MBS-177 | Minor | `attachment_exposure_diagnostic.png` duplicates the side view | nothing |
| MBS-178 | Observation | Attachment acceptance floors are 1 %; vertex/local-envelope method | nothing |
| MBS-179 | Observation | Historical baseline passed as a mutable tag, not a commit SHA | nothing |

**MBS-177 — Minor — the attachment/exposure diagnostic contains no attachment or exposure
annotation.**
*Affected:* `fixtures/*/attachment_exposure_diagnostic.png` in the evidence package;
`mesh-builder/app/geometry_v2/assembly.py` preview generation.
*Evidence:* `sha256sum *.png` in `fixtures/approved_gunship/` shows
`attachment_exposure_diagnostic.png` and `multivolume_preview_side.png` share hash
`a5be46dbe1a2f802…` — they are byte-identical.
*Why it matters:* the review request lists an attachment/exposure diagnostic as a distinct visual
artefact, and a reviewer could take a differently-named file as independent corroboration when it
is a copy. The numeric attachment evidence is present and correct in
`multivolume_generation_report.json`, so this is a packaging and labelling defect, not a
measurement failure.
*Remediation:* either render a genuinely distinct diagnostic (for example, colouring each component
by exposed-vertex fraction or annotating measured protrusion), or drop the duplicate and reference
the side view.
*Blocks:* nothing — not user testing, merge, tag or release.

**MBS-178 — Observation — attachment acceptance floors are permissive.**
*Affected:* `mesh-builder/app/geometry_v2/metrics.py`, `ATTACHMENT_THRESHOLDS`
(`minimumEmbeddedFraction: 0.01`, `minimumExposedFraction: 0.01`, `surfaceTolerance: 1e-05`,
`xyNeighbourCount: 32`).
*Evidence:* a component with 1 % embedded vertices satisfies
`validEmbeddedAndExposedAttachment`; realised values are 0.130/0.870.
*Why it matters:* the gate is real and falsifiable, but its floor admits marginal contact. The
method is also a vertex-sampled local-envelope approximation rather than solid containment, so
concave or very thin shell regions are a theoretical weak spot — none of my six mutations exposed
one.
*Remediation (optional):* raise the floors toward realised values with margin, or add a measured
intersection-volume check in Alpha 2.
*Blocks:* nothing.

**MBS-179 — Observation — historical baseline is a mutable tag.**
*Affected:* `.github/workflows/ci.yml` line 39; `mesh-builder/scripts/verify_import_probe_baseline.py`.
*Evidence:* `--baseline v0.7.1-accepted-baseline` is passed as a tag name.
*Why it matters:* moving the tag would move the comparison target while the check still passes.
`BASELINE_LOCK.json` records the commit, and the tag currently resolves correctly.
*Remediation (optional):* pass `d38dd5d1638eae0942929a4ed568edb048220894`, or assert the tag
resolves to it before comparing.
*Blocks:* nothing.

---

## 23. Required changes

**None blocking.** MBS-177 should be corrected at the next convenient commit; MBS-178 and MBS-179
are hardening suggestions for Alpha 2. No change is required before user testing or merge.

---

## 24. Residual risks

- **MBS-150 remains open** — perimeter terracing and ribbed edge walls are visibly unaddressed in
  the side view, exactly as declared. Alpha 2 smooth-shell/contour-loft work.
- **MBS-151 through MBS-154 remain open** as candidate-addressed. MBS-152 is the weakest of the
  four on visual evidence: gunship engine capsules read as bulges rather than housings.
- **Overlapping watertight components without boolean union** — unchanged from MBS-CR-0024 and
  accurately declared in the report's `limitations`. Downstream risks (z-fighting, doubled
  surfaces, AO and shadow artefacts, mass-property double counting, non-manifold export input)
  remain bounded to the Alpha 1 diagnostic context.
- **The delta gate is silhouette-only** and must never be cited as semantic evidence. The current
  documentation does not do so; future reports should preserve that discipline.
- **Not assessed:** Blender import/export behaviour; shading, AO and seam quality under real
  rendering; the GitHub Actions runs themselves.
- **MBS-136 remains open** against a real provider.

---

## 25. Final verdict

> ## **ACCEPT**

MBS-165 through MBS-173 are all **CLOSED**. The gates that previously asserted now measure, and I
falsified each replacement independently — six attachment mutation cases classified correctly, band
counts genuinely clustered from reloaded geometry, legacy propagation confirmed, post-reload
topology confirmed post-reload, and the historical binding confirmed to fail loudly on a missing
baseline object. All reported numbers reproduce exactly. No regression: legacy and governance files
are byte-identical, both bindings verify, and output is byte-deterministic.

Visual inspection was completed and the geometry materially demonstrates the intended path toward
MBS-151 through MBS-154, which remain open.

**The exact candidate `c5531e37bd2a379e4714e9f4e9904ed149b652c7` may advance to controlled
visual/user testing and to merge**, subject to the standing project controls. I performed no merge,
tag, release, paid call or user testing, and made no repository modification.

**MBS-136 remains OPEN against a real provider and no paid-provider work is authorized.**
MBS-150 through MBS-154, MBS-158 and MBS-159 remain open.

Finding numbering continues from **MBS-180**.
