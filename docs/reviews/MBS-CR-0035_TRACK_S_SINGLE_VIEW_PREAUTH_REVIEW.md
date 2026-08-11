# MBS-CR-0035 — Track S Single-View Preauthorization Architecture and Implementation Review

**Reviewer role:** Independent adversarial reviewer
**Repository:** `martyhlavacek/SkyForge-Mesh-Builder`

| Binding | Value |
|---|---|
| **Candidate SHA reviewed** | `8884b57d13f19039598db3df577f35714a3bd0fd` |
| **Parent SHA** | `8b4d8f0ce5a82dfd2e7269370693fa859af23f0e` (= current `origin/main`) |
| **Evidence SHA-256 verified** | `aeac24a7bbb2c7ebf8e7174b4e5a263fda60c8aa90a0cfa9828a3116c97befe7` |
| **Producer binding reproduced** | 337 files / `f6f73ccedd12274e1dafca7f2b48a1aa5b56355599a45dea3a4028d65889630c` |
| **Import Probe binding reproduced** | 64 files / `883510570c572ada2166019b356bfbefd3e7053c5074553d1c1dde1234d74ba7` |

**VERDICT: ACCEPT WITH REQUIRED CHANGES**

**Safe to progress only to human NO-SPEND Track S input binding/testing: YES.**

New findings: **MBS-210 (MAJOR)**, **MBS-211 (MINOR)**, **MBS-212 (OBSERVATION)**.
Neither MBS-210 nor MBS-211 blocks no-spend progression; **MBS-210 must be closed before any real
authorization.**

---

## 1. Evidence and candidate identity

Evidence ZIP matches the sidecar and the expected digest; the two supplied archives are
**byte-identical**, independently substantiating deterministic generation. Internal manifest:
**21 of 21 entries verified** by hash and size, nothing unlisted, nothing absent.

**Candidate proven, not inferred.** `8884b57d…` is not pushed. Following the method accepted in
MBS-CR-0033/0034: the declared parent `8b4d8f0c…` **is present and is `origin/main`** (the MBS-CR-0034
candidate `2c641084…` is confirmed an ancestor, so that merge landed). `COMPLETE_DIFF.patch` applied
to it cleanly, and the rebuilt tree reproduced the declared binding exactly:

```
PRODUCER rebuilt : 337  f6f73ccedd12274e1dafca7f2b48a1aa5b56355599a45dea3a4028d65889630c
PRODUCER declared: 337  f6f73cce…5889630c      per-file records identical: True
PROBE            :  64  883510570c572ada2166019b356bfbefd3e7053c5074553d1c1dde1234d74ba7  (unchanged)
```

## 2. Historical multiview compatibility (focus point 1)

This was the highest regression risk, and it is clean.

| Property | Result |
|---|---|
| Historical multiview canonical digest | **STABLE** — the preserved MBS-195 bundle recomputes to `c624051f…0581117f` under the candidate, unchanged |
| `inputKind` present in historical bundles | **NO** — kind is derived from `schemaVersion`, so no field was added and no digest shifted |
| Previously valid bundles reload under same rules | **YES** — same integrity path |
| MBS-196 cross-view gate still mandatory | **YES** — the rejected bundle still refuses at 1,290,626 ppm on reload |
| MBS-203 degenerate-image protections intact | **YES** — `cross_view.py` unchanged by this candidate |
| Multiview approval semantics | **UNCHANGED** |
| Quarantine added to multiview path | `build_bundle` and `approve_bundle` now also assert hash eligibility — strictly additive refusal |

**No versioning was required because no historical digest changed.** Deriving kind from
`schemaVersion` rather than a stored discriminator is the design decision that achieves this, and it
is the right one.

**Coercion probes — all fail closed:**

| Attempt | Result |
|---|---|
| Multiview bundle + injected `inputKind: single_view_v1` | resolves to `multiview_bundle_v1` (schemaVersion governs) |
| Single-view doc with `inputKind` removed | **REFUSED** |
| Single-view doc with unknown `inputKind` | **REFUSED** |
| Single-view doc with empty `inputKind` | **REFUSED** |
| Single-view doc carrying multiview `schemaVersion` | routes to multiview validation, which then fails on absent views |
| Bare `{}` | **REFUSED** |

