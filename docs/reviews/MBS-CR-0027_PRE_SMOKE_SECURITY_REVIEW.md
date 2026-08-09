# MBS-CR-0027 — v0.8.1 Pre-Smoke Security Review (No-Spend Preauthorization)

**Review identifier:** MBS-CR-0027
**Date:** 4 August 2026
**Reviewer:** Claude (independent adversarial reviewer)

| Item | Value |
|---|---|
| Repository | `martyhlavacek/SkyForge-Mesh-Builder` |
| Candidate commit | `5cdc698258e71438ea21f71648f37de854e78e08` |
| Prior reviewed candidate | `dbcad7f2898c1360f2bc50a21c34ec89eb3b3f78` (MBS-181 remediation) |
| Accepted baseline / tag | `d38dd5d1638eae0942929a4ed568edb048220894` / `v0.7.1-accepted-baseline` |
| Producer binding | 317 / `2f2a3a43e7a92aad0e413db131e9896ab019cf0c77137de45a89ba013a95132b` |
| Import Probe binding | 64 / `883510570c572ada2166019b356bfbefd3e7053c5074553d1c1dde1234d74ba7` |
| Evidence ZIP | `f92e653c5b94ce3aee5065eda8358aa65c53e31274c7b5826280b3412a2e7324` |

---

## Executive verdict

> ## **ACCEPT**
>
> The candidate is **ready for the separate authority-bundle and explicit-authorization gates.**
>
> This does **not** authorize a live Meshy operation, paid work, credit consumption, merge, tag,
> release, or visual testing. No live smoke task is authorized by this review.

I independently re-verified the Meshy contract against live official documentation and every
committed assumption is accurate, including the 20-credit geometry-only price and the
`assets.meshy.ai` artifact hostname. Production now approves **exactly** `assets.meshy.ai` through
the real operating-system resolver and rejected all 21 unsafe host classes I constructed. DNS
enforcement fails closed on all 11 hostile resolution cases, including a **mixed** global/private
result. The preflight is provably byte-free, key-free and submission-free — it uses HEAD only,
strips fragments, and redacts signed query values. The dry-run projection is genuinely unsendable.
All MBS-181 protections, POST authorization, duplicate-spend controls, redaction, v0.7.1
preservation and subsystem isolation remain intact.

One observation is raised (**MBS-184**) about synthetic DNS values in one evidence file. It is
correctly labelled offline and does not affect the verdict.

I did not modify the repository, use an API key, or execute any provider operation.

---

## Scope and method

Fresh clone into an empty directory, detached checkout at the exact candidate, the complete
`dbcad7f2..5cdc6982` diff inspected, both bindings recomputed, all local gates re-run, and direct
adversarial probing with injected stub resolvers and spy transports. Codex's report was treated as
claim. The Meshy contract was re-verified by fetching the live official documentation — a read of
public docs, not an API call, requiring no key and consuming nothing.

**Evidence classification.**

- **Independently reproduced:** provenance and bindings; the focused diff; v0.7.1 and subsystem
  preservation; Producer Ruff and collection; focused reconstruction and preauthorization suites;
  Import Probe Ruff, pytest and historical comparison; the 22-case host matrix; the 11-case DNS
  matrix; 10 preflight redirect/redaction cases; the 15-case MBS-181 kill-switch matrix; 12 POST
  authorization and duplicate-spend cases; evidence manifest (8/8) and secret scan; bundle-absence.
- **Inspected but not reproduced:** the GitHub Actions runs cited in prior evidence — I have no
  GitHub API access, though their substance is covered by local execution.
- **Could not be verified:** live provider behaviour and actual DNS records for `assets.meshy.ai`
  (deliberately not resolved — see MBS-184); the full 354-test producer suite was collected but I
  ran the focused subsets rather than the whole suite in this pass, having reproduced the full
  suite at the two immediately preceding commits.

**Recorded deviation:** Python 3.11 unavailable; clean from-contract-only Python 3.12 used.
`requirements.txt` unchanged from the accepted v0.7.1 contract.

