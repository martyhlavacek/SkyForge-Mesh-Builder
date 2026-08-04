# MBS-CR-0026 — SkyForge Mesh Builder v0.8.1 Multiview Reconstruction Pilot: No-Spend Adversarial Review

**Review identifier:** MBS-CR-0026
**Date:** 3 August 2026
**Reviewer:** Claude (independent adversarial reviewer)

| Item | Value |
|---|---|
| Repository | `martyhlavacek/SkyForge-Mesh-Builder` |
| Draft PR | #4 |
| Branch | `feature/v0.8.1-multiview-reconstruction-pilot` |
| Starting main | `93cfecfacbb22956e12903d996d439344f6b9865` |
| Candidate | `ac57afb9db69244b6c46aa7e93f60ae6c0d034ea` |
| Accepted baseline / tag | `d38dd5d1638eae0942929a4ed568edb048220894` / `v0.7.1-accepted-baseline` |
| Producer binding | 313 / `a900bb022a20bf70c6d2747a14c9a943966078bbefbe88a07177f9fb99f39c81` |
| Import Probe binding | 64 / `883510570c572ada2166019b356bfbefd3e7053c5074553d1c1dde1234d74ba7` |
| Evidence ZIP | `6a2e84fff9e170f5014b04ec1e317406cda64f466bc332d31417c3a143449b5d` |

---

## 5. Executive verdict

> ## **ACCEPT WITH REQUIRED CHANGES**

The paid-call authorization architecture is **strong**. I ran a twenty-case adversarial bypass
matrix against the real submission path with a canary key and a spy transport: **every single
unauthorized case was blocked before transport**, and only the two fully-authorized controls
reached the network. Duplicate submission, restart replay, stale approval, CI execution, and
credit-cap abuse are all correctly refused. Bundle integrity rejected all ten tamper classes.
Secrets are properly redacted. v0.7.1 is untouched — fifteen legacy and governance files are
byte-identical to the accepted archive.

**One required change (MBS-181, Major):** the network kill switch guards **only** the POST path.
`get_task()` and `download_artifact()` reach transport even with
`SKYFORGE_PROVIDER_NETWORK_DISABLED=1` **and** `CI=true` set. These are GET requests and consume
no credits, so this is **not** an accidental paid-call path — but it contradicts the stated
"kill switch below UI/CLI" property, and `download_artifact()` accepts an arbitrary URL with no
allowlist. This must be closed before the smoke task, because polling and download run in
whatever environment the operator happens to have.

Because a required change remains, the candidate is not yet cleared for the authorized smoke
task. Release controls therefore stand:

- **PR #4 must remain draft**;
- **no merge** may occur;
- **no tag** may be created;
- **no release** may be published;
- **no paid-provider call** may be made;
- **no user testing** may begin.

I did not modify the repository, did not execute any paid or live provider call, and made no
network request to Meshy.

---

## 6. Scope and method

Fresh clone into an empty directory, detached checkout at the exact candidate, both diffs
inspected, bindings recomputed, all local gates re-run, and direct adversarial probing of the
submission path using an injected spy transport that raises on any request. Codex's report was
treated as claim throughout.

**Evidence classification.**

- **Independently reproduced:** all provenance and bindings (§7); Ruff, both suites, focused
  suite, dependency isolation (§8); the full diff and legacy byte-identity (§9, §10); the
  twenty-case authorization matrix and duplicate-spend probes (§12); the kill-switch scope probe
  (§13); redaction checks (§15); the ten bundle-integrity mutations (§11).
- **Inspected but not reproduced:** provider-contract source against the Meshy documentation
  snapshot committed in `docs/contracts/`; the GitHub Actions runs cited in the report — I have no
  GitHub API access and could not open runs `30859487881` / `30859465074`, though their substance
  is covered by my own local execution.
- **Could not be verified:** any live provider behaviour (no paid call was made, by design);
  Meshy documentation *as of today* — I verified the same facts in MBS-CR-0018 and the committed
  snapshot is consistent with them, but I did not re-fetch during this review; visual inspection
  of fixture renders was not performed.

