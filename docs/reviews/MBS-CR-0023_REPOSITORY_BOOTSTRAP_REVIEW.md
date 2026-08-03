# MBS-CR-0023 — Repository Bootstrap Review (PR #1)

**Review ID:** MBS-CR-0023
**Repository:** `martyhlavacek/SkyForge-Mesh-Builder` (private)
**Pull request:** #1 — `bootstrap/v0.7.1-accepted-baseline`
**Head commit reviewed:** `629831032f13ce08f7d36e8ec2d65c8266b84572`
**Base commit:** `2f2a9494884b2ed7761d5db718c41fe21ab98b67`
**Reviewer:** Claude (independent adversarial reviewer)
**Evidence package:** `MBS-CR-0023_REVIEW_EVIDENCE.zip` — SHA-256 `3edc96cc43515490664451773c9f2498bdfbcd2e5cfa8320714f1eb359fdf316`
**Git bundle:** `MBS-CR-0023_EXACT_REPOSITORY.bundle` — SHA-256 `57e8581d845e95f2c1e751994f388caee4f46f66a9712b805efe2a58c6695ce0`

> ## VERDICT: **ACCEPT WITH REQUIRED CHANGES**
>
> Exact source preservation is **proven**: both accepted trees are byte-for-byte identical to
> the archives accepted in MBS-CR-0022, with zero modified files and both binding digests
> reproducing independently.
>
> One required change, CI-only and non-behavioural: the workflow declares no `permissions:`
> block, so least-privilege is not enforced at the artefact level (**MBS-160**).
>
> No product source defect. No user testing need be repeated. Paid-provider work remains unauthorized
> and MBS-136 remains open.

## 1. Integrity and binding

| Step | Result |
|---|---|
| Outer ZIP vs sidecar | `3edc96cc…fdf316` — **match** |
| `SHA256SUMS.txt` | **27 of 27 verify** |
| `git bundle verify` (run by me in a scratch repo) | *"is okay"*, 2 refs, **"records a complete history"**, no prerequisites |
| Clone from bundle into empty directory | success |
| `git rev-parse HEAD` after detached checkout | `629831032f13ce08f7d36e8ec2d65c8266b84572` — **exact match** |
| `refs/heads/main` in bundle | `2f2a9494884b2ed7761d5db718c41fe21ab98b67` — **exact match** |
| `git fsck --full` on my clone | clean |

**Ancestry independently established from the Git objects**, not from any assertion:

```
2f2a949  Create README.md                                  ← base main
  └─ d691f97  chore: import accepted v0.7.1 baseline
       └─ 438d675  ci: run producer checks in virtual environment
            └─ 6298310  ci: use runner temp for producer environment   ← PR head
```

Head's parent is `438d675…`; base is a direct ancestor; 4 commits total. Because a bundle
carries original commit and tree objects, these are cryptographic identities, not a
reconstructed equivalent.

## 2. Evidence classification

As requested, findings are separated by how they were established:

- **Independently established from the Git bundle:** all of §3 (source preservation), §4
  (hygiene, history, secret scan), §5 (CI workflow content), and the ancestry above.
- **Independently reproduced by execution:** all of §6.
- **Supported only by the authenticated `gh` export:** §7 — PR state, draft/unmerged status,
  check conclusions, and that `main` is unchanged. I have no direct GitHub access; these are
  attested, not independently verified.

## 3. Scope A — Exact source preservation: **PROVEN**

I compared both repository subtrees against the accepted archives I verified in MBS-CR-0022
(`e406fff9…aca83a4c` producer, `13d5472e…aaaa1475` probe), which I still hold.

| | Accepted tree | `mesh-builder/` / `import-probe/` | Modified | Only in accepted | Only in repo |
|---|---:|---:|---:|---|---|
| Producer | 291 files | 291 files | **0** | none | none |
| Import Probe | 65 files | 65 files | **0** | none | none |

(291 / 65 = the 290 / 64 protected files plus each binding JSON, which is excluded from its own
digest.) **Every file hash matches; not one accepted source file was modified during bootstrap.**