---

## Provenance and diff

| Check | Result |
|---|---|
| HEAD after detached checkout | `5cdc698258e71438ea21f71648f37de854e78e08` — **exact match** |
| Working tree | **clean** — 0 modified or untracked |
| Accepted tag | → `d38dd5d1638eae0942929a4ed568edb048220894` — **unchanged** |
| MBS-181 candidate `dbcad7f2…` | **is an ancestor** |
| Evidence ZIP vs uploaded sidecar | `f92e653c…2a2e7324` — **match**, equals the request value |
| Producer binding | **verified: True**, 317, `2f2a3a43…3a95132b` |
| Import Probe binding | **verified: True**, 64, `88351057…34d74ba7` (unchanged) |

**Diff from the MBS-181 candidate — 16 files.** Two source additions
(`app/reconstruction_v1/preflight.py`, `scripts/preflight_meshy_artifact_url.py`), one source
modification (`app/reconstruction_v1/provider.py`), one new test module, the binding, and eleven
documentation/evidence files. A grep for `geometry_v2`, `import-probe/`, `vmp`, `server`,
`pipeline` and `BASELINE_LOCK` across the diff returns **nothing**.

---

## 1. Meshy contract snapshot — independently re-verified

I fetched the live official documentation and compared it to
`docs/contracts/MESHY_CONTRACT_REVERIFICATION_2026-08-04.md`. **Every committed assumption is
accurate:**

| Committed claim | Live documentation | |
|---|---|---|
| Create `POST /openapi/v1/multi-image-to-3d` | confirmed | ✔ |
| Retrieve `GET /openapi/v1/multi-image-to-3d/:id` | confirmed | ✔ |
| 1–4 images, `.jpg`/`.jpeg`/`.png` | *"Provide 1 to 4 images… we currently support .jpg, .jpeg, and .png"* | ✔ |
| Public URL **or** Data URI input | both documented explicitly | ✔ |
| `ai_model: meshy-6` | available values `meshy-5`, `meshy-6`, `latest` | ✔ |
| `should_texture: false` | default true; false skips texture phase | ✔ |
| `should_remesh: false` | default false for meshy-6; false returns highest-precision triangular mesh | ✔ |
| `image_enhancement: false` | **default true**; false preserves exact input appearance; only supported on meshy-6/latest | ✔ |
| `auto_size: false` | default false | ✔ |
| `target_formats: ["glb"]` | glb among available values | ✔ |
| Bearer authentication | `Authorization: Bearer ${YOUR_API_KEY}` | ✔ |
| **20-credit** geometry-only estimate | Pricing: *Multi Image to 3D — Meshy-6 models: **20 credits (without texture)*** | ✔ |
| Three-day non-Enterprise retention | consistent with the retention page verified in MBS-CR-0018 | ✔ (carried) |
| Initial artifact hostname `assets.meshy.ai` | every `model_urls.glb` example is `https://assets.meshy.ai/…?Expires=***` | ✔ |

Two points worth recording. First, `image_enhancement` defaults to **true** — the candidate
explicitly sets `false` on `meshy-6`, which is exactly the MBS-108 authority-integrity control and
is only available because meshy-6 was chosen. Second, the documented artifact URLs carry signed
`?Expires=***` query strings, which is precisely why the preflight's query redaction matters.

The snapshot's own closing statement — that any future material difference must fail closed and
that the documentation does not authorize unknown redirect hosts — is a correct and appropriately
conservative reading.

---

## 2. Production host policy — exactly `assets.meshy.ai`

`DEFAULT_ARTIFACT_HOST_POLICY` now carries
`contract_version = "skyforge.meshy-artifact-hosts.2026-08-04.v1"`,
`approved_hosts = frozenset({"assets.meshy.ai"})`, and
`address_resolver = operating_system_address_resolver`. I confirmed by identity that the resolver
**is** the OS function, which calls `socket.getaddrinfo(hostname, 443, SOCK_STREAM)` and returns
both address families, deduplicated and sorted, with no caching of trust.

