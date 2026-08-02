# MBS-CR-0010 — Final Verification and Clearance: SkyForge Mesh Builder Sidecar v0.5.3

**Reviewer:** Claude (independent adversarial reviewer)
**Date:** 31 July 2026
**Scope:** MBS-83 / MBS-84 completion, and production of the sealed v0.5.3 release.
**Paid API calls made:** none.

---

# VERDICT: **GO — v0.5.3 is sealed. Keychain testing may resume.**

**MBS-83 CLOSED. MBS-84 CLOSED.** All five verification gates pass, and the sealed archive is **bit-identical** to the candidate I reviewed.

Paid image generation stays gated behind one live check, described in §7.

---

## 1. Identity — **PASS**

| Artifact | Claimed | Computed | Result |
|---|---|---|---|
| Outer package | `3dbdbd3e…c5f9f` | `3dbdbd3e668f454631c358c955ae4593fcde13857972b190de3cc178ed5c5f9f` | **Match** |
| Candidate source | `db7d55a4…4586d3` | `db7d55a4495bac3f338ddac5de4bca7624997be126c110384f58fc199f4586d3` | **Match** |
| Candidate sidecar | — | `db7d55a4…4586d3` | **Match** |
| Base | — | `28816ac1cddb7d84ab6b70e4deb5a5297b3ad282791d05d6f64f9c3ff641bc0b` | **Match — the MBS-CR-0009 hotfix candidate** |
| `SHA256SUMS.txt` (11 files) | — | **11/11 `OK`** | **Pass** |

Chain of custody is unbroken across four hops: `818d6b57` (cleared v0.5.2) → `28816ac1` (hotfix) → `db7d55a4` (completion).

## 2. Scope — **within bounds, and the extra change was correctly disclosed**

```
base 147   candidate 147
ADDED (0) · REMOVED (0) · CHANGED (5) · UNCHANGED 142/147
```

| File | Change | Assessment |
|---|---|---|
| `tests/test_macos_keychain_runtime.py` | Unused `pytest` import removed | Exactly the supplied line |
| `BUILD_INFO.json` | `0.5.3-keychain-hotfix-candidate` → `0.5.3` | Correct — `-candidate` dropped as recommended |
| `app/server.py` | Same version string, one line | No route, handler, budget or estimator touched |
| `scripts/seal_release.py` | `VERSION = '0.5.3'`, plus generated filenames now derived from `VERSION`, tempdir prefix, argparse text | **Better than my patch** — see below |
| `tests/test_release_sealing.py` | Hardcoded `v0.5.2` expectations replaced with `f'…v{seal_release.VERSION}…'` | The disclosed extra change; correct |

**No pricing, budget, ledger, cache, governance, Keychain, geometry, provider or v0.6 change entered this completion.** `app/macos_keychain.py`, `app/settings_store.py`, `common/image_pricing.py`, `common/spend_ledger.py`, `app/image_governance.py` and all Blender code are byte-identical to the MBS-CR-0009 candidate I already reviewed.

### 2a. Sol improved on the supplied patch

My MBS-84 patch changed only `VERSION = '0.5.2'` → `'0.5.3'`. Sol also replaced the hardcoded generated filenames:

```python
-        build_verification = staging / 'BUILD_VERIFICATION_v0.5.2.md'
+        build_verification = staging / f'BUILD_VERIFICATION_v{VERSION}.md'
-        binding = staging / 'CLAUDE_REVIEW_BINDING_v0.5.2.json'
+        binding = staging / f'CLAUDE_REVIEW_BINDING_v{VERSION}.json'
```

That is the correct generalization. My patch would have produced a v0.5.3 archive alongside a `BUILD_VERIFICATION_v0.5.2.md` — a new inconsistency in place of the old one. Deriving from `VERSION` means the next version bump is a one-line change with no stragglers, and the same reasoning applied to `test_release_sealing.py` turned a hardcoded expectation into a derived one.

### 2b. The disclosed extra change was necessary, not scope creep

Sol reported: *"I also corrected a stale test expectation that still hard-coded the generated review package as v0.5.2; applying only Claude's two supplied lines would have left that test failing."*

Confirmed, and correct. `test_release_sealing.py` asserted literal `v0.5.2` filenames, so bumping `VERSION` without it would have produced a red suite and a refused seal. Sol found a defect in my patch, fixed it in the right direction, and said so plainly rather than folding it in silently. That is exactly the behaviour that makes this review loop work.

