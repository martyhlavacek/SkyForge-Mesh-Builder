# MBS-CR-0005 — Adversarial Review: SkyForge Mesh Builder Sidecar v0.5.1

**Artifact:** `SOURCE/SkyForge_Mesh_Builder_Sidecar_v0.5.1.zip`
**SHA-256:** `d58a7ba93f498fe0f843e8afc4fbdd7ee076faf22b3b159498b749e2608c30c5` — **verified** against the adjacent `.sha256` sidecar and `SHA256SUMS.txt`; all 25 package files verified `OK`.
**Evidence:** `EVIDENCE/enemy.interceptor.01-7cf6536d_review_package.zip` and the accompanying PNGs/JSON.
**Reviewer:** Claude (independent adversarial review)
**Predecessors:** MBS-CR-0001 (25 findings), -0002 (19), -0003 (11), -0004 (5). New findings continue the series at **MBS-61**.
**Date:** 30 July 2026

---

## 1. Verdict

**CONDITIONAL GO for the next epoch, with a hard split between the two tracks.**

- **Track A (cost): GO immediately, and treat it as blocking.** The ~US$0.75 charge is exactly reproducible from the shipped defaults, and the sidecar is pinned to what is now the **most expensive image model OpenAI sells**. The economy path is a configuration change plus a governance layer, not research. Routine exploration can drop from **$0.750 to $0.010 per round — 75× — with no architectural risk.** No further paid concept rounds should run until the budget gate exists, because there is currently no mechanism that can prevent an accidental $10 afternoon.

- **Track B (geometry): CONDITIONAL GO for provider integration, with a strong recommendation to do one cheap local change first.** The 2.5D ceiling is real and I have now quantified it: **62.2% of the delivered interceptor's surface area carries no shape information** — 31.6% is a perfectly flat belly on a single hardcoded plane, 30.6% is vertical extrusion wall. That is not a tuning problem. But the highest-value next step is *not* the neural provider; it is a two-sided height field, which is roughly a day of deterministic work and removes the flat belly and the vertical walls outright. Do that in parallel with the Meshy adapter so Experiment 02 has an honest baseline.

**NO-GO on one thing specifically:** training or fine-tuning any 3D foundation model. Nothing in the evidence suggests it is needed, and it would convert SkyForge into a 3D-research project.

---

## 2. Mechanical verification performed

| Check | Result |
|---|---|
| SHA-256 of source ZIP vs sidecar and SHA256SUMS | **Match**; `sha256sum -c` → 25/25 `OK` |
| Source extraction and inventory | 4 432 lines of Python across app/blender/common/tests |
| `ruff check .` | **FAIL — 1 error** (F821). → MBS-66 |
| `pytest -q` (Flask 3.1.1, Werkzeug 3.1.7, pinned) | **2 failed, 51 passed** in 85 s. → MBS-67 |
| Official OpenAI pricing retrieved and cost model rebuilt | ~$0.75 reproduced **exactly**. → MBS-61 |
| Interceptor GLB loaded and measured independently (trimesh) | Topology confirmed; 2.5D ceiling quantified. → MBS-70, MBS-71 |
| Endpoint probes (job rejection path) | Workspace state created on rejected requests. → MBS-69 |

Findings are labelled **[probe]** (executed) or **[read]** (source analysis).

**Pricing provenance.** All figures below come from OpenAI's official image-generation cost table at
`https://developers.openai.com/api/docs/guides/image-generation#calculating-costs` and the model token rates at
`https://developers.openai.com/api/docs/pricing`, both **retrieved 30 July 2026**. I have not used remembered pricing anywhere.

---

## 3. What should be preserved

The list in the review request is accurate and I would not weaken any of it. Three items deserve specific credit because they are load-bearing and easy to lose in a provider migration:

- **The exact glTF↔Blender coordinate contract.** `TARGET_TO_GLTF` / `GLTF_TO_BLENDER` with a measured `blenderImportBoundsDelta` of `4.8e-08` is the hardest-won result in this codebase (MBS-CR-0003 lineage). Any provider adapter must round-trip through the *same* contract and report the same delta.
- **The fail-closed gate structure**, including `blenderImportSilhouetteIoU` measured on the *reimported* mesh rather than the generated one. That is the pattern that catches coordinate regressions.
- **Independent reload validation** — exporting the GLB and re-loading it with trimesh before accepting it. I reproduced this myself and it holds.

Also worth preserving: the v0.5.1 `_rgba_and_mask` float32 fix, with its comment explaining the int16 overflow. That comment will stop someone reintroducing the bug.

---

# TRACK A — API Cost Architecture

## 4. Current cost flow

```
UI (Concept Lab)
  │  beautyCount (1–4, default 3), userPrompt, profileId
  ▼
POST /api/concepts/beauty ─────────────────────────────────────────┐
  │  server.py:279  no estimate, no cap, no cache, no idempotency  │
  ▼                                                                │
openai_client.generate_beauty_candidates()                         │  ← every call bills
  payload = { model: gpt-image-1,          ← settings              │
              size:  1536x1024,            ← settings              │
              n:     3,                    ← settings              │
              quality: 'high' }            ← HARDCODED, line 87    │
  requests.post(timeout=240) ──────────────────────────────────────┘
  │
  ├─ response.raise_for_status()        ← no retry policy, no backoff
  ├─ payload['data']  → images kept
  └─ payload['usage'] → DISCARDED       ← actual billable tokens thrown away
  │
  ▼
workspace/_concepts/<run>/metadata.json
  openai: { imageModel, size, count }   ← quality absent: the dominant cost driver is not recorded
```

The authority stage repeats the same shape against `/v1/images/edits`, adding **input image tokens** for the uploaded beauty reference that are neither estimated nor recorded.

## 5. Findings — Track A

### HIGH