Binding digests recomputed by me directly from the repository trees:

| Component | Files | Digest | Binding JSON | Required |
|---|---:|---|---|---|
| Producer | 290 | `abe74a56…d210f45` | agrees | agrees |
| Import Probe | 64 | `88351057…34d74ba7` | agrees | agrees |

Per-file maps match the binding JSONs exactly. `producerSourceIncluded: false` confirmed on the
probe.

**Folder stripping:** the outer archive wrapper names (`SkyForge_Mesh_Builder_Sidecar_v0.7.1`,
`SkyForge_Sprite_Foundry_Import_Probe_v0.1.1`) were removed and contents placed at
`mesh-builder/` and `import-probe/`. Internal relative paths are unchanged — proven by the
zero-difference comparison above, which is path-sensitive. No flattening occurred.

**Executable permissions preserved:** all nine launcher/script files carry mode `100755`:

```
mesh-builder/Launch SkyForge Mesh Builder.command
mesh-builder/Run v0.7.1 Live Blender Preflight.command
mesh-builder/Seal v0.7.1 for Claude.command
mesh-builder/scripts/{configure_blender,configure_openai,lint,run,run_tests,setup}.command
```

No `.command` or `.sh` file lacks the bit. Note Git records only the executable bit, not full
POSIX modes; that is the property that matters for launch and sealing.

**Provenance correction (scope requirement):** confirmed on all three counts. It is documented
in `docs/baseline/BOOTSTRAP_PROVENANCE_CORRECTION_001.md`; the accepted tree was **not** altered
to accommodate the erroneous value (zero modified files above); and the corrected digest
`88351057…34d74ba7` is used consistently in `BASELINE_LOCK.json`, the correction document, and
the CI binding output. My own recomputation — third independent derivation across three reviews
— produces the same value. The document correctly assigns no product MBS finding, since this was
an external transcription error.

## 4. Scope B — Repository hygiene and security: **PASS**

`.gitignore` covers `.DS_Store`, `**/.venv/`, `**/__pycache__/`, `**/.pytest_cache/`,
`**/.ruff_cache/`, `**/config.json`, `**/workspace/`, `**/*.pyc`, `**/*.pyo`, `**/*.log`,
`**/dist/`, `**/build/`, `**/*_EXACT_CANDIDATE_WORK/`, `**/*_FAILURE_EVIDENCE_*.zip`.

**Path scan at HEAD and across every commit in history** — no tracked `.venv`, `config.json`,
`workspace/`, generated job, `.pyc`/`__pycache__`, cache directory, `.DS_Store`, `.env`, private
key, or generated review package. The only hits on my `keychain|secret|credential` pattern were
three legitimate source files (`app/macos_keychain.py`, a hotfix doc, and its test) — the
Keychain *integration module*, not Keychain *content*.

**Content-level secret scan across every blob in every commit** (`sk-`, `msy_`, `ghp_`,
`github_pat_`, `AKIA`, PEM private keys): the single match is
`msy_dummy_api_key_for_test_mode_12345678` — Meshy's **documented public zero-credit test-mode
key**, which I verified in the Meshy changelog during MBS-CR-0018 and which was adopted on my
own MBS-126 recommendation. Not a credential (**MBS-162**, informational).

**Fixtures correctly retained, not over-ignored:** 47 PNG, 100 JSON, 2 `.sfmeshpack`
(`import-probe/tests/fixtures/valid_embedded.sfmeshpack`, `valid_hash_only.sfmeshpack`), and the
MBS-155 regression fixture `mesh-builder/samples/rejected_three_quarter_beauty_mbs155.png`.
`config.json.example` is correctly tracked while `config.json` is ignored.

No unrelated personal files. Repository root contains only `README.md`, `BASELINE_LOCK.json`,
`.gitignore`, `.github/`, `docs/`, `mesh-builder/`, `import-probe/`.

## 5. Scope C — Baseline and governance records: **ACCURATE**

