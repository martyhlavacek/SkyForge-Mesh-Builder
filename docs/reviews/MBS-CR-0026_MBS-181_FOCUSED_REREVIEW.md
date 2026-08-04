# MBS-CR-0026 — MBS-181 Focused Remediation Re-Review

**Review identifier:** MBS-CR-0026 (focused MBS-181 re-review)
**Date:** 4 August 2026
**Reviewer:** Claude (independent adversarial reviewer)

| Item | Value |
|---|---|
| Repository | `martyhlavacek/SkyForge-Mesh-Builder` |
| Draft PR | #4 |
| Branch | `feature/v0.8.1-multiview-reconstruction-pilot` |
| Original reviewed candidate | `ac57afb9db69244b6c46aa7e93f60ae6c0d034ea` |
| Remediation candidate | `dbcad7f2898c1360f2bc50a21c34ec89eb3b3f78` |
| Accepted baseline / tag | `d38dd5d1638eae0942929a4ed568edb048220894` / `v0.7.1-accepted-baseline` |
| Producer binding | 313 / `6ace859559a8d7d5ffb64e46afbb6c0be8451823d9240a678215100a3eadcd5e` |
| Import Probe binding | 64 / `883510570c572ada2166019b356bfbefd3e7053c5074553d1c1dde1234d74ba7` |
| Evidence ZIP | `2753101f2403a5d108d74d1bd5bf30721e551a2ee4b7aa377f7ecd6634ab9ca0` |

---

## Executive verdict

> ## **ACCEPT**
>
> **MBS-181 is FULLY REMEDIATED.**

The provider-layer guard now blocks **all five** network entry points under **all three**
CI/no-network indicators — I proved this with a fifteen-case spy matrix producing **zero transport
attempts**, with live controls confirming the spy would have detected any crossing. The artifact
host policy rejected **all twenty** unsafe URL classes I constructed and accepted only the three
legitimate ones. Redirect escape, final-response-URL mutation, redirect loops and missing
`Location` all fail closed. Production is genuinely fail-closed: the default policy has an empty
approved-host set **and** a `None` resolver, so even `assets.meshy.ai` is refused today.

Every original property survives unchanged: eleven POST authorization controls still block with
zero network attempts, duplicate-spend and restart replay are still refused, bundle integrity
still rejects tampering, redaction still removes the canary and all Data URIs, and fifteen legacy
and governance files remain byte-identical to the accepted v0.7.1 archive.

No new finding is raised. **MBS-184 remains unused.**

`ACCEPT` means this exact remediation may proceed through the separately controlled release
process. It does **not** authorize a live task, paid work, merge, tag, release, or user testing,
and I performed none of those. **MBS-182** and **MBS-183** remain open by design, as instructed.

---

## Scope and method

Fresh clone into an empty directory, detached checkout at the exact remediation candidate, the
complete `ac57afb9..dbcad7f2` diff inspected, both bindings recomputed, all local gates re-run,
and direct adversarial probing of the guard and host policy with an injected spy transport that
raises on any request. Codex's report was treated as claim.

**Evidence classification.**

- **Independently reproduced:** provenance and bindings; the focused diff; v0.7.1 byte-identity;
  Producer Ruff, full and focused pytest; Import Probe Ruff and pytest in isolation; the
  historical Import Probe comparison; the 15-case kill-switch matrix; the 23-case host-policy
  matrix; 11 redirect/final-URL cases; 11 POST authorization cases; duplicate-spend and replay;
  bundle-integrity spot mutations; redaction; the evidence manifest (42/42) and secret scan.
- **Inspected but not reproduced:** the GitHub Actions runs cited in the evidence
  (`30865064557`, `30865066264`) — I have no GitHub API access, though their substance is covered
  by my own local execution.
- **Could not be verified:** live provider behaviour (no call was made, by design); Meshy asset
  host identity — correctly the subject of MBS-183.

**Recorded deviation:** Python 3.11 is unavailable to me; I used clean from-contract-only Python
3.12 environments. `requirements.txt` is unchanged from the accepted v0.7.1 contract.

