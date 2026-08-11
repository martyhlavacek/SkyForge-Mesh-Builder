# MBS-CR-0036 — Track S Session Isolation and Human Input-Binding Re-Review

**Reviewer role:** Independent adversarial reviewer
**Repository:** `martyhlavacek/SkyForge-Mesh-Builder`

| Binding | Value |
|---|---|
| **Candidate SHA** | `adab0bcdb2fbd8a943e123b54c07834b39794168` |
| **Parent SHA** | `8884b57d13f19039598db3df577f35714a3bd0fd` |
| **Evidence ZIP SHA-256** | `f3e6878fef90a6a80518116349023163c561d4eb5fe714701d6c0a2f995ed674` — **verified, both uploaded copies byte-identical** |
| **Producer binding** | 338 files / `6ba720597c94678b01f89a464d23b1603efe6c7454dd93f1422f21388eaa7e0a` — **reproduced** |
| **Import Probe binding** | 64 files / `883510570c572ada2166019b356bfbefd3e7053c5074553d1c1dde1234d74ba7` — **reproduced, unchanged from MBS-CR-0035** |

**VERDICT: ACCEPT WITH REQUIRED CHANGES**

**MBS-213: CLOSED.**

**May Marty resume the human NO-SPEND Track S single-view input-binding and approval workflow on this exact candidate? YES**, via the UI as designed. This is not authorization to merge, tag, release, freshen the contract, or contact Meshy.

---

## 1. Evidence and candidate-identity verification

**ZIP.** Both uploaded copies (`...EVIDENCE.zip` and `..._second.zip`) hash to `f3e6878f…f995ed674`, matching the sidecar file and the value stated in the review request — and are byte-for-byte identical (`cmp` confirms). This satisfies the deterministic-double-build check at the level available to me: I can confirm the two supplied builds are identical; I cannot independently confirm they came from two separate build invocations rather than one file uploaded twice.

**Internal manifest.** `SHA256_MANIFEST.json` lists 16 files. All 16 recompute to the declared hash and size with zero missing or extra files.

**Candidate and parent commits are not reachable from the remote.** I cloned `martyhlavacek/SkyForge-Mesh-Builder` fresh and fetched every branch, PR ref, and tag (`refs/pull/*`, all `feature/*` branches, `v0.7.1-accepted-baseline`). Neither `adab0bcd…794168` nor `8884b57d…3bd0fd` appears anywhere, and direct `git fetch origin <sha>` for both is refused by the server (`not our ref`). This is exactly what "intentionally local-only and unmerged" predicts, and is not itself a defect — but it means this evidence package (unlike some prior packages in this series) supplies **no actual source tree**, only a diff, JSON hash manifests, and text logs. I could not clone-and-hash real bytes at the candidate. See §12 for what this does and does not limit.

**Parent identity is independently corroborated.** `8884b57d…3bd0fd` is not an arbitrary claim: it is the exact candidate SHA I recorded as **ACCEPTED** in the governing prior review MBS-CR-0035, where I independently reproduced its Producer binding directly from real repository bytes as **337 files / `f6f73ccedd12274e1dafca7f2b48a1aa5b56355599a45dea3a4028d65889630c`**. That value is load-bearing for the check in §2.

---

## 2. Producer/Import Probe binding reproduction

The tree-manifest algorithm is not stated in this evidence package. I recovered it from my own MBS-CR-0035 session transcript: for each tracked file (excluding the binding file itself, `.git`, caches, and `workspace/`), sort by relative path, concatenate `"{sha256}  {relpath}\n"`, and SHA-256 the result. Applying this to the `files` maps embedded in `PRODUCER_SOURCE_BINDING.json` and `IMPORT_PROBE_SOURCE_BINDING.json` reproduces both declared `treeManifestSha256` values exactly:

- Producer: recomputed `6ba720597c94678b…` = declared `6ba720597c94678b…` ✔ (338 files)
- Import Probe: recomputed `883510570c572ada…` = declared `883510570c572ada…` ✔ (64 files)