`BASELINE_LOCK.json` records every identity I independently verified — reviewed candidate
`d896ec9e…67862ea`, both archive SHAs, both file counts (290 / 64), both binding digests
including the corrected probe value, `claudeVerdict: ACCEPT`, `mbs155UserRegression: PASS`,
`vmpIndependentImportProbeUserTest: PASS`, `paidProviderWorkAuthorized: false`, and open findings
MBS-136, MBS-150–154, MBS-158, MBS-159. Every checkable value is correct.

`docs/findings/OPEN_FINDINGS.md` lists all eight open findings and states plainly that the
accepted v0.7.1 baseline contains no geometry fix for MBS-150 through MBS-154.

`docs/testing/V0.7.1_USER_TEST_STATUS.md` records the MBS-155 rejection before job creation, the
valid-authority pass, Blender IoU `0.975865` (matching the `approved_gunship` value I verified in
MBS-CR-0022), independent Import Probe acceptance with package digest and transport SHA, no paid
provider, and that MBS-158/159 were worked around **without modifying reviewed v0.7.1 source** —
consistent with the zero-modification result in §3.

`docs/reviews/MBS-CR-0022_ACCEPT_STATUS.md` deserves specific credit. It records the verdict and
the two informational findings, then states: *"Full reviewer-authored text has not yet been
imported into Git and must not be reconstructed or paraphrased as though it were the original
review."* **Nothing is fabricated or reconstructed.** That is exactly the right posture and it
directly satisfies the scope-C requirement.

`README.md` correctly states the three-party workflow, that no paid provider work is authorized,
that MBS-136 remains open against a real provider, and that no geometry fix is claimed.

## 6. Scope E — Independent execution: **ALL TARGETS MET**

**Reviewer-environment deviation, recorded as permitted:** Python 3.11 is not installable in my
environment (apt and the deadsnakes PPA are network-blocked), so I used clean, from-contract-only
**Python 3.12** virtual environments created outside the repository. All four deviation
conditions are satisfied: the deviation is recorded here; the exact 3.11 Actions evidence is
inspected below; both complete suites reproduce under 3.12; and no defect is concealed — the CI
logs and my runs agree on every count and digest.

| Check | Required | My result (3.12) | CI evidence (3.11.15) |
|---|---|---|---|
| Producer pins | 12 exact | 12 exact | — |
| Producer Ruff | clean | **All checks passed** | passed |
| Producer suite | 244 passed, 0 skipped | **244 passed, 0 skipped, 0 failed, 0 errors** | `244 passed` |
| Producer binding | 290 / `abe74a56…d210f45` | **verified: True, 290, `abe74a56…d210f45`** | same digest in log |
| Probe pins | 8 exact | 8 exact | — |
| Probe Ruff | clean | **All checks passed** | passed |
| Probe suite | 39 passed, 0 skipped | **39 passed, 0 skipped, 0 failed, 0 errors** | `39 passed` |
| Probe binding | 64 / `88351057…34d74ba7` | **verified: True, 64, `88351057…34d74ba7`** | same digest in log |
| Flask absent | required | **absent** | — |
| SciPy absent | required | **absent** | — |
| Producer `app`/`common` imports in probe | none | **none** | CI check passed |

The probe suite ran with `PYTHONPATH` unset and `PYTHONNOUSERSITE=1`. CI logs confirm
`python-3.11.15` was used on the runner, so the 3.11 result is directly evidenced even though I
executed under 3.12.

## 7. Scope D — CI independence and correctness

Assessed from the exact `.github/workflows/ci.yml` at head.

