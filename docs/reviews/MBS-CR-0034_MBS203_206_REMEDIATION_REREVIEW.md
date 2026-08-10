# MBS-CR-0034 — MBS-203–206 Cross-View Gate Remediation Re-Review

**Reviewer role:** Independent adversarial reviewer
**Repository:** `martyhlavacek/SkyForge-Mesh-Builder`

| Binding | Value |
|---|---|
| **Candidate SHA reviewed** | `2c641084ea3c19e0406b1fe865179c408334bb67` |
| **Parent SHA** | `3e72f6e18343430074e5e334bcadf73177e9779c` |
| **Cumulative base** | `7b1f213857ce641ba1bb0f24458ca8e04217a6f5` |
| **Evidence SHA-256 verified** | `705638a9bda840f6d2b7a000c44742649c4fd782712059b9b11818d13ab668cb` |
| **Accepted fallback** | `v0.7.1-accepted-baseline` → `d38dd5d1638eae0942929a4ed568edb048220894` |

**VERDICT: ACCEPT**

**MBS-203 CLOSED · MBS-204 CLOSED · MBS-205 CLOSED · MBS-206 CLOSED**
**MBS-196 CLOSED · MBS-197 CLOSED**
**MBS-195 OPEN · MBS-136 OPEN · MBS-198–202 OPEN · MBS-207 not implemented (as required)**

New findings: **MBS-208 (MINOR)**, **MBS-209 (MINOR)** — neither blocks merge.

---

## 1. Evidence identity and deterministic build

| Artefact | Expected | Computed | Result |
|---|---|---|---|
| Evidence ZIP | `705638a9…3ab668cb` | identical | **MATCH** |
| `.sha256` sidecar | matches ZIP | — | **MATCH** |
| Second build ZIP | — | **byte-identical to first** | **DETERMINISTIC** |

The two supplied archives are byte-for-byte identical, independently substantiating the
deterministic-generation claim rather than merely asserting it. Internal `SHA256_MANIFEST.json`:
**33 of 33 entries verified**; nothing unlisted on disk, nothing listed but absent.

## 2. Source reconstruction and binding reproduction (items 4–6)

Candidate `2c641084…` is **not pushed**, as stated. Following the method accepted in MBS-CR-0033, the
candidate was reconstructed and then *proven*, not inferred:

1. Fresh tree reset to cumulative base `7b1f2138…`.
2. `cumulative_diff.patch` applied with `git apply` — **clean, no fuzz, no rejects**.
3. Rebuilt through the repository's own `common/source_binding.py:build_binding`.

```
PRODUCER rebuilt from reconstructed tree : 328  f63d2dd2e7622c21e9ace9f788e2fbffe17dda8d83a66c9b4ff43e0c54bbf756
PRODUCER declared in candidate           : 328  f63d2dd2…4bbf756
PRODUCER expected by request             : 328  f63d2dd2…4bbf756
per-file records identical               : True
IMPORT PROBE declared / recomputed       : 64   883510570c572ada2166019b356bfbefd3e7053c5074553d1c1dde1234d74ba7  (unchanged)
```

The Producer binding is a function of all 328 in-scope files, so reproducing it from base + diff is
cryptographic proof the reconstructed tree **is** the candidate tree. **Not REVIEW BLOCKED.** All
findings below come from executing the real candidate.

**Change scope verified against the MBS-CR-0033 candidate.** Exactly seven files differ, matching the
declared list. Critically, `bundle.py` is **byte-identical** to the previously accepted candidate, as
are `authorization.py`, `provider.py`, and `test_pilot_ui.py` — the architecture MBS-CR-0033 accepted
was not touched.

## 3. Independent test execution (item 7)

| Gate | Reported | My result |
|---|---|---|
| Producer Ruff | PASS | **PASS** |
| Complete Producer pytest | 438 passed, 0 skipped | **438** (417 + 21), **0 skipped** |
| Focused reconstruction/bundle/pilot/cross-view | 149 passed, 0 skipped | **149 passed** |
| Real rejected bundle | FAIL, 1,290,626 / 1,282,108 / 1,543,409 | **exact reproduction** |

Full-suite execution again required splitting around `tests/test_authority_mesh.py` (~147 s of trimesh
work) — the known environmental slowness recorded since MBS-CR-0030, not a defect.

## 4. MBS-203 — adversarial analysis (item 8)

**Implementation.** Two changes in `_mask_for_threshold` / `_bbox_record`:

```python
if low == high:
    raise CrossViewError("Uniform authority image cannot produce a valid silhouette")
...
if left == 0 and top == 0 and right == image.width and bottom == image.height:
    raise CrossViewError(f"Threshold {threshold} produced a degenerate full-canvas foreground")
```

**Executed matrix — every uniform polarity and mode refused:**