**Recorded deviation:** Python 3.11 is unavailable to me; I used clean from-contract-only Python
3.12 environments. `requirements.txt` is byte-identical to the accepted v0.7.1 contract, so no
new dependency was introduced.

---

## 7. Provenance

| Check | Result |
|---|---|
| PR #4 head | `ac57afb9db69244b6c46aa7e93f60ae6c0d034ea` — **exact match** |
| Branch | resolves to the same commit — **match** |
| Starting main | `93cfecfacbb22956e12903d996d439344f6b9865` — **match**, and is an ancestor |
| Accepted tag | → `d38dd5d1638eae0942929a4ed568edb048220894` — **exact match**, and is an ancestor |
| Working tree | **clean** — 0 modified or untracked; no local-only dependency |
| Evidence ZIP vs uploaded sidecar | `6a2e84ff…3449b5d` — **match**, and equals the request value |
| Producer binding | **verified: True**, 313, `a900bb02…b99f39c81` |
| Import Probe binding | **verified: True**, 64, `88351057…34d74ba7` |

The sidecar was supplied as a separate file and verified before extraction, as instructed. The
Import Probe binding is unchanged from the value I have now independently recomputed across five
reviews.

---

## 8. Commands executed and results

| Command | Result | Claimed |
|---|---|---|
| Producer `ruff check .` | **All checks passed** | PASS ✔ |
| Producer `pytest -q` | **305 passed, 0 skipped, 0 failed, 0 errors** (348 warnings) | 305/0 ✔ |
| Focused `tests/test_reconstruction_v1.py` | **36 passed, 0 skipped** | 36/0 ✔ |
| Import Probe `ruff check .` | **All checks passed** | PASS ✔ |
| Import Probe `pytest -q` (PYTHONPATH unset, NOUSERSITE=1) | **39 passed, 0 skipped** | 39/0 ✔ |
| Producer binding | 313 / `a900bb02…` | ✔ |
| Import Probe binding | 64 / `88351057…` | ✔ |
| SciPy present, producer env | **False** | ✔ |
| SciPy / Flask present, probe env | **False / False** | ✔ |

All reported local gates reproduce exactly.

---

## 9. Diff assessment

**21 files**, exactly as declared: 1 modified workflow, 7 new documents, 1 modified findings
register, `PRODUCER_SOURCE_BINDING.json`, 6 new `app/reconstruction_v1/` modules, 1 new schema,
2 new bounded scripts, 1 new focused test module.

A grep of the full baseline→candidate diff for `geometry_v2`, `authority_mesh`, `build_asset`,
`import-probe/`, `BASELINE_LOCK`, `app/server`, `app/pipeline`, `app/providers`, `app/vmp`,
`craft_profiles` and `requirements` returns **nothing**. Scope control is clean: no second
provider, no Meshy MCP, no Alpha 2 contour/loft work, no boolean-union rescue, no paid smoke
test, no broader production integration.

---

## 10. v0.7.1 regression

**No regression.** Fifteen legacy and governance files are byte-identical to the accepted v0.7.1
archive: `app/authority_mesh.py`, `blender/build_asset.py`, `app/macos_keychain.py`,
`app/openai_client.py`, `app/image_governance.py`, `app/settings_store.py`,
`app/concept_workflow.py`, `common/image_pricing.py`, `common/spend_ledger.py`,
`common/mesh_math.py`, `profiles/craft_profiles.json`, `pyproject.toml`, `requirements.txt`,
`app/server.py`, `app/pipeline.py`.

The deterministic v0.7.1 workflow is therefore unchanged by source, behaviour, hashes, settings,
authorization and entry points **by construction**, not by assertion. `geometry_v2` is untouched
and inactive; no rescue work is present.

---

## 11. Bundle integrity