| # | Requirement | Result |
|---|---|---|
| 1 | Separate dependency environments | **Yes** — two independent jobs |
| 2 | Producer installs only `mesh-builder/requirements.txt` | **Yes** (`working-directory: mesh-builder`) |
| 3 | Probe installs only `import-probe/requirements.txt` | **Yes** |
| 4 | `PYTHONNOUSERSITE=1` enforced | **Yes** — job-level `env` on both |
| 5 | `PYTHONPATH` unset for probe | **Yes** — `unset PYTHONPATH` in every probe step |
| 6 | Producer uses a real venv under runner temp | **Yes** — `$RUNNER_TEMP/producer-venv`, all steps invoked via its interpreter. This is precisely the correction made by commits `438d675` and `6298310` |
| 7 | Ruff for both | **Yes** |
| 8 | Complete suites | **Yes** — `pytest -q`, unfiltered |
| 9 | Source bindings independently verified | **Yes** — both jobs |
| 10 | Probe cannot import producer modules | **Yes** — dedicated step scanning `probe/**/*.py` for `from app`, `import app`, `from common`, `import common` |
| 11 | No secrets, provider calls, paid actions, production credentials | **Yes** — no `secrets.*` reference anywhere; no network beyond PyPI |
| 12 | **Least-privilege permissions** | **NO** — see MBS-160 |
| 13 | No `pull_request_target`; no untrusted code with elevated credentials | **Yes** — triggers are `push` and `pull_request` only |

**Node 20 deprecation — informational only; no action required before merge.** The single CI
annotation is: *"Node.js 20 is deprecated. The following actions target Node.js 20 but are being
forced to run on Node.js 24: actions/checkout@v4…"*. GitHub is already force-running these on
Node 24, so behaviour is unaffected; it concerns the Actions runtime, not workflow correctness or
security. Bump to newer action majors at convenience.

## 8. Scope F — GitHub status (attested, not independently verified)

From the authenticated `gh` export. I have no direct GitHub access, so these are **attested**:

| Item | Evidence |
|---|---|
| PR state | `OPEN` (`pr-view.json`), `open` (`pr-api.json`) |
| Draft | `isDraft: true`, `draft: true` |
| Merged | `merged: false`, `merged_at: null` |
| `headRefOid` | `629831032f13ce08f7d36e8ec2d65c8266b84572` |
| `baseRefOid` | `2f2a9494884b2ed7761d5db718c41fe21ab98b67` |
| `headRefName` | `bootstrap/v0.7.1-accepted-baseline` |
| Merge state | `CLEAN` / `mergeable_state: clean` |
| Check runs (exact head) | 4 runs, all `completed` / `success`: Producer ×2, Import Probe ×2, every `head_sha` = `6298310…b84572` |
| Workflow runs | `30783081091` (push) and `30783083117` (pull_request), both `success` at the exact head |

Head and base OIDs in the export match what I established cryptographically from the bundle,
which is meaningful cross-corroboration. Draft/unmerged state and "`main` unchanged" remain
attested only.

**This limitation is smaller than it appears.** I do not need GitHub's check *conclusions* to be
trustworthy, because scope E had me re-run Ruff, both complete suites and both binding
verifications myself — direct evidence that is stronger than a green check. What genuinely rests
on attestation is PR lifecycle state, which bears on a merge *recommendation*, not on any
correctness finding.

No tokens, credential configuration, environment secrets or unrelated account data appear in the
export. I scanned the complete logs for credential patterns: none. `MANIFEST.md` records no field
substitutions were needed and complete logs were available for both runs — consistent with what I
found.

## 9. Findings

### Blocking
None.

### Major
None.

### Minor

**MBS-160 — CI workflow declares no `permissions:` block, so least-privilege is not enforced at
the artefact level.**
`.github/workflows/ci.yml` sets no workflow-level or job-level `permissions:`, so the
`GITHUB_TOKEN` scope falls back to the repository/organisation default, which cannot be
determined from the bundle or the evidence export. Scope D item 12 requires least-privilege; as
written it is unverifiable rather than demonstrably wrong.

Exploitability here is low — the workflow never uses the token, triggers are `push` and
`pull_request` (fork PRs receive a read-only token regardless), and there is no
`pull_request_target` or untrusted-code execution path. But this project's governing principle is
that controls belong in the artefact, not the environment, and a one-line addition makes the
property provable from the workflow file alone.

**Required change:** add at workflow level:

```yaml
permissions:
  contents: read
```

No other change is required, and this touches no product source.

### Informational