---

#### MBS-61 — The observed ~US$0.75 is exactly reproducible, and the shipped defaults select the most expensive model in the current lineup **[probe]**

Confirmed from source, not from the brief:

| Setting | Value | Location |
|---|---|---|
| `imageModel` | `gpt-image-1` | `openai_client.py:14`, `bootstrap.py:40` |
| `beautySize` | `1536x1024` | `openai_client.py:42`, `bootstrap.py:41` |
| `beautyCountDefault` | `3` | `openai_client.py:44`, `bootstrap.py:43` |
| `authoritySize` | `1024x1024` | `openai_client.py:43`, `bootstrap.py:42` |
| `authorityCountDefault` | `2` | `openai_client.py:45`, `bootstrap.py:44` |
| `quality` | `'high'` — **hardcoded** | `openai_client.py:87` and `:114` |

Against the official table:

```
beauty : gpt-image-1 / high / 1536x1024 / n=3 = 3 × $0.250 = $0.750   ← exact match to the reported charge
authority: gpt-image-1 / high / 1024x1024 / n=2 = 2 × $0.167 = $0.334  (+ unmeasured input image tokens)
full default beauty+authority round (output only)      = $1.084
```

The more consequential half of this finding is model selection. At the shipped beauty point (1536×1024, high), per image:

| Model | Price | vs gpt-image-1 |
|---|---:|---|
| gpt-image-1-mini | $0.052 | −79.2% |
| **gpt-image-2** | **$0.165** | **−34.0%** |
| gpt-image-1.5 | $0.200 | −20.0% |
| **gpt-image-1 (current default)** | **$0.250** | — |

`gpt-image-1` is the **most expensive** of the four at every quality/size cell in the official table. It also no longer appears in the main pricing page's per-token model list — only in the legacy per-image table alongside 1.5 and mini, while `gpt-image-2` is documented as "our latest". The sidecar is paying a premium to stay on an older model.

Worth noting for the estimator: the cheapest cell in the entire table is **gpt-image-2 / low / non-square at $0.005** — cheaper than `gpt-image-1-mini` low ($0.006). Landscape and portrait are *cheaper* than square on gpt-image-2, which is counter-intuitive and should be encoded in the estimator rather than assumed.

---

#### MBS-62 — There is no cost governance of any kind **[read]**

Neither `/api/concepts/beauty` nor `/api/concepts/authority` has:

- a pre-flight cost estimate,
- a per-run or per-session budget cap,
- a content-hash cache,
- an idempotency key,
- an in-flight lock (note the contrast: `pipeline.py` guards Blender jobs with `_JOB_SEMAPHORE`, but the *billed* endpoints are unguarded — a double-clicked button bills twice),
- any recorded spend.

A user holding the button, or a browser retrying a slow POST, spends real money with no ceiling and no record. Given the project's standing principle that governance belongs at the transactional core rather than the UI layer, the billed call site is exactly where the gate is missing.

---

#### MBS-63 — `quality` is hardcoded, unconfigurable, and absent from the provenance record **[read]**

`quality: 'high'` appears as a literal in both call paths. It is:

- not a parameter of `sanitize_and_save_settings()` (`settings_store.py:136-176`),
- not in `settings_payload()`,
- not in the Settings UI,
- **not written into `metadata.json`** — the concept run records `imageModel`, `size` and `count` only (`server.py:311`, `:373`).

So the artifact that documents a concept run omits the single variable with the largest effect on its cost — a 4.8× swing between low and high at the same model and size. This is the recurring pattern from CR-0002 and CR-0003 in a new place: the record describes the run without recording what actually drove it.

---

#### MBS-64 — The response `usage` block is discarded, so actual spend can never be reconstructed **[read]**

`generate_beauty_candidates` reads `payload.get('data')` and drops everything else (`openai_client.py:91-95`); the same in the authority path. GPT Image responses carry a `usage` object with input/output token counts and an `input_tokens_details` breakdown.

This matters more than the estimator. **Estimated cost is a model; `usage` is ground truth.** Without it, the job record can only ever assert what a run *should* have cost. Capturing it turns spend into a measured quantity — which is the standard this project has applied to every other value in an evidence file.

Concretely, it is also the only way to price the authority stage honestly, because the edits endpoint bills input image tokens for the uploaded beauty reference and the guide is explicit that reference-image edits "can use more input tokens."

---

#### MBS-65 — A 240-second timeout on a billed request is a silent-money path **[read]**

`requests.post(..., timeout=240)` with `n=3` at high quality. The guide notes complex prompts "may take up to 2 minutes"; three high-quality landscape images in one request is a plausible timeout candidate. On timeout:

1. `requests` raises;
2. OpenAI has already generated — and billed — the images;
3. the handler's blanket `except Exception` returns a generic 500;
4. no images are saved, nothing is recorded;
5. the user's natural next action is to press the button again — **billing a second time**.

There is no `Idempotency-Key` header, so the retry is a genuinely new charge. This is the single most likely way to lose money without noticing, and it is invisible in the current logs.

---

### MEDIUM

---

#### MBS-66 — Ruff fails, so `run_tests.command` never reaches pytest. This is a regression of MBS-46 **[probe]**

```
$ ruff check .
F821 Undefined name `Any`
  --> app/openai_client.py:60:34
Found 1 error.
```

`_decode_item(item: dict[str, Any], ...)` uses `Any` without importing it. `from __future__ import annotations` makes the annotation lazy, so it does not raise at runtime — but it is still a real undefined name that would fail under `typing.get_type_hints()`, and it fails the lint gate.

`scripts/run_tests.command` is `set -e` → `ruff check .` → `pytest`. Ruff exits non-zero, so **pytest never runs**. MBS-46 identified this exact failure mode in v0.2.1; v0.2.2 closed it and I verified the preflight green. It has regressed. One-line fix (`from typing import Any`), but the lesson is that the preflight needs to be part of the release checklist, not a file that exists.