**No alternate provider preparation path.** `provider.py` no longer calls `validate_bundle` directly;
both preparation sites now route through `validate_reconstruction_input`, and image URLs come from
`reconstruction_image_paths`, which itself re-validates. Single-view cannot reach a multiview-only
bypass, and multiview cannot reach single-view behaviour.

## 3. MBS-200 — executable or descriptive? (focus point 2)

**Partially executable. Precisely: the alignment and gameplay metrics are executable; the GLB
measurement engine is not implemented, and the hard gates consume caller-supplied attestations.**

| Element | Status |
|---|---|
| `MEASUREMENT_SPEC` (frozen, digest-bound) | **Present and enforced** — spec/decision/request digests are pinned into the preregistration |
| `align_top_silhouettes` | **Executable** — real numpy, recomputable by a reviewer |
| `gameplay_silhouette_metrics` | **Executable** |
| `hard_validity_failures` | **Structural only** — reads `glbExists`, `glbHashMatches`, `blenderReloadSucceeded`, `watertight`, component counts, bbox, etc. from a dict supplied by the caller |
| Blender reload / topology / watertightness engine | **NOT IMPLEMENTED in this candidate** |
| `decide_experiment` | Consumes `top_iou_ppm` as a caller-supplied integer; it does **not** recompute IoU from images |

**Executed demonstration:** a fully fabricated measurement record — no GLB, no Blender, no image ever
supplied — combined with a self-constructed readability review and an asserted
`top_iou_ppm = 999999` yields **`CONTINUE_SINGLE_VIEW`**. The decision record correctly carries
`createsProviderTask: False`, `authorizesAnotherTask: False`, `automaticRetryCount: 0`, so nothing is
spent or launched — but the decision itself is a classification over attestations.

This is not concealed by the submission, and it is consistent with a preauthorization-plumbing scope.
It does mean **MBS-200 cannot be closed**. What is proven is the specification, the alignment
mathematics, the hard-gate *structure*, and the abort dominance — not that measurements originate
from an independently reloaded GLB.

**MBS-200: PARTIALLY REMEDIATED — REMAINS OPEN.**

## 4. MBS-199 — cost governance (focus point 3)

`validate_cost_governance(require_resolved=True)` correctly refuses every representation trick:

| Attempt | Result |
|---|---|
| `UNRESOLVED` (honest current state) | **REFUSED** |
| field missing | **REFUSED** |
| empty string | **REFUSED** |
| unknown enum (`PROBABLY_FREE`) | **REFUSED** |
| lowercase `not_charged` | **REFUSED** (case-sensitive enum) |
| resolved status with empty evidence | **REFUSED** |
| cap raised to 40 / second task / retry enabled / sequential costs understated | **REFUSED** |

The 20-credit cap, single authorized task, zero retry, and the honest 20/40/60 cumulative
sequential-cost table are all pinned — the cost model I raised in MBS-199 is recorded correctly,
including `strategyRationale: "information_value_not_per_task_savings"`, which states the trade
plainly rather than implying savings that do not exist.

**One gap, raised as MBS-210:** a resolved disposition passes with **arbitrary non-empty free-text
evidence**. `failedTaskChargingEvidence` is not bound to a contract-snapshot digest or any verified
artifact, so a fabricated `NOT_CHARGED` + `"x"` validates.

**MBS-199: REMAINS OPEN** pending fresh official evidence of Meshy's failed/rejected-task charging
behaviour, exactly as required. The synthetic fixtures prove logic and do not satisfy real
preauthorization.

## 5. MBS-201 — preregistration (focus point 4)

Committed policy and run-specific preregistration are correctly separated: the policy digest is one
of several digests *inside* the run record, so the policy cannot masquerade as the run artifact.

| Attempt | Result |
|---|---|
| Honest, committed, ancestral | **ACCEPTED** |
| Post-commit mutation | **REFUSED** — digest changed |
| Uncommitted (non-ancestral commit) | **REFUSED** |
| Candidate source commit non-ancestral | **REFUSED** |
| Measurement spec / decision rules / fixed request / quarantine digest altered | **REFUSED** |
| Rebuilt cleanly on unrelated history (digest recomputed) | **REFUSED** — "uncommitted or not bound to executing source" |
| Quarantined FRONT substituted as beauty input | **QUARANTINE REFUSAL** |
| Substituted TOP validation target | produces a different preregistration digest (detectable at authorization) |

The record binds all ten required elements including `validationTarget.isReconstructionInput: False`,
which encodes the independence property in the artifact itself.