---

## Provenance and diff

| Check | Result |
|---|---|
| PR #4 head | `dbcad7f2898c1360f2bc50a21c34ec89eb3b3f78` — **exact match** |
| Branch | resolves to the same commit — **match** |
| Original candidate `ac57afb9…` | **is an ancestor** |
| Accepted tag | → `d38dd5d1638eae0942929a4ed568edb048220894` — **unchanged** |
| Working tree | **clean** — 0 modified or untracked |
| Evidence ZIP vs uploaded sidecar | `2753101f…4ab9ca0` — **match**, equals the request value |
| Producer binding | **verified: True**, 313, `6ace8595…3eadcd5e` |
| Import Probe binding | **verified: True**, 64, `88351057…34d74ba7` (unchanged) |

**Focused diff — exactly 8 files**, as declared:

```
M  docs/architecture/V0.8.1_MULTIVIEW_RECONSTRUCTION_PILOT.md
A  docs/contracts/MESHY_ARTIFACT_HOST_POLICY.md
M  docs/findings/OPEN_FINDINGS.md
M  docs/security/V0.8.1_PAID_CALL_SECURITY_CONTRACT.md
M  docs/testing/V0.8.1_NO_SPEND_TEST_PLAN.md
M  mesh-builder/PRODUCER_SOURCE_BINDING.json
M  mesh-builder/app/reconstruction_v1/provider.py
M  mesh-builder/tests/test_reconstruction_v1.py
```

Only one source file and its tests. No `geometry_v2` change, no Import Probe change, no
UI/VMP/server/pipeline integration, no second provider, no legacy or default-route change.
`app/reconstruction_v1/provider.py` grew from 187 to 276 lines; nothing else in the package moved.

**A note on scope reading:** a baseline→HEAD diff also lists `geometry_v2` files, but that is
because `main` already merged the v0.8.0 Alpha 1 work at `93cfecfa`. The focused
`ac57afb9..dbcad7f2` diff touches none of them, which is the correct comparison for this review.

---

## Commands executed and results

| Command | Result | Claimed |
|---|---|---|
| Producer `ruff check .` | **All checks passed** | PASS ✔ |
| Producer `pytest -q` | **334 passed, 0 skipped, 0 failed, 0 errors** (348 warnings) | 334/0, 348 ✔ |
| Focused `tests/test_reconstruction_v1.py` | **65 passed, 0 skipped** | 65/0 ✔ |
| Import Probe `ruff check .` | **All checks passed** | PASS ✔ |
| Import Probe `pytest -q` (PYTHONPATH unset, NOUSERSITE=1) | **39 passed, 0 skipped** | 39/0 ✔ |
| `verify_import_probe_baseline.py` vs accepted tag | *"Import Probe matches historical baseline"*, exit 0 | PASS ✔ |
| Producer binding | 313 / `6ace8595…` | ✔ |
| Import Probe binding | 64 / `88351057…` | ✔ |
| Evidence internal manifest | **42 of 42 entries verify** | verified ✔ |
| Evidence secret / Authorization / Data URI scan | **no match** | PASS ✔ |

All reported gates reproduce exactly, including the 348 pre-existing warning count.

---

## 1. Network guard — MBS-181 core

`_assert_network_permitted(operation)` (provider.py:129) collects `CI`, `GITHUB_ACTIONS` and
`SKYFORGE_PROVIDER_NETWORK_DISABLED == "1"`, and raises `AuthorizationError` naming both the
operation and the triggering indicators. It is called as the **first statement** of all five
entry points: `submit_task` (:190), `get_task` (:217), `poll_until_terminal` (:241),
`download_artifact` (:251), `download_artifacts` (:272).

**Fifteen-case spy matrix — 5 operations × 3 indicators:**

| Indicator | submit_task | get_task | poll_until_terminal | download_artifact | download_artifacts |
|---|---|---|---|---|---|
| `SKYFORGE_PROVIDER_NETWORK_DISABLED=1` | blocked | blocked | blocked | blocked | blocked |
| `CI=true` | blocked | blocked | blocked | blocked | blocked |
| `GITHUB_ACTIONS=true` | blocked | blocked | blocked | blocked | blocked |