---

#### MBS-67 — Two shipped tests fail, and the build verification's expectation for them is wrong **[probe]**

`BUILD_VERIFICATION_v0.5.1.md` reports "43 passed, 2 skipped" and states the Flask modules "are expected to run after the target Mac launcher installs the pinned requirements." They run. Two fail:

```
FAILED tests/test_server.py::test_provider_mesh_mode_requires_mesh   — assert 422 == 400
FAILED tests/test_server.py::test_authority_mesh_mode_rejects_uploaded_mesh
```

I re-ran against the exact pinned Flask 3.1.1 / Werkzeug 3.1.7 to rule out an environment artifact — still fails. The endpoint now returns **422** with a richer body; the tests still assert 400. The behaviour is arguably correct and the tests are stale, but the release ships with a red suite and a document asserting it will be green.

The pattern to name: **a claim about an unverifiable environment is still a claim.** "Expected to pass on the Mac" carried the same epistemic weight in v0.2.1 (MBS-46) and was wrong then too. Where a check cannot be run in the build sandbox, the honest form is "unverified" with no prediction attached.

---

#### MBS-68 — The API key is passed as a `security` command-line argument **[read]**

`settings_store.py:94-97` calls `security add-generic-password -U -s ... -a ... -w <value>`. On macOS the full argument vector of a running process is readable by other processes of the same user via `ps`. The exposure window is short (a single `subprocess.run`), and the threat model for a single-user Mac is limited — but the key is also the thing that spends money, and this is the one place it appears in cleartext outside the Keychain. Prefer stdin-fed entry or a temporary file with `0600` and immediate unlink.

---

#### MBS-69 — Rejected job requests still create workspace state and leak absolute paths **[probe]**

```
POST /api/jobs (Authority Mesh mode + a mesh upload)
→ 422 {"error":"ValueError: Authority Mesh mode generates its own mesh; remove the mesh upload",
       "jobId":"enemy.test-f9c76d40",
       "jobPath":"/tmp/.../ws/enemy.test-f9c76d40",
       "preparationLog":".../logs/preparation_error.log"}
```

A request rejected on a validation rule still allocates a job directory, writes a preparation log, and returns absolute filesystem paths plus a raw `ValueError:` prefix to the client. Validate before allocating; return the message without the exception class or the paths.

---

## 6. API-economy recommendation

### 6.1 Recommended economy-mode defaults

| Stage | Model | Quality | Size | n | Cost | Rationale |
|---|---|---|---|---:|---:|---|
| **S0 explore** | `gpt-image-2` | low | 1536×1024 | 2 | **$0.010** | Cheapest cell in the table; two candidates preserve A/B choice |
| **S1 refine** | `gpt-image-2` | medium | 1536×1024 | 1 | $0.041 | Only on an approved S0 direction |
| **S2 final beauty** | `gpt-image-2` | high | 1536×1024 | 1 | $0.165 | Once, after visual approval |
| **A0 authority draft** | `gpt-image-1-mini` | low | 1024×1024 | 2 | $0.010 | Silhouette legibility, not beauty |
| **A1 authority final** | `gpt-image-1-mini` | medium | 1024×1024 | 1 | $0.011 | Feeds the mesh generator |
| | | | | | **$0.237** | **one accepted asset, full ladder** |

Answering question 10 directly — **yes, the two stages should use different models, and not only for cost.** The image-generation guide states `gpt-image-2` **does not support transparent backgrounds**. The authority image feeds a silhouette extractor whose v0.5.1 hotfix (`MBS-RES-0011`) was specifically about opaque-background mask overflow, and whose fallback path is a corner-colour distance heuristic with a magic threshold of 28. An authority model that supports `background: "transparent"` deletes that entire failure class and replaces `corner_colour_distance_28` with a true alpha mask. That is a correctness argument, not a cost argument, and it points at `gpt-image-1-mini` or `gpt-image-1.5` for the authority stage regardless of price. **Verify transparent-background support on the chosen authority model before relying on it** — the guide is explicit only about `gpt-image-2` lacking it.

### 6.2 Cost envelopes

| Workflow | Current | Economy | Ratio |
|---|---:|---:|---:|
| Rough beauty exploration (one round) | $0.750 | **$0.010** | 75× |
| Ten exploration rounds | $7.50 | **$0.10** | 75× |
| Approved beauty refinement | — | $0.041 | |
| Final beauty (once) | $0.250 | $0.165 | 1.5× |
| Authority generation | $0.334 | $0.010 | 33× |
| Multiview 4-view set (mini/low/1024, independent) | — | $0.020 | |
| Multiview as one 2×2 composite sheet (gpt-image-2/medium/1024) | — | $0.053 | |
| **One accepted game asset, end to end** | ~$1.08+ | **$0.237** | 4.6× |

### 6.3 Cost estimator design

```python
# common/image_pricing.py — data, not logic
PRICING_RETRIEVED = "2026-07-30"
PRICING_SOURCE = "https://developers.openai.com/api/docs/guides/image-generation#calculating-costs"
OUTPUT_IMAGE_USD = { ("gpt-image-2","low","1536x1024"): 0.005, ... }   # full table, verbatim

def estimate(model, quality, size, n, *, reference_images=0) -> Estimate:
    """Return a fail-closed estimate. Unknown combination => raise, never guess."""
```

Three rules that matter more than the arithmetic:

1. **Unknown (model, quality, size) must raise, not fall back to a default.** A silent fallback is how a $0.005 estimate precedes a $0.25 charge.
2. **The table carries its own retrieval date**, surfaced in the UI and written into every run record. Pricing changes; an estimate whose provenance is unknown is worse than none.
3. **Edit-endpoint estimates must be explicitly marked lower-bound**, because input image tokens are not in the per-image table. Report `estimatedOutputUsd` and `inputTokensUnknown: true` rather than a single confident number.