**MBS-201: REMAINS OPEN** — the real first-run preregistration does not exist yet. This candidate
supplies the machinery only.

## 6. MBS-202 — quarantine (focus point 5)

**Hash identity governs, not filename, path, or provenance label.**

| Attempt | Result |
|---|---|
| Rejected FRONT renamed `beauty_reference.png` | **QUARANTINE REFUSAL** |
| Rejected RIGHT copied to `concepts/approved_beauty.png` | **QUARANTINE REFUSAL** |
| Rejected FRONT, second copy, unrelated name/path | **QUARANTINE REFUSAL** |
| Approved TOP `7009a2b6…` as beauty input | **ACCEPTED** — correctly *not* quarantined |
| Quarantined hash in preregistration | **QUARANTINE REFUSAL** |

Enforcement is at multiple boundaries — single-view build, multiview `build_bundle` and
`approve_bundle`, `validate_reconstruction_input`, and preregistration construction. Preserved
historical MBS-195 evidence remains inspectable read-only: the rejected bundle still loads for
measurement and still reports FAIL, so negative evidence was retained rather than deleted.

**MBS-202: CLOSED.**

## 7. Experiment-decision semantics (focus point 6)

`DECISIONS = {CONTINUE_SINGLE_VIEW, ESCALATE_TWO_VIEW_ELIGIBLE, ABORT_MESHY}` has **zero overlap**
with the 15 canonical provider lifecycle states in `TRANSITIONS` — verified by set intersection. The
canonical lifecycle is unchanged. Decision records carry explicit `createsProviderTask: False`,
`authorizesAnotherTask: False`, `automaticRetryCount: 0`, and `decide_experiment` performs no
provider call, state transition, cost approval, or retry.

`ABORT_MESHY` is an experiment result, not a lifecycle state. **MBS-198's abort branch now exists and
dominates correctly:** an `UNREADABLE` human verdict forces `ABORT_MESHY` even at 990,000 ppm, and any
hard-gate failure forces `ABORT_MESHY` even at a perfect 1,000,000 ppm.

**MBS-198: CLOSED.**

## 8. IoU anti-gaming (focus point 7)

Reproduced the alignment adversarially rather than trusting the declared constants:

| Probe | Result |
|---|---|
| Identical silhouettes | 1,000,000 ppm |
| **Mirrored candidate** (reflection would restore it) | **384,083 ppm**, `reflectionUsed: False` — reflection correctly refused |
| 90°-rotated candidate | 1,000,000 ppm, quarter-turn permitted |
| **Anisotropically stretched** | **728,128 ppm**, `anisotropicScaleUsed: False` — not "fixed" |
| Pure translation | 1,000,000 ppm via centroid alignment, `translationSearchUsed: False` |
| Tie-break | smallest angle selected |
| Non-1024 input | **REFUSED** — "must be exactly 1024 x 1024" |

Alpha threshold is 128; scale is isotropic with the **fore-aft (Y) extent as the anchor**; translation
is centroid-only with no search. Integer arithmetic throughout.

**Exact decision boundaries confirmed:**

```
 940000 -> CONTINUE_SINGLE_VIEW        800000 -> CONTINUE_SINGLE_VIEW
 800001 -> CONTINUE_SINGLE_VIEW        799999 -> ESCALATE_TWO_VIEW_ELIGIBLE
 650001 -> ESCALATE_TWO_VIEW_ELIGIBLE  650000 -> ESCALATE_TWO_VIEW_ELIGIBLE
 649999 -> ABORT_MESHY  (reason TOP_IOU_BELOW_0_65)
```

**Production floor preserved and isolated.** `BLENDER_SILHOUETTE_IOU_MIN = 0.94` in
`vmp_job_export.py` and `assembledSilhouetteFloor >= 0.94` in `geometry_v2/metrics.py` are untouched.
`track_s.py` references `940000` only as `productionIouFloorPpmUnchanged` — a recorded reference,
with no write path to the production gate. Track S exploratory bands cannot weaken or overwrite it.

## 9. 64×64 / 75° gameplay evidence (focus point 8)

The camera convention is frozen in `MEASUREMENT_SPEC` with orthographic projection, 75° elevation,
135° azimuth, 0° roll, 10% framing margin, 64×64 output, alpha threshold 128, clipping check,
`foregroundPixelCount >= 128`, and `largestComponentPixelFractionPpm >= 800000` — all enforced in
`hard_validity_failures` (subject to §3: enforced against a supplied record).