| Input | Result |
|---|---|
| uniform black | **REFUSED** — uniform |
| uniform mid-grey (128) | **REFUSED** — uniform |
| uniform white | **REFUSED** — uniform |
| uniform 200 | **REFUSED** — uniform |
| uniform `L`-mode (64) | **REFUSED** — uniform |
| uniform alpha = 0 (fully transparent) | **REFUSED** — empty foreground |
| uniform alpha = 128 (full-canvas opaque) | **REFUSED** — degenerate full-canvas |

**The exact attack that succeeded under MBS-CR-0033** — three visually-blank images with genuinely
distinct bytes, which previously built a bundle at 0 ppm and earned
`measured_orthographic_cross_view_consistency_pass` — is now **REFUSED at build**:
`Uniform authority image cannot produce a valid silhouette`. It cannot produce a silhouette record,
cannot pass consistency, cannot earn the declaration, and cannot construct an approvable bundle.

**False-positive check — the guard does not over-reject.** Valid synthetic geometry passes at 0 ppm,
and a deliberately tight-framed valid silhouette (2 px margin) also passes. The real rejected MBS-195
images still measure correctly rather than being caught by the new guards.

**Residual, raised as MBS-208.** The full-canvas guard tests the bounding box for *exact* canvas
equality, with no foreground-coverage ceiling. A deliberately crafted image that is uniform except a
one-pixel border therefore yields a near-full-canvas silhouette that passes:

```
alpha uniform + 1px transparent border  -> PASS (0 ppm)
luminance uniform + 1px dark border     -> PASS (0 ppm)
```

This requires deliberate construction; it is not a natural export failure, and the realistic failure
mode MBS-203 described is fully closed. **MBS-203's stated remediation — "refuse when low == high
regardless of polarity, and add a positive foreground-plausibility guard … reject when the silhouette
occupies the entire canvas bounding box" — was implemented exactly as specified.**

**MBS-203: CLOSED.**

## 5. MBS-204 — adversarial analysis (item 9)

I read the whole document, not only the revised heading, looking for stale contradictions further
down — which was the specific failure mode last time.

| Required statement | Present? |
|---|---|
| Scaffold = **LATER / CONTINGENCY** | **YES** — it is the section heading |
| Not the next implementation | **YES** — "records a contingency architecture only" |
| Authorizes no scaffold implementation | **YES** — stated twice, opening and closing |
| Track S is the preferred next empirical direction | **YES** — its own section |
| Track S uses one approved 3/4 beauty reference | **YES** |
| Existing Meshy multi-image endpoint with `N=1` | **YES**, explicitly |
| Approved TOP is an independent validation target | **YES** — "not a second reconstruction input for the first experiment" |
| Second view requires separate evidence/authorization | **YES** |
| Scaffold reconsideration requires empirical justification | **YES** — "only if provider evidence demonstrates a need" |
| MBS-195 remains OPEN | **YES** |
| Abandoning Track M ⇒ SUPERSEDED BY SCOPE, not CLOSED | **YES**, explicitly — "it must not be marked CLOSED on that basis" |
| No provider work authorized | **YES** — closing sentence |