**Total transport attempts across all fifteen blocked cases: 0.**

**Control (empty environment):** `get_task`, `poll_until_terminal`, `download_artifact` and
`download_artifacts` each reached the spy transport (1 attempt each) — proving the instrumentation
was live and the fifteen zeros are genuine blocks, not absent wiring.

This is the exact defect I raised in MBS-181, and it is closed. In the original candidate these
same four operations reached transport under both indicators simultaneously.

## 2. Artifact-host policy

`ArtifactHostPolicy.validate()` enforces, in order: well-formed URL, HTTPS scheme, hostname
present, no credentials, port in `{None, 443}`, not an IP literal, not localhost, **exact**
lowercase membership in `approved_hosts`, a resolver being configured, resolution returning
addresses, and every resolved address being `is_global`.

**Twenty-three-case matrix — 0 mismatches:**

| Case | Expected | Result |
|---|---|---|
| Exact approved HTTPS host | accept | **accepted** |
| Explicit port 443 | accept | **accepted** |
| Uppercase approved host | accept | **accepted** (case-folded) |
| Arbitrary domain | reject | host not approved |
| HTTP scheme | reject | must use HTTPS |
| `localhost` / `*.localhost` | reject | must not target localhost |
| IPv4 literal / IPv6 literal `[::1]` | reject | must not target an IP literal |
| Embedded credentials `u:p@` | reject | must not contain credentials |
| Deceptive **prefix** `assets.example.test.evil.com` | reject | host not approved |
| Deceptive **suffix** `evilassets.example.test` | reject | host not approved |
| Subdomain of approved `cdn.assets.…` | reject | host not approved |
| Unexpected port 8443 | reject | unexpected port |
| Missing host `https:///a.glb` | reject | must use HTTPS with a hostname |
| Malformed `https://[bad/a.glb` | reject | malformed URL |
| Empty string | reject | malformed URL |
| Resolves private `10/8` | reject | non-public address |
| Resolves link-local `169.254.169.254` | reject | non-public address |
| Resolves loopback `127.0.0.1` | reject | non-public address |
| Resolves reserved `240/4` | reject | non-public address |
| Resolves IPv6 ULA `fd00::1` | reject | non-public address |
| Resolves to no addresses | reject | resolved to no addresses |

The deceptive-hostname handling is correct in both directions — neither `startswith` nor
`endswith` matching is used; membership is exact after case-folding, so subdomains and
concatenations are refused. The link-local case matters specifically: `169.254.169.254` is the
cloud metadata endpoint, and it is refused at the resolution stage even if a hostname were
approved.

## 3. Redirect and final-URL safety

`download_artifact` validates the initial URL **before** any transport, uses
`allow_redirects=False`, revalidates `response.url` when present, resolves each `Location` with
`urljoin` and revalidates the result, and bounds the chain at four hops.

| Case | Result | Transport calls |
|---|---|---|
| Direct 200 on approved host | **accepted**, 44 B | 1 |
| Redirect to evil host | **rejected** — host not approved | 1 (no fetch of target) |
| Redirect to IP literal | **rejected** | 1 |
| Redirect to `http://localhost` | **rejected** | 1 |
| Relative redirect within approved host | **accepted** | 2 |
| **Final `response.url` mutated to evil host** | **rejected** | 1 |
| Redirect with no `Location` | **rejected** | 1 |
| Redirect loop (>4) | **rejected** — limit exceeded | 4 |
| 200 but not glTF magic | **rejected** — corrupt GLB | 1 |
| 200 truncated (`glTF` only) | **rejected** | 1 |
| **Initial URL evil** | **rejected** | **0** — refused pre-transport |

The last row is the important one: an unsafe URL never reaches the network at all. The
final-URL revalidation closes the case where a transport implementation silently follows a
redirect internally.

## 4. Production fail-closed