### 6.4 Budget gate schema (fail-closed)

```json
{
  "budget": {
    "schemaVersion": "skyforge.image-budget.v1",
    "perRequestUsdMax": 0.05,
    "perAssetUsdMax": 0.50,
    "perSessionUsdMax": 2.00,
    "requireConfirmationAboveUsd": 0.02,
    "onEstimateUnavailable": "deny",
    "onLedgerUnwritable": "deny"
  }
}
```

Enforcement sequence at the call site, before any HTTP request:

```
estimate() ──► exceeds perRequest / perAsset / perSession?  ──► 402, no call
     │  estimate unavailable? ──────────────────────────────► 402, no call  (fail closed)
     ▼
reserve(estimate) in the ledger; ledger unwritable? ────────► 402, no call
     ▼
call with Idempotency-Key = sha256(model|quality|size|n|prompt|refSha)
     ▼
on success: reconcile reserved → actual from response.usage
on timeout/error: KEEP the reservation (assume charged) until reconciled
```

That last line is the important one. On an ambiguous failure the ledger must assume the money was spent, not assume it was not. The current code assumes the opposite by doing nothing.

### 6.5 Caching and idempotency

Cache key: `sha256(model | quality | size | n | resolvedPrompt | referenceImageSha256)`.

- Store under `workspace/_concepts/_cache/<key>/` with the images, the `usage` block, and the estimate.
- A cache hit returns instantly with `cost: 0.00` and `cacheHit: true` recorded in the run metadata.
- Send the same digest as `Idempotency-Key` so a network-level retry inside the provider's window returns the original result rather than a new billed generation.
- Cache invalidation is by key only — never by time. Prompts are cheap to re-hash; regenerating is not.

This directly answers question 7: identical prompt + identical settings + identical reference should cost **nothing** on the second run. Today it costs full price.

### 6.6 Retry policy

- Retry only `429` and `5xx`, max 2 attempts, exponential backoff with jitter.
- **Never** retry `image_generation_user_error` — the guide is explicit that these need a changed request, and the `moderation_blocked` code carries `moderation_details` worth surfacing to the user.
- Every attempt increments an attempt counter in the ledger and is separately estimated. A retry that would breach the budget is refused.
- Timeouts count as *possibly charged* and are reconciled manually, not retried automatically.

### 6.7 What to write into the job record

```json
"imageGeneration": {
  "stage": "beauty_explore",
  "model": "gpt-image-2", "quality": "low", "size": "1536x1024", "n": 2,
  "estimatedUsd": 0.010, "estimateSource": "official_table", "pricingRetrieved": "2026-07-30",
  "actualUsage": { "input_tokens": 0, "output_tokens": 0, "total_tokens": 0 },
  "actualUsd": 0.0102, "reconciled": true,
  "cacheHit": false, "idempotencyKey": "sha256:…", "attempts": 1,
  "requestId": "req_…", "cumulativeAssetUsd": 0.010
}
```

No API key, no `Authorization` header, no raw request body. `requestId` is the safe correlator for support.

### 6.8 UI

Per-stage: estimated cost shown **before** the button is enabled, button disabled when the estimate exceeds the cap, and a running "this asset so far: $0.xx / $0.50" strip. After the call, replace the estimate with the reconciled actual and flag any divergence above 10% — a persistent divergence means the price table is stale.

### 6.9 Tests (no-charge regression suite)

- `image_pricing` table tests: every documented cell, plus `pytest.raises` on unknown combinations.
- Mocked `requests.post` returning canned `data` + `usage`; assert the ledger reconciles.
- Budget-gate tests: over-cap estimate → 402 and **assert the transport was never called** (`mock.assert_not_called()` is the real assertion here).
- Fail-closed tests: unknown model, unwritable ledger → 402, no call.
- Idempotency test: identical inputs twice → one transport call, second is `cacheHit`.
- Timeout test: transport raises → reservation retained, status `possibly_charged`.

None of these spend money, and together they make it structurally hard for a future change to reintroduce an unguarded call site.

---

# TRACK B — Post-2.5D Mesh Architecture

## 7. What the current generator actually is

```
authority PNG
   │  _rgba_and_mask()      alpha, else corner-colour distance (threshold 28)
   ▼
   mask ── _largest_component() ── _fit_authority() ──► 160×160 grid (WORK_GRID_SIZE)
   │
   ▼  _height_field()   authority_mesh.py:218
   distance = _distance_inside(mask)            # pure-Python double loop
   broad_hull = (distance/max)**0.58
   values = 0.10 + 0.62*broad_hull + 0.10*luminance + 0.16*orange
   values = smooth(values, 3); values = (values + fliplr(values))/2
   │
   ▼  _build_mesh()     authority_mesh.py:281
   top    z = corners[y,x]        (single-valued height field)
   bottom z = -0.12               ← CONSTANT, line 289
   sides  vertical quads wherever the mask ends
```

So the representation is: **a single-valued height field over the planform, sitting on a flat plate, joined by vertical walls.** Everything the user observed follows from those three sentences.

## 8. Findings — Track B

### HIGH

---

#### MBS-70 — `componentCount` is a hardcoded `1` feeding a gate that checks `<= 1` **[probe]**

`authority_mesh.py:513` — `component_count = 1` — is a literal. It flows to `_gate_results()` where `"components": component_count <= ACCEPTANCE_GATES["componentCountMax"]` (`:501`), i.e. `1 <= 1`, and into the report as `mesh.componentCount` (`:578`). **The gate cannot fail.**

The review request cites "connected components: 1" among the evidence of a good result. I measured it independently:

```
reported componentCount : 1
MEASURED body_count     : 1     (trimesh.split)
MEASURED euler_number   : 2
```

So the value is *true* — but it is asserted, not measured, and the user is relying on it as evidence. This is precisely the pattern MBS-27 and MBS-50 were raised about, reappearing in a new module. `trimesh` is already imported and already loads the mesh three times; `len(loaded_mesh.split(only_watertight=False))` is one line.

The same audit should extend to `_edge_audit`, which computes boundary/non-manifold counts from the face list rather than from the reloaded mesh. Those two happen to agree here; measuring both and asserting agreement is the durable form.

---

#### MBS-71 — The 2.5D ceiling, quantified on the delivered interceptor **[probe]**

Loaded `source/generated/authority_generated_mesh.glb` and measured in the target frame:

| Measurement | Value |
|---|---|
| Vertices on the single plane z = −0.12 | **8 015 / 16 030 = 50.0%** |
| Distinct z values below zero | **1** (exactly −0.12) |
| Surface area exactly downward-facing (flat belly) | **31.6%** |
| Surface area within 3° of vertical (extrusion wall) | **30.6%** |
| **Combined belly + wall** | **62.2% of total surface** |
| Wall height at the thinnest edge | 0.2259 units = **4.11% of the 5.5-unit planform**, uniform around the entire silhouette |
| Thinnest : thickest section | 1 : 3.77 |
| Top-surface z std / range | 0.141 / 0.626 |
| height / planform | 0.1675 |
| `euler_number` | **2** → genus 0 |

Reading these back to the user's observations:

- *"vertically extruded swept-wing edges"* — the 0.2259 wall. It is `0.10` (the constant floor in `values = 0.10 + …`) plus `0.12` (`bottom_z`). It appears at **every** silhouette edge, identically, because both terms are constants.
- *"uniform wing and tail thickness"* — the belly is one plane, so thickness is entirely determined by the top field, whose 5th–95th percentile spread is only 0.173→0.638.
- *"flat wingtip pylons"* — `broad_hull = distance^0.58` with an exponent below 1 rises steeply from the edge then flattens; anything narrow is pinned near the floor.
- *"cockpit and engine mass conveyed mainly by texture/height"* — see MBS-72.
- *"weak general 3D credibility"* — 62.2% of the surface is a construction artifact.

`euler_number = 2` is the structural statement: **genus 0, no through-holes, anywhere, ever.** A height field over a plane cannot express a gap between wing and fuselage, an intake tunnel, a canopy undercut, or a separated nacelle. No parameter tuning changes this.

---

#### MBS-72 — Geometry is partly derived from albedo, so repainting the ship reshapes it **[read]**

`authority_mesh.py:228`:

```python
values = 0.10 + 0.62 * broad_hull + 0.10 * luminance + 0.16 * orange
```

`luminance` is image brightness; `orange` is a hardcoded two-term chroma heuristic (`:224-226`) that fires on saturated orange — an engine-glow detector by construction. Together they contribute up to **26% of the height budget from paint rather than form**.

Two consequences worth stating plainly:

1. **The same craft in a different livery is a different mesh.** A darker repaint flattens it. That breaks the project's own identity-anchor premise, because the anchor is supposed to be the *planform*, not the paint.
2. **The 0.16 orange term is a silent semantic classifier** — an unlabelled, uncalibrated part detector. It is doing the job that MBS-CR-0005's Track B recommendation says should be done explicitly by segmentation, but without a name, a threshold justification, or a record in the report.

Albedo belongs in the texture (where it already correctly goes, `:521`). It should not be in the geometry.

---

#### MBS-73 — The height gate is not the binding constraint; raising it will not help **[probe]**

`ACCEPTANCE_GATES["heightToPlanformRatioMax"] = 0.45`. The interceptor measures **0.1675** — it uses 37% of its permitted height budget. Reported as `blenderImportHeightToPlanformRatio: 0.16747664`.

I flag this because it is the obvious wrong fix. The craft is not flat because a gate is stopping it; it is flat because `0.10 + 0.62·d^0.58` produces a shallow dome and the belly is a plane. Relaxing 0.45 → 0.7 changes nothing. The constraint is the representation.

(As a cross-check against MBS-57 from CR-0004: the frame envelope tolerated ratios up to ~0.575, so there is headroom in the camera frame too. Neither gate is binding.)

---

### MEDIUM

---

#### MBS-74 — Grid resolution and an O(n²) Python loop cap thin-feature survival **[read/probe]**

`WORK_GRID_SIZE = 160`. A wingtip 3 px wide at 160×160 is three quads across, and after `_smooth(passes=3)` it is essentially gone. This is the direct mechanism behind "will not be adequate for more delicate winged craft" — the grid, not the algorithm, sets the floor.

`_distance_inside` (`:163-196`) is a pure-Python double loop over the grid, twice. It is the dominant cost in an 85-second test suite. `scipy.ndimage.distance_transform_edt` is one call and would make a 512×512 grid cheaper than the current 160×160. Raising resolution is otherwise free of risk, and it is a prerequisite for any thin-feature work.

---

#### MBS-75 — Bilateral mirroring assumes perfect centring in the authority image **[read]**

`values = (values + np.fliplr(values)) * 0.5` (`:231`) mirrors about the *image* column centre, not about a measured symmetry axis. `_fit_authority` centres the bounding box, so a craft whose mass is asymmetric within a symmetric bbox — or which is rendered a few degrees off-axis — gets its features smeared across the centreline rather than sharpened. The comment says geometry "should be stable and bilaterally balanced even when painted detail is not," which is a reasonable goal achieved by a fragile means. Detect the symmetry axis (principal axis of the mask) and mirror about *that*, and record the detected axis and the pre/post mirror residual in the report so a bad fit is visible.

---

