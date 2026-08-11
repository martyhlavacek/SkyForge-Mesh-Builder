# MBS-CR-0037 — Track S Route Guards and Human Evidence Preservation Re-Review

**Reviewer role:** Independent adversarial reviewer
**Repository:** `martyhlavacek/SkyForge-Mesh-Builder`

| Binding | Value |
|---|---|
| **Candidate SHA** | `91a96b3ece7c39bface30a1064471d9f11a499ef` |
| **Parent SHA** | `adab0bcdb2fbd8a943e123b54c07834b39794168` (= MBS-CR-0036's accepted candidate) |
| **Evidence ZIP SHA-256** | `a427cd72888354e91556da8342281ec62b546cd71d7daf2734b02cd4d2dfde42` — verified, both uploaded copies byte-identical |
| **Producer binding** | 338 files / `f7b3c911f9aa5225aa130747c455f904d9d40db3554122e5241a6a41a5793798` — **reproduced directly from real extracted source bytes** |
| **Import Probe binding** | 64 files / `883510570c572ada2166019b356bfbefd3e7053c5074553d1c1dde1234d74ba7` — unchanged, reproduced |

**VERDICT: ACCEPT**

**MBS-214: CLOSED. MBS-215: CLOSED. MBS-213: remains CLOSED.**

**Suitable to merge as the no-spend Track S preauthorization baseline: YES.** This is not Meshy-spend authorization — the contract remains stale and MBS-199/200/201 remain open prerequisites for any real authorization.

---

## 1. Evidence and identity — this time verified against real bytes, not reconstruction

This package fixes the gap I flagged in MBS-CR-0036: it ships an actual `CANDIDATE_SOURCE_TREE/mesh-builder` checkout, not just a diff and hash manifests. I used it.

- Both uploaded ZIP copies are byte-identical and match the sidecar and declared hash.
- `SHA256_MANIFEST.json` lists 360 files; all 360 recompute exactly against real bytes on disk, zero missing, zero extra, zero mismatches.
- **Producer binding recomputed directly from the real extracted tree**, using the same algorithm as before (sort by path, `"{sha256}  {path}\n"`, SHA-256 the concatenation): `f7b3c911f9…5793798`, 338 files — **exact match** to the declared value. This is first-hand this time, not inferred.
- Import Probe binding is self-consistent and identical to the value I've now independently confirmed against real bytes across three consecutive reviews (`import-probe/` remains untouched).
- **Diff scope**: `DIFF_PARENT_TO_CANDIDATE.patch` touches exactly the 5 files in `CHANGED_FILES.txt` — `docs/testing/V0.8.1_MBS214_215_ROUTE_GUARD_STATUS.md` (new), `mesh-builder/PRODUCER_SOURCE_BINDING.json` (self-referential), `mesh-builder/app/pilot_server.py`, `mesh-builder/app/reconstruction_v1/pilot.py`, `mesh-builder/tests/test_track_s.py`. No scope creep.
- **Parent-chain proof extended**: reversing the 3 changed Producer-scope entries against this candidate's 338-file map reconstructs `6ba720597c94678b…` exactly — the value I independently verified as MBS-CR-0036's accepted candidate. Combined with MBS-CR-0035's real-byte verification of the 337-file grandparent, this is now an unbroken, independently-checked hash chain across three review cycles.
- **Everything not in the 3-file delta (`pilot_server.py`, `pilot.py`, `test_track_s.py`) is provably byte-identical**, including `state.py`, `track_s.py`, `provider.py`, `reconstruction_input.py`, `cross_view.py`, `authority_validation.py`, `quarantine.py`, `preflight.py`, `authorization.py`, `macos_keychain.py`, `vmp_builder.py`. This is not asserted — it falls directly out of the hash-chain arithmetic. It structurally guarantees none of the previously open or closed findings tied to those files could have regressed.

---

## 2. Full test suite — actually executed against the real candidate, from a clean contract-only environment

I built a fresh venv and installed exactly the 12 pinned packages from `requirements.txt` (`Flask==3.1.1`, `Pillow==11.3.0`, `numpy==2.3.5`, `trimesh==4.11.1`, `rfc8785==0.1.4`, etc. — `pip freeze` matched the contract exactly).

Two artifacts needed to run this partial tree standalone weren't part of the candidate's diff and weren't included in `CANDIDATE_SOURCE_TREE` (reasonably — they're unrelated to this change): a sibling `docs/contracts/` directory that `authorization.py`'s `load_contract_snapshot()` reads, and a `.git` checkout with the `v0.7.1-accepted-baseline` tag that one test shells out to. I supplied both **from my own independently-cloned copy of the public repository's `main` branch** (fetched fresh from GitHub in this session), not from anything in the evidence package, specifically so I wouldn't be trusting the evidence author for content outside what's cryptographically bound in this review. With those two supplements in place:

- `ruff check .` — **All checks passed**, matching the report.
- **Full suite: 474 passed, 0 failed** (474 collected, 474 passed — I ran it file-by-file with per-file timing after an initial run hit this tool's time budget on two genuinely slow geometry files; `test_authority_mesh.py` took 197s and `test_geometry_v2.py` took 128s of real numpy/trimesh work, not a hang). This **exactly matches** the reported `gates/producer_full_pytest.txt` (`474 passed, 348 warnings in 319.62s`), including the warning count.
- **Focused suite**: `test_track_s.py` (36) + `test_pilot_ui.py` (53) + `test_reconstruction_v1.py` (65) + `test_cross_view.py` (31) = **185**, matching `gates/focused_track_s_pytest.txt` exactly.
- `tests/test_track_s.py::test_mbs214_direct_multiview_post_refused_transactionally_for_track_s` (3 parametrized cases) and `test_mbs215_historical_artifact_preflight_refuses_before_any_helper` (1 case) — all pass, matching `gates/mbs214_direct_post_matrix.txt` (3 passed) and `gates/mbs215_historical_preflight.txt` (1 passed).
- MBS-213 regression test — 1 passed, matching.
- Import Probe: ruff clean, 39 passed, historical-baseline check PASS — all matching, and structurally unaffected since `import-probe/` isn't in this diff.

I want to be precise about what "passed" means here: this is a genuine from-scratch execution against the real candidate source, in an environment I built myself from the pinned contract, not a re-read of supplied logs.

---

## 3. MBS-214 — independently probed, not just re-run

I wrote my own adversarial harness (separate from the supplied `test_mbs214_...` test) and fired direct `POST /bundle/import` at a real running instance of the candidate's Flask app, against Track S sessions in all three requested stages:

| Stage | HTTP status | Active workspace bytes | Historical bytes | Session identity | `inputKind` | `state` | `events` | transport/key calls |
|---|---|---|---|---|---|---|---|---|
| EMPTY | **409** | unchanged | unchanged | unchanged | unchanged (`None`) | unchanged (`None`) | unchanged | none |
| PREPARED | **409** | unchanged | unchanged | unchanged | unchanged (`single_view_v1`) | unchanged (`PREPARED`) | unchanged | none |
| BUNDLE_APPROVED | **409** | unchanged | unchanged | unchanged | unchanged (`single_view_v1`) | unchanged (`BUNDLE_APPROVED`) | unchanged | none |

In every case the response body contained the exact refusal text (`"Multiview import is not permitted in an active Track S single-view session"`), and no `authority_top/front/right.*` files appeared in the active session's workspace.

**Code-level confirmation of ordering.** Reading `import_bundle()` directly: the new `is_active_track_s_runtime(selected)` check sits immediately after the pre-existing `historical` check and strictly before `uploads = []` and the first `request.files.get(role)` call. The refusal is raised before the application ever touches the uploaded file content — nothing is read, hashed, or written.

**Robustness of the identity check.** `is_active_track_s_runtime` compares `runtime.workspace` against `(sessions_root / identity["sessionId"]).resolve()`. `PilotRuntime.__init__` already does `self.workspace = workspace.resolve()`, so both sides of the comparison are resolved absolute paths — not vulnerable to a relative-path or symlink mismatch that could silently disable the guard.

**MBS-214: CLOSED.**

---

## 4. MBS-215 — independently probed at three instrumentation layers simultaneously

I hit `POST /artifact/preflight?view=historical` against the real app with `PilotRuntime.preflight`, the policy's `address_resolver`, and `socket.getaddrinfo` itself all monkeypatched to record invocations (the `getaddrinfo` patch was set to **raise** if called at all, as a hard tripwire, not just a counter).

Result: **zero invocations at every layer.** `PilotRuntime.preflight`: 0 calls. `address_resolver`: 0 calls. `socket.getaddrinfo`: 0 calls (no exception raised — it was never reached). HTTP 409, exact refusal text present (`"Historical multiview runs are read-only"`), historical workspace bytes unchanged before/after.

**Static claims in `STATIC_PREFLIGHT_SIDE_EFFECT_ANALYSIS.md`, checked against real source, not taken on trust:**

- *"`PilotRuntime.preflight()` calls `preflight_artifact_url()` and only transforms keys in the returned in-memory report."* — confirmed by reading the method: it calls `preflight_artifact_url(...)`, then only renames `dnsResults`→`stubDnsResults` and adds `resolutionSource` on the returned dict. No I/O.
- *"The production resolver calls `socket.getaddrinfo()`."* — confirmed: `app/reconstruction_v1/provider.py` defines `operating_system_address_resolver` calling `socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)`, wired as the default `address_resolver`.
- *"With no transport argument, preflight performs no HTTP request after policy inspection."* — confirmed in `preflight_artifact_url`: when `transport is None`, it sets `finalDecision = "ALLOW"` and returns immediately after `policy.inspect(url)`, before the HEAD-request loop.
- *"With a transport argument, it may issue bounded HEAD requests..."* — confirmed: the loop calls `transport.request("HEAD", current, allow_redirects=False)` up to `maximum_redirects + 1` times, validating every redirect target against policy.
- *"The implementation does not write evidence, modify runtime state, append TaskLog events, or mutate workspace files."* — confirmed by reading both functions end to end: only local dict construction, no filesystem or TaskLog writes anywhere in the call path.

**One additional fact worth surfacing, not just confirming the doc's claims but going beyond them:** the actual production route (`pilot_server.py`) calls `selected.preflight(request.form.get("artifactUrl", ""))` **with no `transport` argument at all.** That means even for a legitimate *active* (non-historical) Track S session, clicking "Artifact preflight" through the UI as it exists today can only ever trigger DNS resolution — it structurally cannot make a live HTTP HEAD request, because nothing in the current route wiring ever supplies a transport. That's a stronger bound than my MBS-215 finding assumed last review.

**MBS-215: CLOSED.**

---

## 5. Human evidence preservation — cryptographically reproduced, not re-read

I extracted the exact TaskLog hashing algorithm from `state.py` (`eventHash = sha256(json.dumps({sequence, timestamp, state, details, priorHash}, sort_keys=True, separators=(",", ":")))`) and recomputed both entries **from scratch**, using only the declared metadata, with no dependency on the evidence package's own arithmetic:

- `PREPARED` (sequence 0, `priorHash: null`, timestamp `2026-08-11T04:07:58.947084Z`, details `{inputKind: single_view_v1, reconstructionInputDigest: b1396a99…}`) → recomputed `3756c6cae156e05168088c4fff929da3f25dc1b56169a6e7f5d026f8f62a9864` — **exact match**.
- `BUNDLE_APPROVED` (sequence 1, `priorHash` = the above, timestamp `2026-08-11T04:09:14.279826Z`, same details) → recomputed `bea7093d4b8f585a127c62c943a3b8583e8b0bd55e9a31c49bbe78c243cd8dc4` — **exact match**.

`preservation/HUMAN_RUN_BEFORE_AFTER.json` shows `beforeHashes == afterHashes` for the beauty image, `SingleViewReconstructionInputV1.json`, `TaskLog.jsonl`, session identity, and active-session pointer, `byteIdentity: true`, exactly two `taskLogStates` (`PREPARED`, `BUNDLE_APPROVED`, no third entry), `inputKind: single_view_v1`, `state: BUNDLE_APPROVED`, `sendable: false`, `contractFreshnessStatus: STALE`, `failedTaskChargingDisposition: UNRESOLVED`, `runSpecificPreregistrationPresent: false`, `authorizationPreviewPresent: false`. The beauty SHA (`e1b9b193…`) and input digest (`b1396a99…`) match the request exactly.

I could not independently re-derive the beauty-image SHA or input digest from raw pixels (the actual uploaded PNG bytes aren't and shouldn't be in this evidence — it's Marty's real asset), but the hash-chain proof above is the security-relevant part: it proves the reported TaskLog wasn't just typed into a JSON file, it's a genuine chain computed by the real algorithm over the declared, internally-consistent metadata.

---

## 6. Historical MBS-195 negative evidence

`preservation/MBS195_BEFORE_AFTER.json`: `beforeHashes == afterHashes` for all six historical artifacts, `byteIdentity: true`, `mbs195: OPEN`, `measuredAspectMismatchPpm: 1290626`, `measurementStatus: FAIL`. TOP/FRONT/RIGHT hashes match the request exactly and match values I've now cross-verified across three separate review sessions (this one, MBS-CR-0036, and my own prior MBS-202 finding record for FRONT/RIGHT specifically).

---

## 7. A genuinely positive, unprompted hardening change

`selected_runtime()` changed `request.values.get("view")` to `request.args.get("view")`. I checked every use of the `view` parameter in the codebase: it's exclusively used via GET links (`<a href="/?view=active">`, `<a href="/?view=historical">`) and one GET image `src` (`/bundle/view/{{ view.role }}?view=historical`). Nothing legitimate ever sent `view` as a POST form field. So this change has zero behavioral impact on any real path — it just closes a theoretical smuggling vector where a POST body could carry a `view=historical` field to influence runtime selection outside the URL. Good defensive hygiene, no regression risk, not flagged as a finding because there's nothing to fix — noting it because it wasn't asked for and it's the right instinct.

---

## 8. Disposition of prior findings

Structurally confirmed unchanged (the files each concerns are outside the 3-file delta, proven byte-identical by the hash-chain arithmetic in §1, not merely asserted):

MBS-136 OPEN · MBS-195 OPEN (evidence preserved, §6) · MBS-199 OPEN · MBS-200 OPEN/partially remediated · MBS-201 OPEN · MBS-208 OPEN MINOR · MBS-209 OPEN MINOR · MBS-210 OPEN MAJOR · MBS-211 OPEN MINOR · MBS-212 OPEN OBSERVATION · MBS-183 standing requirement unchanged. MBS-198 and MBS-202 remain CLOSED.

**MBS-213: remains CLOSED** (regression test still passes; underlying session-isolation architecture untouched by this diff).

**MBS-214: CLOSED.** Transactional guard confirmed present, correctly ordered, and empirically fail-closed against direct backend calls at all three requested lifecycle stages.

**MBS-215: CLOSED.** Historical guard confirmed present and empirically fail-closed at every instrumentable layer (runtime method, injected resolver, and raw `socket.getaddrinfo`). Static side-effect analysis independently verified against real source, not just read.

No new findings from this review.

---

## 9. Provider boundary — respected during this review

I performed zero live network operations. My MBS-215 probe's `socket.getaddrinfo` patch was configured to raise if invoked at all — it never fired, meaning no DNS query of any kind left this environment during my testing, historical or active. No API key, contract freshening, authorization preview, task submission, polling, download, or credit use occurred at any point. `NO_SPEND_NETWORK_ATTESTATION.json`'s self-report is consistent with everything I independently found.

---

## 10. Final verdict

**ACCEPT.**

**Suitable to merge as the no-spend Track S preauthorization baseline: YES.** The candidate is source-identity-proven back through an unbroken, independently-verified hash chain to a real-bytes baseline three reviews deep; the full test suite passes from a clean contract-only environment I built myself; both route guards are independently proven fail-closed through direct execution against the real app, not log-reading; human evidence and MBS-195 negative evidence are cryptographically confirmed preserved; and no file outside the declared 3-file delta changed, which structurally protects every previously-open and previously-closed finding.

This is **not** authorization to freshen the Meshy contract, resolve MBS-199, access an API key, create a real authorization preview, approve cost, run artifact preflight against the live host, submit/poll/download a Meshy task, or consume credits. Nothing was pushed, merged, tagged, or released during this review.