That only proves internal arithmetic consistency, not that the per-file hashes reflect real bytes. So I went further: `FOCUSED_DIFF.patch` declares exactly 4 modified files and 1 added file inside the Producer scope. I reversed those 5 changes against the candidate's 338-file map to reconstruct the **parent's** 337-file map, and hashed it with the same algorithm:

```
app/pilot_server.py                          f23cae80…95200ec4a  ->  a5fa1a6a…3ab3c175
app/reconstruction_v1/pilot.py               b60b7df2…8529de0dbaa -> c1234ed1…094170d34a
app/templates/pilot_index.html               09972d81…895ee93a03d156dd -> 17148f2b…772fe00084e906a2b
tests/test_track_s.py                        f8f4b631…54d23b3a2a4e85c7 -> c83a6b3b…9ba8c337505904440
profiles/track_s_experiment_session_v1.schema.json  (new)  -> b71ff04b…6ce35144399777e
```

**Reconstructed parent Producer binding: 337 files / `f6f73ccedd12274e1dafca7f2b48a1aa5b56355599a45dea3a4028d65889630c`** — an **exact match** to the value I independently computed from real bytes in MBS-CR-0035.

This means: for all 333 files that are neither modified nor added, the candidate's claimed hashes are provably consistent with real bytes I verified myself two reviews ago. Combined with the diff scope check in §3, this is strong (though not first-hand-at-this-commit) evidence against fabrication for the overwhelming majority of the tree. The Import Probe binding is untouched and identical to the value I verified from real bytes in the same prior session — expected, since `import-probe/` does not appear in `CHANGED_FILES.txt`.

**Security-critical unchanged files confirmed present and untouched in this binding chain:** `state.py`, `track_s.py`, `reconstruction_input.py`, `provider.py`, `cross_view.py`, `authority_validation.py`, `macos_keychain.py`, `vmp_builder.py`, `preflight.py`. None of these appear in the 5-entry delta, so the canonical lifecycle, quarantine denylist, cross-view gate, authorization digest logic, credit ledger, and keychain code are byte-identical to the MBS-CR-0035 baseline — a structural, not asserted, non-regression argument.

---

## 3. Diff scope

`FOCUSED_DIFF.patch` touches exactly 7 files, matching `CHANGED_FILES.txt` exactly, no more, no less:

```
docs/testing/V0.8.1_TRACK_S_SESSION_ISOLATION_STATUS.md   (new)
mesh-builder/PRODUCER_SOURCE_BINDING.json                  (self-referential update)
mesh-builder/app/pilot_server.py
mesh-builder/app/reconstruction_v1/pilot.py
mesh-builder/app/templates/pilot_index.html
mesh-builder/profiles/track_s_experiment_session_v1.schema.json  (new)
mesh-builder/tests/test_track_s.py
```

No hidden scope creep. `PRODUCER_SOURCE_BINDING.json` correctly excludes itself from its own `files` map (0 self-referencing keys), consistent with the recovered algorithm.

---

## 4. Historical evidence immutability (highest priority)

`historical_mbs195/IMMUTABILITY_AND_RENDER.json` reports `hashesBefore == hashesAfter` for all six historical artifacts (bundle JSON, TaskLog, contact sheet, and all three authority images), and `byteIdentity: true`. The three image hashes match the review request exactly:

- TOP `7009a2b685fd170c8f…60c24c49`
- FRONT `ff3d6931b1b4eb79ca…af00af58f`
- RIGHT `d787043b91dc58cb3c…518ce37c11`

FRONT and RIGHT are independently corroborated — these exact values appear in my own MBS-CR-0202 finding record ("Rejected MBS-195 inputs are not quarantined") from a prior session, where I recorded them directly against the real rejected files. The 1,290,626 ppm FAIL figure the request asks me to confirm also matches a measurement I recomputed directly from the real rejected bundle in a prior session ("the median recomputes to 1,290,626 from the ensemble").