## 9. Post-2.5D architecture recommendation

### 9.1 Target architecture

```
             approved beauty concept (S2)
                       │
        ┌──────────────┴───────────────┐
        ▼                              ▼
  APPROVED TOP-DOWN AUTHORITY     GOVERNED MULTIVIEW SET
  (hard identity anchor,           front / left / back
   never provider-generated)       (derived, advisory)
        │                              │
        │                              ▼
        │                    ┌─────────────────────┐
        │                    │  PROVIDER ADAPTER   │  ← provider-neutral contract
        │                    │  meshy | hunyuan |  │
        │                    │  local-deterministic│
        │                    └──────────┬──────────┘
        │                               │ raw GLB
        │                               ▼
        │                    ┌─────────────────────┐
        └───────────────────►│ AUTHORITY PROJECTION│  hard silhouette constraint:
                             │   CONSTRAINT        │  clamp/warp planform to authority
                             └──────────┬──────────┘
                                        ▼
                             ┌─────────────────────┐
                             │ DETERMINISTIC CLEAN │  orient, scale, remesh, weld,
                             │   (existing gates)  │  manifold repair, LOD, UV
                             └──────────┬──────────┘
                                        ▼
                             existing coordinate contract + gate suite
                                        ▼
                             normalized.glb / review package
```

The key structural point: **the authority stays outside the provider.** The provider proposes side and vertical geometry; the authority governs the planform. That is how a neural provider can invent volume without being permitted to invent identity.

### 9.2 Explicit recommendation per route

| Route | Recommendation | Reasoning |
|---|---|---|
| **Meshy Multi-Image to 3D** | **BUILD FIRST** | Hosted; no GPU; accepts 1–4 images which matches the governed view set exactly; returns GLB. Decisive for us: it has a **sample API key that consumes no credits** and returns a fixed sample result, so the entire adapter can be built and tested at **zero spend**; failed tasks auto-refund (`consumed_credits: 0`); `alpha_thumbnail` returns an RGBA preview and `multi_view_thumbnails` returns front/right/back/left renders — those are *exactly* the artifacts our evaluation schema needs, for free. ~20 credits/task (30 with texture); at Pro-tier rates (1 000 credits / $20) that is **≈$0.40–0.60 per candidate**. |
| **Hunyuan3D-2mv** | **DEFER to a CUDA cloud sidecar; do not attempt locally first** | Official example is `device='cuda'`. Shape generation needs roughly 6 GB VRAM (community "GPU-poor" forks claim 6 GB at profile 4; the mini variant ~5 GB). Apple-Silicon/MPS is not the documented path and third-party claims of M-series compatibility are unverified. A rented GPU hour is a cheaper and fairer test than days of local porting. Also: outputs can reach ~600k triangles, so retopology is mandatory before our `triangleCountMax: 180000` gate. Licence terms restrict use in some jurisdictions and must be reviewed before any output is shipped. |
| **Hunyuan3D 2.1** | **DEFER** | Same hosting constraints, plus a separate PBR texture stage we do not need yet. Revisit only if 2mv geometry wins on quality and texture becomes the gap. |
| **Training / fine-tuning a foundation model** | **REJECT** | Nothing in the evidence requires it. It would replace a game project with a research project. |
| **Local deterministic improvement** | **BUILD IN PARALLEL — highest value per unit effort** | See 9.3. |

### 9.3 The cheapest large improvement is local, and should happen regardless

Before any provider, one change removes the two most visible defects:

**Replace the constant `bottom_z = -0.12` with a second height field.**

```python
top_z    = +f_top(distance, part_class)
bottom_z = -f_bottom(distance, part_class)      # currently the constant -0.12
```

This alone:

- deletes the flat belly (**31.6% of surface area** becomes sculpted),
- collapses the uniform 0.2259 vertical wall toward a true tapered edge (**another 30.6%**),
- turns wings into lens sections — thin at the tip, thick at the spine — which is the actual complaint,
- keeps the top-down silhouette **bit-identical**, so every existing gate still passes unchanged,
- requires no provider, no GPU, no new dependency, and is unit-testable.

Then, in order of value:

1. **Part segmentation from the authority** (fuselage / wing / nacelle / canopy / pylon) driving per-part profile exponents and thickness scales. This replaces the global `^0.58` and, importantly, **retires the `0.16 * orange` heuristic** (MBS-72) with a named, recorded classifier.
2. **Drop `luminance` and `orange` from geometry entirely.** Albedo → texture only.
3. **Raise `WORK_GRID_SIZE` to 384–512 and vectorize the distance transform** (`scipy.ndimage.distance_transform_edt`). Faster *and* higher resolution. Prerequisite for thin features.
4. **Symmetry-axis detection** instead of `fliplr` about the image centre (MBS-75).
5. **Multi-contour extrusion** for genuinely separated features — the only local route to non-genus-0 topology, and the point at which the local approach stops being cheap. This is the natural handoff line to the neural provider.

My honest assessment: steps 1–4 will close most of the visible gap for the fixed camera at 96/64 px, at a fraction of the cost and risk of a provider integration. The provider earns its place at step 5 and beyond — separated engines, canopy undercuts, wing-fuselage gaps — which is exactly where "delicate winged craft" live.

### 9.4 Multiview reference contract

Answering question 4: **top (authority) + front + left + back**, with the top **never** provider-generated.

```json
{
  "schemaVersion": "skyforge.multiview-set.v1",
  "identityAnchor": { "view": "top", "source": "approved_authority",
                      "sha256": "…", "governed": true, "mutable": false },
  "derivedViews": [
    { "view": "front", "sha256": "…", "source": "composite_sheet_quadrant_1" },
    { "view": "left",  "sha256": "…", "source": "composite_sheet_quadrant_2" },
    { "view": "back",  "sha256": "…", "source": "composite_sheet_quadrant_3" }
  ],
  "consistencyChecks": {
    "singleCraftPerPanel": true, "aspectAgreementWithAuthority": 0.031,
    "spanAgreement": 0.024, "panelBackgroundUniform": true
  }
}
```