**22-case host matrix — 0 mismatches:**

| Accepted | Rejected |
|---|---|
| exact `assets.meshy.ai` | `api.meshy.ai` (not the artifact host) |
| explicit `:443` | `meshy.ai` apex |
| uppercase host (case-folded) | `evilassets.meshy.ai` (deceptive suffix) |
| signed query preserved | `assets.meshy.ai.evil.com` (deceptive prefix) |
| | `cdn.assets.meshy.ai` (subdomain) |
| | `assets.meshy.ai.` (trailing dot) |
| | arbitrary host, HTTP scheme |
| | port 8443, port 80 |
| | embedded credentials |
| | IPv4 literal, IPv6 literal |
| | `localhost`, `x.localhost` |
| | missing host, malformed, empty |

Membership is exact after case-folding — neither `startswith` nor `endswith` — so every deceptive
variant fails. Notably `api.meshy.ai` is rejected: the API endpoint host is deliberately **not** an
approved artifact host.

**DNS enforcement — 11 cases, all fail closed:**

| Resolution | Result |
|---|---|
| all global (IPv4 + IPv6) | accepted |
| empty | rejected — resolved to no addresses |
| private `10/8` | rejected — non-public |
| loopback `127.0.0.1` | rejected — non-public |
| link-local `169.254.169.254` (cloud metadata) | rejected — non-public |
| IPv6 ULA `fd00::1` | rejected — non-public |
| reserved `240/4` | rejected — non-public |
| **mixed global + private** | **rejected** — every address must be global |
| malformed address string | rejected — resolution malformed |
| resolver absent (`None`) | rejected — resolution policy unavailable |
| resolver raises | rejected — resolution failed |

The mixed case is the important one: a single non-global address in a multi-record answer is
sufficient to refuse, which defeats DNS-rebinding style answers that mix a legitimate address with
an internal one.

---

## 3. Preflight — no bytes, no key, no task

`preflight_artifact_url` is a module-level function that takes a policy and an **optional**
transport. With `transport=None` — which is what the CLI `preflight_meshy_artifact_url.py` uses —
it performs **zero network calls** and returns a decision from policy validation alone.

| Property | Verified |
|---|---|
| HTTP method used | **HEAD only** — never GET or POST |
| Artifact bytes read | **none** — no content field anywhere in the report |
| Network calls with `transport=None` | **0** |
| References to `submit_task` | **none** in source |
| References to `poll_until_terminal` | **none** |
| References to `download_artifact` | **none** |
| References to `api_key` / `Authorization` / `Bearer` / `SubmissionAuthorization` | **none** |

It is therefore structurally impossible for the preflight to submit a task, poll a task, download
artifact bytes, read a Meshy key, or consume credits.

**Redaction.** Given a URL carrying a signed query and a fragment, the report emitted
`https://assets.meshy.ai/task/abc.glb?<redacted>` — the signature value, the credential value, the
parameter *names* and the fragment are all absent. Redirect metadata records only hostname, path
and a `queryRedacted` boolean; a signed redirect target did not leak its query value. A malformed
URL yields `<malformed-url-redacted>` rather than echoing input.

**Preflight redirect safety — 10 cases:**

| Case | Decision | Transport calls |
|---|---|---|
| 200 on approved host | ALLOW | 1 |
| Redirect to evil host | REFUSE | 1 |
| Redirect to IP literal | REFUSE | 1 |
| Relative redirect within approved host | ALLOW | 2 |
| **Final `response.url` mutated to evil host** | **REFUSE** | 1 |
| Redirect with no `Location` | REFUSE | 1 |
| Redirect loop > 4 | REFUSE — limit exceeded | 5 |
| HEAD returns 403 | REFUSE | 1 |
| **Unapproved initial URL** | **REFUSE** | **0** |
| Signed redirect target | ALLOW, query redacted, no leak | 2 |