`build_human_readability_review` requires an explicit `READABLE`/`UNREADABLE` verdict, a reviewer, a
timestamp, and a 64-hex artifact SHA-256, and seals them with a digest. `decide_experiment` verifies
that digest and treats a missing or non-`READABLE` verdict as an abort reason. **Human readability
cannot be automatically inferred** — verified by probe: tampering with the review is detected
("readability review digest changed").

**Convention binding — raised as MBS-211.** The 75°/135° gameplay camera is declared inside
`MEASUREMENT_SPEC` but I could not locate a corresponding pre-existing gameplay-camera constant in the
repository to bind it to. It is therefore effectively a new convention introduced by this candidate,
frozen by digest but not cross-referenced to the established `projected_gameplay_64` pipeline.

## 10. Contract-age evidence precision (focus point 9)

I resolved this rather than leaving it as a discrepancy.

- **Implementation is correct.** `load_contract_snapshot` parses the full ``Retrieved at
  `2026-08-04T03:23:05Z` `` timestamp. Executed against the repository snapshot at
  `2026-08-10T23:25Z` it yields **164.032 h → floor 164**, `STALE`, sha `d5736aa3…`. This code path
  is **unchanged** by the candidate.
- **The evidence artifact used a different, cruder path.** `STALE_CONTRACT_EVIDENCE.json` records
  `verificationDate: "2026-08-04"` — a **date, not a timestamp** — and `ageHoursFloor: 167`.
  From midnight the same instant gives **167.42 h → floor 167**, which reproduces the reported figure
  exactly. The ~3.4 h gap is precisely the `03:23:05` offset.
- **Diagnosis:** a *reporting* issue in the evidence generator, not a clock, timezone, or
  implementation defect. The direction is conservative — date-only parsing can only overstate age and
  therefore only make a contract look **more** stale, never fresher — so it cannot cause a false
  FRESH near the 24-hour boundary.

Recorded as **MBS-212 (OBSERVATION)**: the evidence figure is not reproducible from the implementation
and the evidence generator should call `load_contract_snapshot` so the two agree.

## 11. Independent gate execution

| Gate | Reported | My result |
|---|---|---|
| Producer Ruff | PASS | **PASS** |
| Complete Producer pytest | 469 | **469** (448 + 21), 0 skipped |
| Focused Track S / reconstruction / pilot / cross-view | — | **180 passed** |
| Historical rejected bundle | FAIL | **FAIL at 1,290,626 ppm** |
| v0.7.1 isolation | PASS | **PASS** |

Full-suite execution again split around `tests/test_authority_mesh.py` (~177 s of trimesh work) — the
known environmental slowness, not a defect.

**v0.7.1 production isolation:** tag still dereferences to `d38dd5d1638eae0942929a4ed568edb048220894`;
`server.py`, `templates/index.html`, `pipeline.py`, `bootstrap.py`, and `macos_keychain.py` are all
**byte-identical** to it. No Track S change leaked into the accepted production route.

---

## 12. New findings

### MBS-210 — MAJOR — Resolved failed-task charging accepts unbound free-text evidence

`validate_cost_governance` requires `failedTaskChargingEvidence` to be merely truthy when the
disposition is resolved. A fabricated `NOT_CHARGED` with evidence `"x"` **validates**. Every other
representation trick is refused, so this is the single remaining route by which MBS-199 could be
declared resolved without official evidence.

**Remediation.** Bind the evidence to a verifiable artifact — a fresh contract-snapshot SHA-256 plus a
quoted clause locator, validated for shape (64-hex digest, non-empty locator) and cross-checked
against the snapshot actually loaded for the authorization. Add a regression test asserting that a
free-text evidence string is refused.

**Does not block no-spend progression. Must be closed before any real authorization.**

### MBS-211 — MINOR — Gameplay camera convention introduced without cross-binding

The 75° elevation / 135° azimuth / 0° roll / 10% margin / 64×64 convention is frozen inside
`MEASUREMENT_SPEC` but is not cross-referenced to an existing repository gameplay-camera constant, so
Track S could measure against a convention that drifts from the production
`projected_gameplay_64.png` pipeline.

**Remediation.** Bind the Track S camera parameters to the established gameplay-camera definition (or
state explicitly in the spec that Track S defines the canonical convention and the production pipeline
will be aligned to it), and add a test asserting the two agree.