On question 9 (composite sheet vs independent calls) — the arithmetic favours independent calls, but I recommend the sheet anyway, with a gate:

| Approach | Cost | Trade-off |
|---|---:|---|
| 4 independent (mini/low/1024) | $0.020 | Cheaper; views may disagree with each other |
| One 2×2 composite (gpt-image-2/medium/1024) | $0.053 | One generation → mutually consistent views; but each panel is only 512×512, and the guide lists "Composition Control" as a known limitation |

Inconsistent views are worse than expensive views for multiview reconstruction — a provider fed three mutually contradictory profiles will confidently produce a wrong ship. So: generate the composite sheet, then **gate it locally** (one craft per quadrant, consistent span and aspect against the authority, uniform background) and fall back to independent per-view edits when the gate fails. Record which path was taken. The $0.033 difference is irrelevant next to a wasted 20-credit Meshy task.

### 9.5 Provider adapter contract

```python
class MeshProvider(Protocol):
    id: str; version: str
    def estimate(self, request: MeshRequest) -> ProviderEstimate: ...
    def submit(self, request: MeshRequest) -> ProviderJob: ...      # idempotency key required
    def poll(self, job: ProviderJob) -> ProviderStatus: ...
    def fetch(self, job: ProviderJob) -> ProviderResult: ...        # raw GLB + provenance
```

Non-negotiables, carried from the existing gate discipline:

- Provider output enters as **raw**, is normalized through the **same** `TARGET_TO_GLTF` / `GLTF_TO_BLENDER` contract, and must report the same `blenderImportBoundsDelta ≤ 1e-5`.
- Provenance (`provider`, `model`, `version`, `licence`, `licenceUrl`, `taskId`, `consumedCredits`, `retrievedDate`, `approvedForDistribution: false`) is **required** — the same hard precondition MBS-11 established for the image stage.
- Cost governance from Track A applies unchanged: estimate → budget gate → idempotency → reconcile.
- The **local deterministic generator stays as a first-class provider** (`id: "skyforge.authority-extrusion"`), so Experiment 02 compares like with like through one code path.

### 9.6 Evaluation schema — what should supplement top-down IoU

Top-down IoU is now saturated (0.948 / 0.953 / 0.956) and can no longer discriminate. It measures the one thing the current generator is guaranteed to get right. Add:

| Metric | Definition | Why |
|---|---|---|
| `multiviewReprojectionIoU` | IoU of rendered front/left/back against the governed derived views | The direct test of side geometry; Meshy's `multi_view_thumbnails` supplies the comparison renders free |
| `flatBellySurfaceFraction` | Fraction of surface area within 3° of downward-facing | **Interceptor baseline: 0.316.** Single best discriminator against 2.5D |
| `verticalWallSurfaceFraction` | Fraction within 3° of vertical | **Baseline: 0.306** |
| `sectionThicknessRatio` | thinnest : thickest cross-section | **Baseline: 1 : 3.77** |
| `genus` / `eulerNumber` | Topological genus | **Baseline: genus 0.** Non-zero genus proves real separated features |
| `partSeparationCount` | Connected components before manifold merge | Wings/engines as distinct volumes |
| `thinFeatureSurvival` | Fraction of authority features < 4 px wide present in the mesh | The "delicate wings" test |
| `heightToPlanformRatio` | existing | **Baseline: 0.1675** |
| `cleanupMinutes` | human-recorded | Already in `review.json` |
| `costUsd` / `latencySeconds` | per candidate | Provider viability |

The first five give Experiment 02 numbers that *can* separate the routes, which top-down IoU cannot.

---

## 10. Experiment 02 specification

**Question:** does a neural multiview provider, constrained by the approved top-down authority, produce materially better side volume and thin-feature survival than the deterministic route — at acceptable cost, latency and cleanup?

**Controlled input:** the **same approved interceptor authority** (`authority_01.png`, sha256 `8eb3b788…a782f`) already used for the accepted baseline. One authority, one profile, one camera pitch (20°), one bank (±18°).

### Comparison matrix

| # | Route | Inputs | Provider cost | Notes |
|---|---|---|---|---|
| **R0** | Deterministic 2.5D (v0.5.1) | authority only | $0.00 | **Accepted baseline — already measured** |
| **R1** | Deterministic two-sided height field | authority only | $0.00 | §9.3 step 1; the honest local ceiling |
| **R2** | Meshy Multi-Image (adapter dry run) | 4-view set | **$0.00** | Sample API key; validates adapter, contract and gates with zero spend |
| **R3** | Meshy Multi-Image, untextured | top+front+left+back | ~$0.40 | 20 credits |
| **R4** | Meshy Multi-Image, textured | top+front+left+back | ~$0.60 | 30 credits; tests whether PBR helps at 64 px |
| **R5** | Meshy Multi-Image, top-only | authority only | ~$0.40 | Isolates the value of the derived views |
| **R6** | Hunyuan3D-2mv on rented CUDA | front/left/back | ~$1–3 GPU-hour | **Only if R3/R4 fail the identity gate or licensing is unacceptable** |

**Total to a decision: R0–R5 ≈ $1.40 plus one $0.053 multiview sheet — under $1.50.** That is roughly two of the old beauty rounds.

Run R2 before spending anything. Run R6 only on a stated trigger.

### Acceptance

A route beats the baseline only if it improves **at least three** of `multiviewReprojectionIoU`, `flatBellySurfaceFraction`, `sectionThicknessRatio`, `thinFeatureSurvival`, `genus` — while holding `blenderImportSilhouetteIoU ≥ 0.94` against the authority and `cleanupMinutes ≤ 20`. Silhouette fidelity is not tradeable; it is the identity anchor.