An unsafe initial URL is refused before any transport at all.

---

## 4. MBS-181 and original controls — regression check

**Kill switch, 5 operations × 3 indicators = 15 cases, all blocked, total transport attempts: 0.**
`submit_task`, `get_task`, `poll_until_terminal`, `download_artifact` and `download_artifacts` each
refuse under `SKYFORGE_PROVIDER_NETWORK_DISABLED=1`, `CI=true` and `GITHUB_ACTIONS=true`.

**POST authorization — 8 controls all blocked pre-transport with 0 network attempts:**
`paid_enabled=False`, `paid_enabled=1`, digest mismatch, `maximum_credits=19`,
`maximum_credits=True`, `api_key=None`, `prior_task_id` set, `submission_registry=None`. The
authorized control reached transport.

**Duplicate spend:** first submission reached transport; **second submission with the same digest
and registry blocked**; **restart replay blocked**. The atomic guard is unchanged.

**Redaction:** canary key absent from redacted evidence; no `data:image` payload; `image_urls`
becomes `['<redacted-data-uri-1>', …-2>, …-3>]`. `estimate_cost()` returns
`{'currency': 'credits', 'estimatedCredits': 20, 'assumptionDate': '2026-08-04'}`.

**v0.7.1 and subsystem preservation:** fifteen legacy and governance files byte-identical to the
accepted archive — `authority_mesh.py`, `build_asset.py`, `macos_keychain.py`, `openai_client.py`,
`image_governance.py`, `settings_store.py`, `concept_workflow.py`, `image_pricing.py`,
`spend_ledger.py`, `mesh_math.py`, `craft_profiles.json`, `pyproject.toml`, `requirements.txt`,
`server.py`, `pipeline.py`. `geometry_v2`, Import Probe, VMP, UI, server and pipeline are untouched
by this diff.

---

## 5. Bundle-existence claim and no misrepresentation

I searched the repository for any committed approved `MultiviewAuthorityBundleV1`. **None exists** —
only `profiles/multiview_authority_bundle_v1.schema.json` (the schema) and VMP schema/example files
matched on `"approval"`. No same-craft top/front/right approved bundle is present.

`MESHY_SMOKE_INPUT_READINESS.md` states this accurately and without overreach:

> *"The repository was inspected for a genuine, human-approved, same-craft `top`/`front`/`right`
> `MultiviewAuthorityBundleV1`. None exists. Existing multiview bundles and images are generated
> test fixtures. Existing approved gunship evidence is single-view material and is not a
> substitute. No fixture was promoted, and no front or right view was fabricated."*

`NO_SPEND_ATTESTATION.json` reinforces it: `evidenceClass:
NO_SPEND_PREAUTHORIZATION_NOT_PROVIDER_OUTPUT`, `humanApprovedAuthorityBundle: MISSING`,
`fixtureResultsAreNotMeshyOutputs: true`, `noApiKeyReadOrUsed: true`, `noCreditsConsumed: true`,
`noMeshyTaskCreated: true`, `noProviderArtifactDownloaded: true`, `providerTaskId: null`.

**No fixture or older single-view evidence has been promoted as a real authority bundle.**

---

## 6. Dry-run projection is genuinely unsendable

`V0.8.1_MESHY_SMOKE_DRY_RUN_PREVIEW.json` records `bundleDigest: null`, `profile: null`,
`bundleStatus: HUMAN_APPROVED_TOP_FRONT_RIGHT_BUNDLE_NOT_AVAILABLE`, `estimatedCredits: 20`,
`maximumCredits: 20`, `paidOperationPerformed: false`, `providerTaskId: null`, and placeholder
`image_urls` of the form `<redacted-data-uri-top-not-available>` — not real Data URIs.

This is unsendable by construction, not merely by labelling: `_authorize` requires
`approved_bundle_digest == confirmed_bundle_digest == validate_bundle(...)`, and a `null` digest
with a `null` profile cannot satisfy that, nor can placeholder strings become image payloads. The
request body otherwise matches the verified contract exactly (`meshy-6`, all five geometry-only
options false/absent, `target_formats: ["glb"]`).