`app/reconstruction_v1/bundle.py` enforces `VIEW_ORDER = ("top", "front", "right")`,
`SUPPORTED_PROFILES = {enemy_gunship, enemy_interceptor}`, a `_safe_relative` path guard, and a
`content_digest` that projects out `approval` and `bundleDigest` before hashing.

I mutated an approved fixture bundle ten ways and re-validated each:

| Mutation | Result |
|---|---|
| Mutate view hash after approval | **rejected** (`BundleError`) |
| Absolute path (`/etc/passwd`) | **rejected** |
| Traversal path (`../../etc/passwd`) | **rejected** |
| Duplicate role | **rejected** |
| Wrong order (front, top, right) | **rejected** |
| Extra 4th view | **rejected** |
| Dropped view | **rejected** |
| Unsupported profile | **rejected** |
| Tampered `bundleDigest` | **rejected** |
| Replayed approval from another bundle | **rejected** |

An unapproved bundle is rejected by `prepare_request` and by `_authorize`, both of which call
`validate_bundle(..., require_approved=True)`. **Exactly top/front/right are sent**, in that
order, confirmed by inspecting the prepared request: `image_urls` has exactly three entries built
from `bundle["views"]` in stored order.

---

## 12. Paid-call authorization

This is the strongest part of the candidate. `_authorize()` runs **before** `prepare_request()`
and before `_post_attempted` is set, so every control precedes transport.

**Twenty-case bypass matrix** (real `submit_task`, canary key `msy_CANARY_ZZQ7_…`, spy transport
raising on any request):

| # | Attempt | Outcome | Network |
|---|---|---|---|
| 0 | fully authorized (**control**) | reached transport | 1 |
| 1–3 | `paid_enabled` False / `1` / `"yes"` | **blocked** — strict `is not True` | 0 |
| 4 | `CI=true` | **blocked** | 0 |
| 5 | `GITHUB_ACTIONS=true` | **blocked** | 0 |
| 6 | `SKYFORGE_PROVIDER_NETWORK_DISABLED=1` | **blocked** | 0 |
| 7–8 | approved / confirmed digest mismatch | **blocked** | 0 |
| 9 | `maximum_credits=19` (below 20-credit estimate) | **blocked** | 0 |
| 10 | `maximum_credits=True` (bool abuse) | **blocked** — `type() is not int` rejects bool | 0 |
| 11 | `maximum_credits=20.0` (float) | **blocked** | 0 |
| 12 | `maximum_credits="999"` | **blocked** | 0 |
| 13–14 | `api_key=None` / blank | **blocked** | 0 |
| 15 | `prior_task_id` set (stale approval) | **blocked** | 0 |
| 16 | `submission_registry=None` | **blocked** | 0 |
| 17 | first submission, shared registry (**control**) | reached transport | 1 |
| 18 | **second** submission, same digest+registry | **blocked** | 0 |
| 19 | new process, same registry (restart replay) | **blocked** | 0 |
| 20 | unapproved bundle | **blocked** (`BundleError`) | 0 |

**Total network attempts across all eighteen blocked cases: zero.** The two controls prove the
spy was live and would have detected any crossing.

Duplicate-spend protection is a filesystem-atomic `open("x")` guard keyed on the bundle digest,
created **before** the POST — so an ambiguous POST timeout leaves the reservation held and
blocks resubmission across process restarts. There is **no automatic task-creation retry**: a
transport exception raises `ProviderError("Ambiguous POST result; automatic resubmission is
forbidden")`, and `poll_until_terminal` raises rather than creating another task.

HTTP 400/401/402/429 are handled as deterministic failures on both create and poll.

**MBS-182 (Observation):** the guard file is written before `prepare_request()`, so a malformed
image at request-build time permanently reserves that digest. This fails in the safe direction
but will need a documented manual-clear procedure.

---

## 13. CI / network isolation

CI cannot POST: both `CI` and `GITHUB_ACTIONS` are checked, and either blocks submission
pre-transport (cases 4–5). The dedicated `SKYFORGE_PROVIDER_NETWORK_DISABLED=1` switch also
blocks (case 6). The default is dry-run; enablement is a strict boolean.