Note also what was correctly **left alone**: the historical `MBS-RES-0012_v0.5.2.md`, `COST_ARCHITECTURE_v0.5.2.md`, `MBS-GATE-0001_v0.5.2_…md` filenames are records of past versions and keep their names. `copy_release_documents()` resolved without a `SealError`, which was the risk I flagged.

---

## 3. Complete pinned preflight — **PASS (5/5)**

| # | Gate | Result |
|---|---|---|
| 1 | Exact dependency conformance | **9/9** — `Flask 3.1.1 · Werkzeug 3.1.7 · blinker 1.9.0 · Pillow 11.3.0 · numpy 2.3.5 · trimesh 4.11.1 · pytest 8.4.1 · ruff 0.15.22 · requests 2.32.3` |
| 2 | `ruff check .` | **`All checks passed!` — exit 0** |
| 3 | `pytest -q` (complete, no filter) | **86 passed** — `tests=86 skipped=0 failures=0 errors=0` |
| 4 | Workspace-safety probe (MBS-82 regression) | **PASS** — see below |
| 5 | Pristine transactional seal | **exit 0**, 17 artifacts |

### 3a. Workspace-safety probe

Planted a realistic pre-existing workspace containing a spend ledger:

```
$ echo '{"real":"user ledger data"}' > workspace/_concepts/spend_ledger.json
$ python3 scripts/seal_release.py
RELEASE NOT SEALED: Archive hygiene failed:
- forbidden directory residue: workspace
- forbidden directory residue: workspace/_concepts
exitCode=1   artifacts published: 0

user ledger preserved: YES
content:               {"real":"user ledger data"}
```

The MBS-82 guarantee survives the hotfix intact: a genuine developer workspace still fails hygiene and is **not** deleted. This is the check worth repeating every round, because a careless change here silently destroys a user's spend record.

### 3b. Pristine seal

```
pristine workspace/: NONE
$ python3 scripts/seal_release.py --output-dir …
RELEASE SEALED: …/SkyForge_Mesh_Builder_Sidecar_v0.5.3_RELEASE
exitCode=0
```

**MBS-84 confirmed resolved** — the generated artifacts now carry the correct version and no longer collide with the cleared v0.5.2 release:

```
SkyForge_Mesh_Builder_Sidecar_v0.5.3.zip           (+ .sha256)
BUILD_VERIFICATION_v0.5.3.md
CLAUDE_REVIEW_BINDING_v0.5.3.json
SkyForge_Mesh_Builder_Claude_Review_Package_v0.5.3.zip  (+ .sha256)
RELEASE_SEAL_EVIDENCE.json
+ 8 historical release documents, release_sealer_refusal.txt, post_gate_sealer_refusal.txt
```

**No residue:** no `workspace/`, zero caches, one staging directory (the atomic release set).

---

## 4. Sealed release integrity

All four assertions agree:

```
sealed source SHA-256 : db7d55a4495bac3f338ddac5de4bca7624997be126c110384f58fc199f4586d3
its .sha256 sidecar   : db7d55a4…4586d3
RELEASE_SEAL_EVIDENCE : db7d55a4…4586d3
CLAUDE_REVIEW_BINDING : db7d55a4…4586d3
```

**The sealed archive is bit-identical to the candidate I reviewed** — not merely content-equivalent. In v0.5.2 the two hashes differed by ZIP container metadata; here the sealer reproduced the candidate archive exactly, which means Sol's packaging and the sealer's `build_source_zip()` are now deterministically aligned. Content check confirms it independently: 147/147 files, zero added, removed or changed.

Machine-generated evidence:

```json
"version": "0.5.3"
"ruff":   { "returncode": 0, "stdout": "All checks passed!\n" }
"pytest": { "executed": 86, "skipped": 0, "zeroSkipsAsserted": true,
            "failures": 0, "errors": 0, "returncode": 0 }
"archiveHygiene": "pass"
```

---

## 5. Finding disposition