**No stale contradictory statements found.** The previously offending framing ("freezes the
architecture of the next experiment", "## Next experiment", "The experiment will create") is gone;
the eleven technical requirements are correctly re-scoped under the conditional "If authorized in a
later task, it would…". The document's sound technical content — that independent image-model
generations cannot establish multi-view geometry — is preserved.

**MBS-204: CLOSED.**

## 6. MBS-205 — adversarial analysis (item 10)

**Implementation.** `_filename_tokens` now applies acronym-boundary, camelCase, and letter/digit
boundary insertion, then splits on the general class `[^A-Za-z0-9]+` with case folding.

**All seven required refusals confirmed:**

| Filename (role `top`) | Result |
|---|---|
| `01_front_canonical.png` | **REFUSE** |
| `FRONT-VIEW.png` | **REFUSE** |
| `render(front).png` | **REFUSE** |
| `authority+front.png` | **REFUSE** |
| `right,front.png` | **REFUSE** |
| `authorityFrontView.png` | **REFUSE** |
| `01front.png` | **REFUSE** |

Additional refusals I probed that are also correct: `front2.png`, `XMLFrontParser.png` (acronym
boundary), `a.front.b.png`, `front___right.png`.

**False-positive hunt — none found.** All correctly accepted: `frontier_concept.png`,
`authority_top.png`, `ChatGPT Image Aug 10.png`, `beauty_reference.png`, `upfront.png`,
`confront.png`, `rightful_heir.png`, `topology_scan.png`, `stoptheclock.png`, `copyright.png`,
`frontage.png`. This matters as much as the refusals — an over-eager matcher would block legitimate
imports, and it does not.

**One residual false negative, raised as MBS-209.** An ALL-CAPS role token immediately followed by
lower case is not split, because the acronym rule `([A-Z]+)([A-Z][a-z])` requires an uppercase
character before the lowercase run:

```
TOPview.png   role=front   -> ACCEPTED   (should refuse)
```

`authorityFrontView.png` is caught only because a lowercase→uppercase boundary exists. `TOPview.png`
is a plausible filename, so this is worth fixing, but it is outside MBS-205's stated scope — every
gap MBS-205 enumerated is closed.

**MBS-205: CLOSED.**

## 7. MBS-206 — adversarial analysis (item 11)

**Implementation.** The ambiguous fields are renamed and a provenance field is added:

| Old | New |
|---|---|
| `representativeThreshold` | `fixedThresholdExemplarThreshold` |
| `perViewBoundingBoxes` | `fixedThresholdExemplarBoundingBoxes` |
| `perViewCenterOffsetsPpm` | `fixedThresholdExemplarCenterOffsetsPpm` |
| — | `headlineMetricSource: "integer_median_of_thresholdSamples.aspectMismatchPpm"` |

**Executed against the real rejected bundle:**

```
per-threshold samples : [1284037, 1282108, 1289950, 1291303, 1473988, 1543409]
median recomputed     : 1,290,626   == measuredAspectMismatchPpm   ✓ reproducible
exemplar threshold    : 24
exemplar recomputed   : 1,289,950   == that threshold's sample     ✓ reproducible
old ambiguous names   : REMOVED
all six samples       : retained
```

Every requirement is met: the headline median is reproducible from the complete ensemble; the
exemplar is separately reproducible and correctly identified with its threshold; the two can no
longer be mistaken for the same statistic; no threshold information was discarded. The schema
requires all four new fields and pins `fixedThresholdExemplarThreshold` to `24` and
`headlineMetricSource` to its constant.

**Deep-equality coverage confirmed by probe:** tampering with `fixedThresholdExemplarThreshold` and
refreshing `bundleDigest` is **DETECTED** — `validate_bundle`'s whole-record equality automatically
covers the renamed structure.

**MBS-206: CLOSED.**

## 8. Regression / bypass assessment (item 12)

Executed against the candidate; every property MBS-CR-0033 accepted is preserved:

| Property | Result |
|---|---|
| Exact 150,000 ppm boundary | **PRESERVED** — 150,000 → PASS; 153,333 → FAIL |
| Integer-only aspect comparison | **PRESERVED** — no floats introduced |
| All-six-threshold requirement | **PRESERVED** — `[8,16,24,40,60,80]`, 6 samples |
| Failure on any invalid threshold | **PRESERVED** — raises out of the whole measurement |
| Reload-time pixel remeasurement | **PRESERVED** — `bundle.py` byte-identical |
| Deep measurement-record equality | **PRESERVED**, and now covers the new fields |
| Camera-declaration binding | **DETECTED** on reversion |
| Forged PASS-record refusal | **DETECTED** — forged bundle with recomputed digest still fails |
| Authority-image mutation detection | **DETECTED** |
| Inconsistent set refused at build | **REFUSED** |
| Strict TOP/FRONT/RIGHT invariants | **PRESERVED** — `VIEW_ORDER` and role/hash checks unchanged |
| No alternate validation bypass | **CONFIRMED** — no new entry points |
| No relaxation for single-image input | **CONFIRMED** — no `SingleViewReconstructionInputV1`; the pre-existing `single_view_source` provenance value is unchanged and remains non-approvable |
| **MBS-207 formula unchanged** | **CONFIRMED** — `abs(lhs - rhs) * 1_000_000 // rhs` byte-identical; tolerance constants unchanged |

**No new bypass was introduced.** The two changes are strictly additive refusals plus field renames.

## 9. v0.7.1 production isolation (item 13)

`v0.7.1-accepted-baseline` still dereferences to `d38dd5d1638eae0942929a4ed568edb048220894`.
Compared against that tag, `app/server.py`, `app/templates/index.html`, `app/pipeline.py`,
`app/bootstrap.py`, and `app/macos_keychain.py` are **byte-identical**. The candidate diff touches no
production surface. **No experimental reconstruction change leaked into the accepted production
route.**

**Preserved rejected evidence:** the MBS-195 workspace files remain byte-identical to the originals I
retained at MBS-CR-0031 — TOP `7009a2b6…`, FRONT `ff3d6931…`, RIGHT `d787043b…`, plus the bundle
JSON, TaskLog, and contact sheet. Rejected evidence was preserved, not repaired.

## 10. Findings

### MBS-208 — MINOR — No foreground-coverage ceiling; near-full-canvas silhouettes still pass

The degenerate guard tests only for *exact* canvas-equal bounding boxes. A crafted image that is
uniform except a one-pixel border produces a silhouette covering ~99.6% of the canvas and passes at
0 ppm (verified for both the alpha and luminance paths). This is defence-in-depth rather than a live
hole: it requires deliberate construction, the realistic blank-export failure is closed, and a human
approver reviewing the contact sheet would see it immediately.

**Remediation.** Add a stated maximum foreground-coverage ratio (and/or a minimum background margin)
alongside the existing full-canvas check, with a regression test built from the one-pixel-border
construction. **Does not block merge.**

### MBS-209 — MINOR — Tokenizer misses ALL-CAPS role tokens followed by lower case

`TOPview.png` imported as `front` is accepted, because `([A-Z]+)([A-Z][a-z])` requires an uppercase
character preceding the lowercase run. `authorityFrontView.png` is caught only via the
lowercase→uppercase boundary.

**Remediation.** Add a boundary rule for an uppercase run followed directly by lowercase (e.g. split
`([A-Z]{2,})(?=[a-z])`), being careful not to regress the accepted cases above, and add `TOPview.png`,
`FRONTview.png`, and `RIGHTside.png` to the filename matrix. **Does not block merge.**

## 11. Explicit dispositions

| Finding | Disposition |
|---|---|
| **MBS-203** | **CLOSED** — uniform inputs fail closed in every polarity, mode, and alpha representation; the exact prior attack is refused; no false positives on valid silhouettes. |
| **MBS-204** | **CLOSED** — LATER/CONTINGENCY throughout; every required statement present; no stale contradiction anywhere in the document. |
| **MBS-205** | **CLOSED** — all seven required refusals confirmed; general separators, camelCase, acronym and digit boundaries handled; no false positives. |
| **MBS-206** | **CLOSED** — headline and exemplar independently reproducible and unambiguously distinguished; no threshold data discarded; schema and deep equality cover the new structure. |
| **MBS-196** | **CLOSED.** The gate measures rather than asserts, with an integer scale-invariant identity, deterministic six-threshold ensemble, pixel-derived centring, derived and digest-bound camera declaration, reload-time remeasurement, and proven resistance to forged records, digest refresh, declaration reversion, and image substitution. It reproduces the real MBS-195 failure to the exact ppm across two independent methods. The one hole MBS-CR-0033 found in it — MBS-203 — is now closed, which was my stated precondition. |
| **MBS-197** | **CLOSED.** Exact role-token matching with comprehensive boundary handling; the real `01_front_canonical.png` case refused; legitimate names unaffected. MBS-205, my stated precondition, is closed. MBS-209 is a new residual, not a reopening. |
| **MBS-195** | **REMAINS OPEN.** This candidate creates no replacement coherent human-approved bundle. The rejected set is preserved byte-identical and still measures FAIL at 1,290,626 ppm. No synthetic fixture closes it. |
| **MBS-136** | **REMAINS OPEN.** No real provider correspondence was exercised. Still the standing prerequisite for any paid provider operation. |
| **MBS-198–202** | **REMAIN OPEN** — Track S prerequisites (abort branch, cost model, success-criteria specification, pre-registration, quarantine denylist), entirely outside this candidate. |
| **MBS-207** | **NOT IMPLEMENTED, as required.** The asymmetric normalisation `abs(lhs-rhs) * 1_000_000 // rhs` is byte-identical to the reviewed candidate. Remains an observation. |
| **MBS-208, MBS-209** | **NEW, OPEN.** Both MINOR; neither blocks merge. |

## 12. Verdict and merge suitability

**VERDICT: ACCEPT.**

Both MAJOR findings and both MINOR findings from MBS-CR-0033 are genuinely remediated, verified by
execution against the proven candidate rather than by reading the summary. The fixes are additive
refusals and field renames; nothing MBS-CR-0033 accepted was weakened, and no bypass was introduced.

**Candidate `2c641084ea3c19e0406b1fe865179c408334bb67` is suitable to merge before beginning the
separate Track S implementation.** Merging it first is in fact the correct order: the measured
cross-view gate is a prerequisite for any future multiview bundle regardless of Track S's outcome,
and landing it now prevents the rejected-bundle class of defect from recurring while attention moves
to single-view work. MBS-208 and MBS-209 should be scheduled but need not gate the merge.

**Merge not performed.**

## 13. Reviewer conduct statement

No provider action of any kind was performed. The Meshy contract was not freshened; no API key was
requested or used; no authorization preview was created; no Meshy task was created, polled, or
downloaded; no credits were consumed. Track S was not implemented. The Shared Authority Geometry
Scaffold was not implemented. Nothing was merged, tagged, or released. No project code was written or
modified — the reconstructed tree was used read-only for measurement, and all adversarial probes ran
in temporary scratch directories.