`DEFAULT_ARTIFACT_HOST_POLICY` has `approved_hosts = frozenset()` (**empty**),
`contract_version = "skyforge.meshy-artifact-hosts.unverified.v1"`, and
`address_resolver = None`. I confirmed that `assets.meshy.ai`, `api.meshy.ai` and an arbitrary
host are **all rejected** by the production default today.

This is a genuinely fail-closed posture and the right one: no artifact download can succeed until
official Meshy asset hosts are re-verified and explicitly approved immediately before live
authorization. The two-layer construction — empty host set *and* absent resolver — means even an
accidental host addition without a resolver still fails.

Offline tests inject a fixture-only policy, so the production default is never exercised
permissively in CI.

## 5. Original properties unchanged

**POST authorization — 11 controls, all still blocked pre-transport with 0 network attempts:**
`paid_enabled=False`, `paid_enabled=1`, digest mismatch, `maximum_credits=19`,
`maximum_credits=True`, `maximum_credits=20.0`, `api_key=None`, blank key, `prior_task_id` set,
`submission_registry=None`. The authorized control reached transport.

**Duplicate spend / replay:** first submission reached transport; **second submission with the
same digest and registry was blocked**; a new process against the same registry was **also
blocked**. The atomic `open("x")` guard is unchanged and still precedes the POST.

**No automatic retry:** transport exceptions still raise
`ProviderError("Ambiguous POST result; automatic resubmission is forbidden")`;
`poll_until_terminal` still raises rather than creating another task.

**Bundle integrity:** mutated view hash, traversal path, duplicate role and unsupported profile
all rejected with `BundleError`.

**Redaction:** canary key **absent** from the redacted evidence; no `data:image` payload survives;
no Authorization key in the prepared request; `image_urls` becomes
`['<redacted-data-uri-1>', …-2>, …-3>]`.

**v0.7.1 preservation:** fifteen legacy and governance files byte-identical to the accepted
archive — `authority_mesh.py`, `build_asset.py`, `macos_keychain.py`, `openai_client.py`,
`image_governance.py`, `settings_store.py`, `concept_workflow.py`, `image_pricing.py`,
`spend_ledger.py`, `mesh_math.py`, `craft_profiles.json`, `pyproject.toml`, `requirements.txt`,
`server.py`, `pipeline.py`.

**No-spend:** across every probe in this review, the **only** transport attempts were the
deliberate authorized controls. No live or paid provider call was made.

---

## Findings

**No new findings.** Finding numbering remains available from **MBS-184**.

| Finding | Disposition |
|---|---|
| **MBS-181** | **CLOSED — fully remediated.** Guard covers all five entry points under all three indicators (0/15 transport attempts); host policy rejects all twenty unsafe classes; redirects and final URLs revalidated; production fail-closed. |
| **MBS-182** | **REMAINS OPEN** (Observation) — submission guard reserved before request build; safe-direction reservation timing. Not closed in this focused review, as instructed. |
| **MBS-183** | **REMAINS OPEN** (pre-smoke requirement) — Meshy contract re-verification before any authorized live call. Now doubly required, since the approved artifact-host set must be populated from re-verified official hosts. Not closed in this focused review. |

---

## Verdict

> ## **ACCEPT**

MBS-181 is fully remediated. The remediation is tightly scoped to eight files, changes one source
module, introduces no regression, and preserves every authorization, duplicate-spend,
bundle-integrity, redaction, v0.7.1 and no-spend property I verified in the original review. All
reported gates reproduce exactly, and the evidence package verifies 42/42 with no secret,
Authorization value or Data URI payload.

This authorizes the exact remediation to proceed through the separately controlled release
process **only**. It does not authorize a live task, paid work, merge, tag, release, or user
testing — and I performed none of those, nor did I modify the repository or make any provider
call.

**MBS-182 and MBS-183 remain open. MBS-136 remains open against a real provider. No
paid-provider work is authorized.**

Before any authorized smoke task, the approved artifact-host set must be populated from
re-verified official Meshy asset-serving hosts with a real resolver configured — until then the
download path is, correctly, inoperable.