---

## 7. Gates reproduced

| Command | Result |
|---|---|
| Producer `ruff check .` | **All checks passed** |
| Producer collection | **354 tests collected** |
| `test_reconstruction_v1.py` + `test_meshy_smoke_preauthorization.py` | **85 passed, 0 skipped** |
| Import Probe `ruff check .` | **PASS** |
| Import Probe `pytest -q` (isolated) | **39 passed, 0 skipped** |
| `verify_import_probe_baseline.py` vs accepted tag | *"Import Probe matches historical baseline"*, exit 0 |
| Producer binding | 317 / `2f2a3a43…` verified |
| Import Probe binding | 64 / `88351057…` verified |
| Evidence internal manifest | **8 of 8 entries verify** |
| Evidence secret / Bearer / Data URI / signed-query scan | **no match** |

---

## Findings

**MBS-184 — Observation — recorded DNS results for `assets.meshy.ai` are synthetic placeholders.**

*Affected:* `OFFLINE_HOST_POLICY_PREFLIGHT.json` in the evidence package.

*Evidence:* the file records
`"hostname": "assets.meshy.ai", "dnsResults": ["8.8.8.8", "2606:4700:4700::1111"]`. Those are
Google Public DNS and Cloudflare DNS resolver addresses — they are not A/AAAA records for
`assets.meshy.ai`. They are globally routable, so the policy correctly returned `ALLOW`, but the
values are stub inputs rather than observed resolution.

*Why it matters:* the filename is prefixed `OFFLINE_`, the attestation states no network occurred,
and the surrounding documentation is honest, so nothing is misrepresented. But a future reader
comparing this record against a live preflight could mistake the placeholders for the real
resolution of the approved host and conclude the addresses had drifted.

*Exact remediation:* rename the field to `stubDnsResults` or add
`"resolutionSource": "offline_stub_not_observed"` to the record.

*Blocks:* nothing — not the authority-bundle gate, not authorization, not merge, not release.

**No other findings.** Numbering continues from **MBS-185**.

---

## Standing items

| Item | Status |
|---|---|
| **MBS-182** | **OPEN** (Observation) — submission guard reserved before request build; safe-direction timing. Unchanged. |
| **MBS-183** | **SATISFIED for this review, remains a standing pre-authorization requirement.** The contract was re-verified today and I confirmed it independently against live documentation. It must be re-verified again immediately before any authorized live call, since Meshy pricing and models have changed historically. |
| **MBS-136** | **OPEN** against a real provider. No paid-provider work is authorized. |
| MBS-150–154, MBS-180 | Unchanged and open. |

---

## Verdict

> ## **ACCEPT**

The committed contract snapshot is accurate against live official documentation, including the
20-credit geometry-only price and the `assets.meshy.ai` artifact hostname. Production approves
exactly one host through the real OS resolver and refuses every deceptive variant, unsafe scheme,
port, credentialed URL, IP literal, localhost form, and non-global or mixed DNS result. The
preflight cannot download bytes, submit, poll, read a key, or consume credits, and it redacts
signed query values and fragments. The dry-run projection is unsendable because no human-approved
top/front/right bundle exists — a fact the candidate states plainly rather than papering over. All
MBS-181 protections, POST authorization, duplicate-spend controls, redaction, v0.7.1 preservation
and subsystem isolation are intact.

**The candidate is ready for the separate authority-bundle and explicit-authorization gates.**

This review does **not** authorize a live Meshy operation, a paid task, credit consumption, an API
key, an artifact download, merge, tag, release, or visual testing. I executed none of those, used
no API key, and did not modify the repository.

The remaining prerequisite is a genuine human-approved same-craft top/front/right authority bundle,
followed by explicit authorization under the 20-credit cap with the contract re-verified at that
moment.