### Stop conditions

- **Stop pursuing a provider** when two consecutive candidates require remodelling rather than cleanup after orientation has been ruled out, or when constraining output to the authority silhouette destroys the volume that motivated using it. (That last one is the specific failure to watch: a hard planform clamp applied to a mesh that disagrees with the authority is the 3D analogue of the planform-conform laundering problem — a warrant check is needed before clamping, not after.)
- **Stop pursuing local reconstruction** when a required feature is genuinely non-genus-0 and multi-contour extrusion has failed twice.
- **Stop the whole line** if R1 alone satisfies the gameplay bar at 96/64 px. That is a legitimate and cheap outcome, and it should be treated as success rather than as an argument for continuing.

---

## 11. Prioritised action list

### P0 — before any further paid API call

| ID | Item |
|---|---|
| MBS-62/64 | Cost ledger: estimate → budget gate → idempotency key → `usage` reconciliation, fail-closed |
| MBS-61/63 | Economy defaults (`gpt-image-2` low 1536×1024 n=2); expose `quality`; record it in metadata |
| MBS-65 | Timeout treated as *possibly charged*; no automatic retry; reservation retained |
| MBS-66 | `from typing import Any`; confirm `ruff check .` exits 0 and the preflight reaches pytest |
| MBS-67 | Fix the two failing tests; stop predicting green for unverified environments |

### P1 — the v0.6 epoch

| ID | Item |
|---|---|
| MBS-70 | Measure `componentCount` and the edge audit from the reloaded mesh; assert agreement |
| §9.3-1 | Two-sided height field (removes flat belly and vertical walls) |
| §9.3-3 | `distance_transform_edt`; raise `WORK_GRID_SIZE` to 384–512 |
| MBS-72 | Remove `luminance` and `orange` from geometry |
| §9.5 | Provider adapter contract + Meshy adapter, developed against the free sample key |
| §9.4 | Multiview reference contract with local consistency gate |
| MBS-68/69 | Keychain argv exposure; validate before allocating job state |

### P2

`§9.3-2` part segmentation · `§9.3-4` symmetry-axis detection · `§9.6` full evaluation schema · `§9.3-5` multi-contour extrusion · Hunyuan CUDA sidecar (trigger-gated) · MBS-73 revisit the height gate *after* the representation changes · MBS-74 suite runtime

---

## 12. Instructions to Sol for the next implementation package

1. **Ship v0.5.2 as a cost-only hotfix first.** Do not bundle geometry work with it. It should contain: the `Any` import fix, the two test corrections, `common/image_pricing.py` with the official table and its retrieval date, the estimator, the fail-closed budget gate, the content-hash cache, idempotency keys, `usage` capture and reconciliation, and the economy defaults. Nothing else.

2. **Prove the budget gate with a no-charge suite.** The critical assertion is `mock_transport.assert_not_called()` on the over-budget path. A budget gate that has only been tested by observing it *allow* a call has not been tested.

3. **Record `quality` in `metadata.json`.** It is the dominant cost variable and it is currently invisible in the provenance record.

4. **Do not touch `gpt-image-1` defaults incrementally — change the model.** Staying on `gpt-image-1` at `low` still costs more than `gpt-image-2` at `low`. The model choice is the larger lever.

5. **Then v0.6.0, geometry, in this order:** two-sided height field → vectorized distance transform + higher grid → remove albedo terms from geometry → measured `componentCount`. Each with the existing gate suite unchanged, so any silhouette regression is caught immediately.

6. **Build the Meshy adapter against the free sample API key and merge it before spending a single credit.** The adapter, the provenance block, the budget integration and the gate wiring can all be completed at zero cost. Only then run R3.

7. **Report `flatBellySurfaceFraction`, `verticalWallSurfaceFraction`, `sectionThicknessRatio` and `genus` for every mesh from now on**, including regenerated baselines. The interceptor's values (0.316 / 0.306 / 3.77 / genus 0) are the numbers every future route must beat, and they should appear in the report before the comparison starts, not after.

8. **In the next resolution document, give every finding an explicit disposition** — including any you reject, and why. MBS-17 went undispositioned in RES-0002 and MBS-46 regressed in this release; both would have been caught by a complete disposition table.

---

## 13. Closing assessment

The interceptor is a real milestone and the numerical gates behind it are sound. The identity anchor works: silhouette IoU of 0.956 against the authority, a bounds delta of 4.8e-08 through the coordinate contract, watertight and winding-consistent on independent reload. None of that is in question.

What the evidence shows is that the project has reached the edge of what its representation can express, and has reached it cleanly — with measurements good enough to prove where the edge is. **62.2% of the delivered mesh surface is construction artifact rather than design**, and no parameter in `_height_field` can change that, because the limit is that `z` is single-valued over the planform and the belly is a constant.

The cost problem is the more urgent of the two and by far the easier. It is not that the workflow is expensive; it is that **nothing in the system knows what anything costs**. There is no estimate, no cap, no cache, no idempotency, and the API's own report of what was billed is discarded on arrival. Fixing the defaults saves 75×; building the ledger is what stops the next surprise. Given how consistently this review lineage has landed on the same principle — a value that can be measured should not be asserted — it is worth noting that `usage` is sitting unread in every response the sidecar has ever received.

On geometry, my recommendation is deliberately unfashionable: **spend a day on the two-sided height field before spending a dollar on a provider.** It removes the two defects the user actually named, keeps every existing gate green, and gives Experiment 02 a baseline that represents the local route at its best rather than at its current floor. If a neural provider then wins, it will have won against a fair opponent — and if it does not, that is a much better outcome than it sounds.