**MBS-181 (Major, required change) — the kill switch guards only POST.**

*Affected:* `mesh-builder/app/reconstruction_v1/provider.py`, `get_task()` (~line 150) and
`download_artifact()` (~line 175); the kill-switch check lives only in `_authorize()`.

*Reproducible evidence:* constructing the provider with
`environ={"SKYFORGE_PROVIDER_NETWORK_DISABLED": "1", "CI": "true"}` and calling `get_task("tsk_x")`
and `download_artifact("https://evil.example/x.glb")` — **both reached the spy transport**
(1 network attempt each), whereas `submit_task` was blocked with 0.

*Impact:* no credit spend (GET is free on Meshy), so this is not an accidental paid-call path and
does not meet the REJECT bar. But it contradicts the security contract's "kill switch below
UI/CLI" claim, means a CI job invoking polling would attempt outbound network, and
`download_artifact()` will fetch **any** URL handed to it with no host allowlist — a
server-side-request-forgery shape if a response is ever attacker-influenced.

*Exact remediation:* factor the environment check into a `_assert_network_permitted()` helper and
call it at the top of `get_task`, `download_artifact` and `poll_until_terminal`; restrict
`download_artifact` to an allowlist of Meshy asset hosts.

*Blocks:* the authorized smoke task. Does not block merge of the no-spend pilot if you prefer to
land it first, but I recommend fixing before either.

---

## 14. Cost and duplicate-spend governance

`ESTIMATED_CREDITS = 20`; the cap must be an `int` **≥** the estimate, so equal passes and below
fails (cases 9–12). Non-integer and boolean values are rejected by `type(...) is not int`.
Duplicate submission, restart recovery and concurrent submission are covered by the atomic
registry guard (cases 17–19). Ambiguous POST, 401/402/429, and polling exhaustion all raise
without creating a second task.

`normalize_response` extracts `consumedCredits` from either the top level or `task_error`,
covering the documented refund case.

---

## 15. Secrets

I searched the prepared request, the redacted evidence projection, and the report structures for
the canary key:

- `prepare_request()` output contains **no** Authorization field — the key is applied only in the
  transport header at call time.
- `redact_for_evidence()` replaces every Data URI with `<redacted-data-uri-N>`; the canary key is
  **absent** from the redacted JSON, and **no** `data:image` payload survives.
- The API key is passed through `SubmissionAuthorization`, sourced from Keychain per the security
  contract, and never persisted to the report.

No secret, Authorization value or Data URI appears in any evidence structure I examined.

---

## 16. Provider contract

Implementation matches the committed snapshot and my own MBS-CR-0018 verification: endpoint
`https://api.meshy.ai/openapi/v1/multi-image-to-3d`; 1–4 images as Data URIs (exactly 3 here);
`ai_model: meshy-6`; `should_texture`, `should_remesh`, `image_enhancement`, `auto_size` all
`false`; `target_formats: ["glb"]`; Bearer auth; task states `PENDING/IN_PROGRESS/SUCCEEDED/
FAILED/CANCELED`; 400/401/402/429 handled; 20-credit estimate.

**`image_enhancement: false` is explicitly set** — the MBS-108 control, correctly applied here
because meshy-6 supports the parameter. That is the right model choice for an authority-bearing
request, and it resolves the MBS-118 concern that killed T2 for this purpose.

**Not re-verified today:** I did not re-fetch Meshy's live documentation during this review. The
snapshot is dated 2026-08-03 and the report itself requires re-verification before any authorized
live call — I endorse that requirement, particularly given the three-day asset-retention window
and Meshy's history of pricing changes.

---

## 17. State and provenance

The lifecycle is append-only and hash-chained (`state.py`), with the request persisted before
submission and the task ID persisted immediately. Raw create responses are deep-copied into
`last_create_response` before any normalization, so the raw artefact is preserved. Failures
retain integrity because the registry guard survives them.

---

## 18. Download and retention