### MBS-212 — OBSERVATION — Evidence contract age not reproducible from the implementation

As analysed in §10: evidence reports 167 h from a date-only parse; the implementation yields 164 h
from the full timestamp. Conservative direction, not authorization-relevant. The evidence generator
should call `load_contract_snapshot` so the recorded age is reproducible.

## 13. Finding dispositions

| Finding | Disposition |
|---|---|
| **MBS-198** | **CLOSED** — `ABORT_MESHY` exists as an experiment-level result, dominates hard-gate failure and `UNREADABLE`, and carries no lifecycle state or automatic action. |
| **MBS-199** | **REMAINS OPEN** — correctly reported `UNRESOLVED`; refusal machinery is sound except MBS-210. Must stay open until fresh official Meshy charging evidence exists. |
| **MBS-200** | **PARTIALLY REMEDIATED — REMAINS OPEN.** Specification frozen and digest-bound; alignment and gameplay metrics executable and non-gameable; hard-gate structure and abort dominance proven. The Blender reload/topology/watertightness engine is **not implemented**, and decision inputs are caller attestations — demonstrated by driving `CONTINUE_SINGLE_VIEW` from a wholly fabricated record. |
| **MBS-201** | **REMAINS OPEN** — machinery proven (immutability, ancestry, digest binding, quarantine); the real run-specific preregistration does not yet exist. |
| **MBS-202** | **CLOSED** — hash identity governs at every boundary; approved TOP not caught; historical evidence still read-only inspectable. |
| **MBS-136** | **REMAINS OPEN** — no real provider correspondence exercised. Standing prerequisite for any paid operation. |
| **MBS-195** | **REMAINS OPEN** — no replacement coherent human-approved bundle exists; the rejected set is preserved and still measures FAIL. |
| **MBS-208** | **REMAINS OPEN MINOR** — no foreground-coverage ceiling; `cross_view.py` unchanged. |
| **MBS-209** | **REMAINS OPEN MINOR** — ALL-CAPS-then-lowercase filename tokens; `pilot.py` tokenizer unchanged in this respect. |
| **MBS-183** | **REMAINS the standing immediate preauthorization re-verification requirement** — unaffected by this candidate, which authorizes nothing. |
| **MBS-210, 211, 212** | **NEW, OPEN.** |

## 14. Verdict and progression boundary

**VERDICT: ACCEPT WITH REQUIRED CHANGES.**

The architecture is the one recommended in MBS-CR-0032 and it is implemented faithfully: one
lifecycle, one authorization path, one spend-governance path, one Meshy endpoint, two input schemas
behind an `inputKind` discriminator derived from `schemaVersion` — which is precisely why no
historical digest moved. Multiview is not weakened; it is strengthened by quarantine enforcement.

**Is candidate `8884b57d13f19039598db3df577f35714a3bd0fd` safe to progress only to human NO-SPEND
Track S input binding/testing? YES.**

Nothing in this candidate can reach a provider: the contract is stale and refused, cost governance
refuses on `UNRESOLVED`, no run-specific preregistration exists, decisions carry no side effects, and
the network kill switch and v0.7.1 isolation are intact. Binding a beauty image, approving it, and
exercising the pilot with no spend is appropriate next work.

**This ACCEPT authorizes none of:** contract freshening; API-key access; an authorization preview for a
real task; cost approval; Meshy contact; provider submission; polling; downloading; credit spending; a
second-view experiment; merge; tag; release.

**Before any real authorization, additionally required:** MBS-210 closed; MBS-199 resolved by official
evidence; MBS-201 satisfied by a real committed run-specific preregistration; MBS-200 either closed by
an executable measurement engine or explicitly accepted as attestation-based with a named accountable
human; and MBS-183 re-verification performed immediately beforehand.

## 15. Reviewer conduct statement

No provider action was performed. No API key was requested or used. The Meshy contract was not
freshened — it remained stale throughout, and I confirmed authorization refuses on that basis. No
authorization preview was created; no Meshy task was created, polled, or downloaded; no credits were
consumed. Track S was not implemented; the Shared Authority Geometry Scaffold was not implemented.
Nothing was merged, tagged, or released. No project code was written or modified — the reconstructed
tree was used read-only for measurement, and all adversarial probes ran in temporary scratch
directories.