**Code-level enforcement, not just attestation.** In the diff, every mutating route (`/bundle/import`, `/bundle/approve`, `/bundle/discard`, `/contract/reverified`, `/authorization/preview`, `/authorization/approve`, `/provider/poll-and-capture`) now begins with `selected, historical = selected_runtime(); if historical: refuse`. `PilotSessionManager.discard_active_session()` only ever calls `.discard()` on the *active* runtime obtained via `active_runtime()` — there is no code path from any request handler to `historical_runtime.discard()`. The old "Discard and restart" button (`/bundle/discard`) is retargeted to the new isolated helper and additionally blocked outright when viewing historical.

**I did not just read this — I extracted the exact new logic verbatim and ran it.** See §6.

---

## 5. Clean new-session lifecycle

`start_track_s_session()` creates a fresh directory keyed by timestamp, writes a `TrackSExperimentSessionV1.json` identity with `inputKind: null`, `historicalWorkspaceInherited: false`, writes the active pointer via write-temp-then-atomic-`replace`, and — critically — **self-verifies** before returning: `if runtime is None or runtime.current_state() is not None: raise PilotError(...)`. A session that somehow started non-empty refuses to be handed back to the caller.

`test_mbs213_historical_multiview_and_new_track_s_session_are_isolated` (the new test, read in full) asserts, among other things: the historical page shows `Input kind</dt><dd>NOT SELECTED` and `Logged state</dt><dd>BUNDLE_APPROVED` simultaneously (reproducing the original MBS-213 symptom as the *historical* view's honest description of frozen history, not the active state); the freshly started session shows `Logged state</dt><dd>NO TASK LOG`; the historical file bytes are identical before and after the whole sequence; `/provider/submit` against the new session returns 409 and never calls the key loader or the transport (`key_calls == [] and transport.calls == []`).

No lifecycle states were added — `state.py` is untouched (§2), and the test imports `TRANSITIONS` from the same unmodified module.

---

## 6. Cross-run forgery resistance — independently executed, not just read

I extracted `PilotSessionManager.active_session_identity()` and `.historical_view_path()` verbatim from the diff into a standalone harness (no Flask, no PilotRuntime — just the exact logic under review) and ran adversarial cases against it:

| Attack | Result |
|---|---|
| Legitimate session identity | **ACCEPTED** |
| Forge `inputKind: "multiview_v1"` to claim historical carryover | **REFUSED** — "Track S session identity record is invalid" |
| Forge `historicalWorkspaceInherited: true` | **REFUSED** |
| Inject extra field `"forgedApproval": "BUNDLE_APPROVED"` | **REFUSED** |
| Inject extra field `"state": "BUNDLE_APPROVED"` | **REFUSED** |
| Pointer `sessionId` containing `../../etc` (path traversal) | **REFUSED** — "identity is unsafe" |
| Pointer with tampered `schemaVersion` | **REFUSED** |
| Identity `sessionId` mismatched against pointer's `sessionId` | **REFUSED** |
| Session workspace directory is a symlink into another tree | **REFUSED** — "workspace is unavailable" |
| Historical bundle `path` field = `../secret.txt` | **REFUSED** — "path is unsafe" |
| Historical bundle `path` field = absolute `/tmp/secret.txt` | **REFUSED** |
| Historical bundle `path` field = empty string | **REFUSED** |
| On-disk file at the declared path is a symlink escaping the workspace | **REFUSED** — "file is unavailable" |
| Unknown role requested | **REFUSED** |

Every forgery/tamper/traversal attempt against the exact new isolation logic failed closed; the one legitimate case succeeded. This directly answers the request's §2 and §7 asks ("try to forge or copy historical `BUNDLE_APPROVED` evidence… ensure it fails closed").

The equality check in `active_session_identity()` (`identity != {...five exact keys...}`) is doing real work: because it's a full dict-equality comparison, **any** extra or renamed key fails it, not just the specific fields I guessed to attack.

---

## 7. Single-view routing and UI session separation

`reconstruction_input.py` and `track_s.py` (routing/quarantine/digest logic) are untouched — see §2 — so nothing about how `single_view_v1` routing or digest binding works could have regressed in this candidate; it is exactly the logic already accepted in MBS-CR-0035.

The template diff gates the TOP/FRONT/RIGHT import section behind `{% if pilot.session.historical or not pilot.session.sessionIsolationEnabled %}`, and the single-view section behind `{% if not pilot.session.historical %}` — so a freshly started Track S session's rendered page shows only the beauty-reference import form, and the historical page shows only the (locked, read-only) multiview section. `selected_runtime()` correctly defaults to the active session when one exists and falls back to historical otherwise, and `?view=historical` / `?view=active` allow explicit navigation without mutating anything (`GET`-only, and the new test hits both and confirms historical bytes are still unchanged afterward).

---

## 8. New findings

**MBS-214 — MINOR — `/bundle/import` is not scoped to Track S sessions at the transactional layer.**
The multiview-import route is blocked for `historical` but **not** disqualified for an *active* Track S session — it is only hidden by the template. A direct `POST /bundle/import` against a freshly created, empty Track S session workspace would currently succeed and turn that session into a multiview import, which is outside what "Track S single-view input binding" is supposed to permit. The new MBS-213 regression test does not exercise this path. This is the same category of gap this project has flagged before ("governance enforced at the UI layer, not the transactional core") — it doesn't touch historical evidence or bleed authorization, but it does let a Track S session become something other than a Track S session without any code refusing it. Recommend an explicit input-kind/session-kind guard on `/bundle/import` (and a regression test posting to it directly against an active session) before this is considered fully closed.

**MBS-215 — MINOR/OBSERVATION — `/artifact/preflight` has no `historical` guard.**
Every other mutating handler touched in this diff begins with `selected, historical = selected_runtime(); if historical: refuse`. `artifact_preflight()` is the one exception: `selected, _historical = selected_runtime(); report = selected.preflight(...)`. `PilotRuntime.preflight()` itself is pre-existing code outside this diff's scope, so I can't determine from what's supplied here whether it's side-effect-free (no network call, no evidence write) when run against the historical runtime. Given the project's artifact-host policy work elsewhere, I'd want this confirmed explicitly, or the same guard added for consistency, before it's exercised against the historical view.

**Observation (non-blocking) — repeated "Start new Track S session" clicks silently orphan the previous active session.** No data is destroyed (satisfies the request's stated minimum bar), but the pointer moves to the new session with no warning, and there's no visible route to resume the abandoned one short of finding it on disk under `pilot_ui_sessions/`. Not a safety issue for no-spend testing; worth a UX note.

**Evidence-completeness gap (process, not defect).** This package supplies a diff + hash manifests + logs rather than a checked-out source tree, which is a step down from the fuller evidence format used in MBS-CR-0035 (where I had a real repository tree to walk and hash directly). I was able to substitute a strong indirect chain (§2) precisely because a prior review's real-byte verification of the parent state existed to reconcile against — that won't always be available. Recommend future evidence packages include either the full working tree or a mechanism to apply the diff against real parent bytes.

---

## 9. Reported test results — not independently re-executed

`gates/*.txt` report: Producer Ruff clean; full Producer suite 470 passed (348 warnings, all pre-existing Pillow deprecation noise, unrelated to this change); focused Track S/pilot/reconstruction/cross-view suite 181 passed; the exact new MBS-213 regression test 1 passed; Import Probe 39 passed and Ruff clean; Import Probe historical-baseline check PASS; v0.7.1 identity check PASS. These numbers match the review request's summary exactly, and the full-suite log leaks a real local path (`/Users/martinhlavacek/Documents/.../SkyForge-Mesh-Builder/...`), which is consistent with genuine local execution rather than fabricated text.

**I did not reproduce these myself.** Without the actual source tree at the candidate commit (§1, §12) there is nothing for me to run `pytest` against. I am relying on the logs as reported, corroborated only by internal consistency and by directly reading and executing the specific new logic under review (§6). This is a real, named limitation, not something I'm glossing over.

---

## 10. Provider boundary — respected during this review

I did not freshen the contract, access an API key, create an authorization preview, submit a task, poll, download, or consume credits at any point in this review. `NO_SPEND_ATTESTATION.json`'s self-report (`noApiKeyAccessed: true`, `noProviderContact: true`, `noCreditsConsumed: true`, `merged: false`, `released: false`) is consistent with everything else I found — no route touched by this diff calls the provider or key loader except the pre-existing, unmodified `/provider/submit` and `/provider/poll-and-capture` paths, both of which remain gated behind `sendable` and are refused for historical/new-unsendable sessions in the new test (`status_code == 409`, `key_calls == []`, `transport.calls == []`).

---

## 11. v0.7.1 isolation

`gates/v071_identity.txt` reports 1 passed for the byte-identity check; nothing in this diff touches any v0.7.1-preserved path (`server.py`, `index.html`, the legacy generator). No regression risk here by construction.

---

## 12. What this review does and does not establish

**Established, with executed evidence:**
- The evidence archive is exactly what it claims to be, byte-for-byte, twice.
- The candidate's declared file-hash map for 333 of 338 Producer-scope files is provably consistent with real bytes I verified myself at the parent commit two reviews ago.
- The new session-isolation and historical-immutability logic, extracted verbatim and executed standalone, resists every forgery/traversal/tamper attempt I threw at it.
- The diff touches exactly the declared 7 files and nothing security-critical outside that set.
- The MBS-195 evidence hashes and FAIL measurement match values I independently recorded in prior sessions.

**Not established by first-hand execution this session:**
- That the reported 470+181+39+1 test results actually pass against the real candidate tree today (I have no tree to run them against).
- That the 4 changed and 1 added file's *new* hash values correspond to the *exact* file contents shown in the diff (I trust the diff/hash pairing is self-consistent, which I verified, but did not compute a SHA-256 of the diff's post-image text myself against the claimed new hash for each file — this is possible to add as a stronger check if a future package includes it).
- Anything about `PilotRuntime.preflight()`'s side effects (pre-existing, unseen code) — see MBS-215.

Given the depth of independent verification that *was* possible — including genuinely executing the exact new tamper-resistance code against a battery of attacks, and a hash-reversal proof tying 333 files back to real, previously-verified bytes — I do not believe `REVIEW BLOCKED` is warranted here. The residual gap is narrower and better-characterized than a blanket "cannot verify."

---

## 13. Disposition of prior findings

Unchanged, as instructed and as structurally confirmed (none of the touched files intersect these):

MBS-136 OPEN · MBS-195 OPEN · MBS-199 OPEN · MBS-200 OPEN/partially remediated · MBS-201 OPEN · MBS-208 OPEN MINOR · MBS-209 OPEN MINOR · MBS-210 OPEN MAJOR · MBS-211 OPEN MINOR · MBS-212 OPEN OBSERVATION · MBS-183 standing requirement unchanged. MBS-198 and MBS-202 remain CLOSED (both closed prior to this candidate; nothing here regresses them — the FRONT/RIGHT quarantine hashes MBS-202 covers are, if anything, further corroborated in §4).

**MBS-213: CLOSED.** The remediation is architecturally sound, independently exercised against adversarial input, and does not weaken any previously-accepted control.

**New: MBS-214 (MINOR, open), MBS-215 (MINOR/OBSERVATION, open).** Neither blocks no-spend progression; both should be closed before this surface sees less-careful use or any real authorization.

---

## 14. Final verdict

**ACCEPT WITH REQUIRED CHANGES.**

Required before this is considered fully closed (not before resuming no-spend UI testing):
1. Close MBS-214 — scope `/bundle/import` to refuse against Track S sessions at the transactional layer, with a direct regression test.
2. Close or explain MBS-215 — confirm `/artifact/preflight` is side-effect-free against the historical runtime, or add the same guard.
3. For future evidence packages of this kind: include either the full source tree or a means to verify per-file hashes against real bytes directly, rather than relying on cross-session reconciliation as I did here.

**May Marty resume the human NO-SPEND Track S single-view input-binding and approval workflow on this exact candidate?**

**Yes.** Use the UI as designed — start a new Track S session, import the beauty reference, approve the exact digest. Do not craft direct API calls to `/bundle/import` against the new session (MBS-214), and avoid the "Artifact preflight" control on the historical/read-only page until MBS-215 is clarified. This is explicitly **not** authorization to freshen the contract, access an API key, preview or approve real authorization, submit a task, poll, download, merge, tag, or release.