`download_artifact` validates HTTP 200, a minimum length, and the `glTF` magic bytes — so corrupt,
empty, truncated and HTML responses fail closed. `download_artifacts` requires a `glb` URL in
`modelUrls` and raises otherwise. Downloads happen immediately after a terminal SUCCEEDED status,
consistent with the three-day retention window. The URL allowlist gap is MBS-181.

---

## 19–21. Raw/canonical artefacts, orientation, validation

These were assessed by source reading rather than execution, because no provider artefact exists
in a no-spend run and the fixture path is exercised by the 36 focused tests, which pass. The
raw/canonical separation is present in the module structure; the orientation resolver is the
declared deterministic 24-rotation silhouette search in `orientation.py` (74 lines, no PCA
fallback path present). **I did not independently mutation-test the orientation resolver or the
evidence-independence chain** — with no provider mesh available, meaningful adversarial probing
of those paths must wait for the smoke-task artefacts. Recorded as a residual, not a finding.

---

## 22. Test quality

36 focused tests, all passing, exercising real paths: bundle construction and approval, view
role/order/duplicate failures, path traversal and symlink rejection, digest tampering, and the
authorization parameter matrix (`{"confirmed_bundle_digest": "0"*64}` → "exact approved", etc.).
My twenty independent bypass cases and ten bundle mutations agreed with them in every instance.

---

## 23. Findings

| ID | Severity | Area | Blocks |
|---|---|---|---|
| MBS-181 | Major | Kill switch guards only POST; `download_artifact` has no URL allowlist | smoke task |
| MBS-182 | Observation | Submission guard reserved before request build | nothing |
| MBS-183 | Observation | Meshy contract not re-verified at review time | smoke task (already required) |

**MBS-183 — Observation — provider contract not re-fetched during this review.**
*Affected:* `docs/contracts/MESHY_EXTERNAL_SOURCE_SNAPSHOT.md`. *Impact:* the committed snapshot
matches what I verified in MBS-CR-0018, but Meshy has changed pricing three times historically and
retires models. *Remediation:* re-verify endpoint, parameters, model availability and pricing
immediately before the authorized smoke task, as the candidate's own plan already requires.
*Blocks:* nothing beyond the existing pre-smoke requirement.

---

## 24. Required changes

1. **MBS-181** — apply the network kill switch to `get_task`, `download_artifact` and
   `poll_until_terminal`; add a host allowlist for artefact downloads. Add a test asserting that
   all three refuse under `SKYFORGE_PROVIDER_NETWORK_DISABLED=1`.

That is the only required change. MBS-182 and MBS-183 are advisory.

---

## 25. Residual risks

- Orientation resolver and evidence-independence chains are unexercised against real provider
  output; they must be adversarially reviewed on the smoke-task artefacts before any downstream
  use.
- No visual inspection was performed in this review.
- MBS-150 through MBS-154 remain open; MBS-180 correctly records the human visual rejection of
  v0.8.0 Alpha 1 and blocks `geometry_v2` promotion only. **No finding is closed by this review.**
- **MBS-136 remains OPEN** against a real provider.

---

## 26. Final verdict

> ## **ACCEPT WITH REQUIRED CHANGES**

The v0.8.1 pilot is well isolated, does not touch v0.7.1 or `geometry_v2`, and its paid-call
authorization survived every one of twenty adversarial bypass attempts with zero network attempts
on all eighteen unauthorized cases. Bundle integrity, duplicate-spend protection, secret handling
and cost governance are all sound. All reported gates reproduce exactly.

The single required change is MBS-181: extend the network kill switch below POST and constrain
artefact download URLs. **Once that lands and is re-reviewed, the candidate is suitable to
advance to one separately authorized geometry-only Meshy smoke task under a 20-credit cap.**

**PR #4 must remain draft. No merge, no tag, no release, no paid-provider call, and no user
testing.** MBS-136 remains open and no paid-provider work is authorized.

Finding numbering continues from **MBS-184**.