**MBS-161 — Probe job installs into the `setup-python` tool-cache interpreter rather than a
venv, asymmetric with the producer.** Isolation still holds: the probe runs as a separate job on
a separate runner, and I independently confirmed Flask and SciPy are absent from a clean
from-contract-only environment. Note also that CI itself does not assert producer-dependency
absence — it proves the probe's *source* has no producer imports, not that its *environment*
lacks producer packages. Consider mirroring the producer's `$RUNNER_TEMP` venv and adding an
explicit Flask/SciPy absence assertion.

**MBS-162 — Meshy public test-mode key string is present in tracked source.**
`msy_dummy_api_key_for_test_mode_12345678` is Meshy's documented, intentionally public,
zero-credit test key, adopted per MBS-126. It is not a credential. Recorded so a future automated
secret scanner flagging it is understood as a false positive.

**MBS-163 — Dependency pins are exact `==` but not hash-pinned.** Neither `requirements.txt` uses
`--require-hashes`, so a compromised PyPI artefact published under a pinned version would install.
This matches the accepted upstream contract and is not a bootstrap regression; noted as a
supply-chain consideration for a future hardening pass.

## 10. Required explicit statements

1. **Is exact source preservation proven?** **Yes.** Both accepted trees are byte-for-byte
   identical to the archives accepted in MBS-CR-0022 — zero modified files, zero additions, zero
   omissions — and both binding digests reproduce independently from the repository trees.

2. **Is repository bootstrap provenance trustworthy?** **Yes.** Identity is established
   cryptographically from original Git objects, not assertion; the provenance correction is
   documented, correct, and did not alter accepted source; and every governance record matches
   independently verified values. The MBS-CR-0022 status document explicitly declines to
   reconstruct the original review text.

3. **Does CI correctly preserve producer/probe independence?** **Yes, substantively** — twelve of
   thirteen requirements met, including separate environments, a real producer venv under runner
   temp, `PYTHONNOUSERSITE=1`, `PYTHONPATH` unset for the probe, both bindings verified, and an
   explicit producer-import prohibition. The single gap is permissions declaration (MBS-160),
   which does not affect independence.

4. **May PR #1 be marked ready and merged?** **Yes, after MBS-160 is applied.** Add the
   `permissions: contents: read` block, let CI re-run green on the new head, and the PR may be
   marked ready and merged. No other change is required. I am not authorising merge of
   `6298310…b84572` as-is, and I have not modified, commented on, or altered the PR.

5. **May a baseline tag be created after merge?** **Yes**, once the merge commit contains this
   exact preserved source. The tag should reference `BASELINE_LOCK.json` and both binding digests.
   Recommend the tag record that it certifies *repository bootstrap fidelity*, not any geometry
   improvement.

6. **Must any user testing be repeated?** **No.** The bootstrap changed no executable product
   source — proven by zero-file-difference against both accepted trees — and revealed no product
   defect. All three findings are CI or documentation matters. The MBS-CR-0022 user-testing
   authorization and the recorded MBS-155 PASS remain valid.

7. **Paid-provider work and MBS-136:** **No paid-provider work is authorized.** No production
   Meshy credential, paid task, texture, remesh, multi-image or credit spend. **MBS-136 remains
   OPEN against a real provider** — mock orphan-unique and orphan-ambiguous evidence de-risks the
   design but is not real-provider correspondence proof. MBS-150 through MBS-154 remain open
   geometry-quality findings; MBS-158 and MBS-159 remain open macOS usability findings; and the
   accepted v0.7.1 baseline claims no geometry fix — structurally guaranteed, since
   `app/authority_mesh.py` and `blender/build_asset.py` are byte-identical to the accepted tree.

## 11. Reviewer actions

I did not modify, stage, commit, push, merge, tag, release, or comment on the PR. All work was
performed in throwaway directories outside any repository: the evidence extraction, a scratch
repo for `git bundle verify`, a clone from the bundle, and two clean virtual environments. The
only artefact produced is this document.

---

**Finding numbering continues from MBS-164.**