| ID | Status |
|---|---|
| **MBS-83** — unused import blocks lint | **CLOSED** — ruff exit 0, verified |
| **MBS-84** — sealer version marker | **CLOSED** — artifacts correctly named v0.5.3; filenames now derived |
| **MBS-82** — sealer hygiene/preflight conflict | **Still closed**, regression-verified this round |
| **MBS-76 / MBS-77** | Closed in MBS-CR-0008, unaffected |
| Keychain OSStatus ABI defect | **Fixed in source and regression-covered.** Awaiting one live confirmation (§7) |
| **MBS-78** — `gpt-image-1` token rates inferred, not published | **Open, non-blocking** |
| **MBS-79** — estimate/reconciliation basis mismatch, no divergence flag | **Open, non-blocking** |
| **MBS-80** — authority stages cannot produce transparent backgrounds | **Open, non-blocking** |
| MBS-70 – MBS-75 | Deferred to v0.6 (geometry) |

**My prior verdict on MBS-78, MBS-79 and MBS-80 is unchanged: they do not block v0.5.3.**

---

## 6. Seal provenance

Produced by me, executing Sol's **unmodified** `scripts/seal_release.py` against candidate `db7d55a4` in the exact pinned environment. **I changed no source this round** — both fixes are Sol's, in Sol's bytes, which is the condition under which I release a sealed build (the line held in MBS-CR-0007 and applied in MBS-CR-0008).

Sealing host is Linux x86_64, recorded in the evidence. If you prefer the seal to come off the Mac, run `scripts/seal_release.py` there after `setup.command`; since the archive is now bit-reproducible, it should produce **the same** `db7d55a4…4586d3`. That would be a useful thing to confirm once.

---

## 7. Clearance

**Keychain testing may resume on the sealed v0.5.3 release.**

**Paid image generation remains gated behind one live check.** The ABI defect is fixed in source, reproduced and regression-covered, but the fix has still never touched a real `Security.framework`. That is the same gap that produced this hotfix, and it closes with one three-step check that costs nothing:

1. **Settings → save the OpenAI API key.**
2. **Save it a second time.** This is the exact path that failed: `SecItemAdd` returns `errSecDuplicateItem`, which must now normalize to `-25299` and route to `SecItemUpdate`. In v0.5.2 it read as `4294941997`, missed the branch, and failed. **A second save is the real regression test.**
3. **Quit the app completely, relaunch, confirm the key is still present.**

If any step fails, capture the OSStatus from the error — it should now read as a small negative number such as `-25299` or `-128`, never a nine-digit positive. A nine-digit value would mean a normalization site was missed.

Only when all three succeed should paid image generation be enabled. Then:

- Start with the shipped budget defaults: **$0.05 per request, $0.50 per asset, $2.00 per session.**
- On the first governed call, compare `estimatedOutputCostUsd` against `calculatedActualCostUsd` in the ledger. **MBS-79** predicts systematic divergence purely from the basis difference — the estimate reads the per-image table, reconciliation reads the per-token rate. Divergence there is expected and is not overspend; a real overspend would show up as a budget refusal, not a reconciliation gap.

### Verify before installing

```bash
shasum -a 256 SkyForge_Mesh_Builder_Sidecar_v0.5.3.zip
# expect: db7d55a4495bac3f338ddac5de4bca7624997be126c110384f58fc199f4586d3
```

---

## 8. Summary

| Item | Result |
|---|---|
| Outer package `3dbdbd3e…c5f9f` | **Verified** |
| Candidate `db7d55a4…4586d3` | **Verified** |
| Base `28816ac1…41bc0b` | **Verified** — the MBS-CR-0009 candidate |
| Delta | **5 files, all in scope**; extra change disclosed and necessary |
| Unrelated source changes | **None** — 142/147 byte-identical |
| Dependencies | **9/9 exact** |
| `ruff check .` | **exit 0** |
| `pytest` | **86 passed, 0 skipped, 0 failed, 0 errors** |
| Workspace-safety probe | **PASS** — user data preserved, hygiene enforced |
| Pristine seal | **exit 0**, 17 artifacts, no residue |
| Sealed source SHA-256 | `db7d55a4…4586d3` — **bit-identical to the reviewed candidate** |
| MBS-83 / MBS-84 | **CLOSED** |
| MBS-78 / MBS-79 / MBS-80 | **Open, non-blocking — verdict unchanged** |
| **Keychain testing** | **CLEARED** |
| **Paid image calls** | **Gated on the three-step Keychain check in §7** |

---

Ten reviews in, the loop has settled into something worth naming. This round Sol found a defect in *my* patch — a stale test expectation that my two lines would have left failing — fixed it in the more general direction, and disclosed it unprompted. That is the same standard I have been applying in the other direction since MBS-27: measure rather than assert, and say what you actually did.

Save the key twice, relaunch, confirm it persisted. Then go generate something.
