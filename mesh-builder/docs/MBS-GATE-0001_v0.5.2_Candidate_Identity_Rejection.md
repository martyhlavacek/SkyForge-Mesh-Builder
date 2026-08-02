# MBS-GATE-0001 — Candidate Identity Rejection: SkyForge Mesh Builder Sidecar v0.5.2

**Submitted artifact:** `SkyForge_Mesh_Builder_Sidecar_v0_5_2_UNSEALED_Claude_Review_Package.zip`
**Reviewer:** Claude (independent adversarial reviewer)
**Date:** 30 July 2026

**Verdict: REJECT — candidate identity failure.**

No adversarial review has been performed. No `MBS-CR-0006` identifier has been issued and no findings have been recorded against this package. Section 6 explains why that restraint is deliberate rather than procedural.

This document is not numbered in the `MBS-CR` series, because the `MBS-CR` series is reserved for reviews bound to a checksummed candidate. It takes a `MBS-GATE` identifier so it does not consume a review number or disturb the finding namespace.

---

## 1. Exact candidate SHA-256 reviewed

**None. No candidate exists to hash.**

The gate instruction was: *"First compute the source ZIP SHA-256 yourself. It must match both the sidecar and RELEASE_SEAL_EVIDENCE.json. If any checksum differs, stop and return REJECT."*

The failure here is stronger than a mismatch. There is no source ZIP anywhere in the submission — not a wrong one, not a stale one, none:

```
$ find . -name '*.zip'        →  0 results
$ find . -name '*.sha256'     →  0 results
$ find . -name 'RELEASE_SEAL_EVIDENCE.json' → 0 results
```

`SOURCE/` contains an **unpacked working tree** of 140 loose files, not a sealed archive. A mutable directory has no identity: nothing binds the bytes I read to the bytes Marty would run. Every finding I issued would be unfalsifiable the moment a single file changed.

---

## 2. Required attachments — gate check

| # | Required artifact | Status |
|---|---|---|
| 1 | `SkyForge_Mesh_Builder_Sidecar_v0.5.2.zip` | **ABSENT** |
| 2 | `SkyForge_Mesh_Builder_Sidecar_v0.5.2.zip.sha256` | **ABSENT** |
| 3 | `RELEASE_SEAL_EVIDENCE.json` | **ABSENT** |
| 4 | `BUILD_VERIFICATION_v0.5.2.md` | Present, but inside the unsealed tree (`SOURCE/.../docs/`) |
| 5 | `MBS-RES-0012_…Cost_Governance_and_Release_Integrity.md` | Present, inside the tree |
| 6 | `COST_ARCHITECTURE_v0.5.2.md` | Present, inside the tree |
| 7 | `IMAGE_PRICING_PROVENANCE_v0.5.2.md` | Present, inside the tree |
| 8 | `NO_CHARGE_TEST_EVIDENCE_v0.5.2.md` | Present, inside the tree |
| 9 | `MBS-CR-0005_v0.5.1_Adversarial_Review.md` | Present, inside the tree |

**Three of nine required release artifacts are absent, and they are the three that constitute candidate identity.** Items 4–9 being present *inside* the unsealed tree does not satisfy the requirement, because their integrity is asserted by the same mutable tree they are meant to attest to.

---

## 3. Mechanical verification performed

Only gate checks were run. No candidate review, no paid API calls, no findings.

| Check | Result |
|---|---|
| Source ZIP present | **No** — 0 `.zip` files in the entire submission |
| Source ZIP SHA-256 computed | **Not possible** — no artifact |
| `.sha256` sidecar present | **No** |
| `RELEASE_SEAL_EVIDENCE.json` present | **No** |
| `SHA256SUMS.txt` present and internally consistent | **Yes — 140/140 files `OK`** |
| `SHA256SUMS.txt` covers a source ZIP | **No — 0 zip entries.** It attests loose files only |
| Self-declared status | `UNSEALED_REVIEW_NOTICE.md`: *"It is **not** the sealed v0.5.2 release candidate"* |
| Sealer refusal record present | `docs/NO_CHARGE_TEST_EVIDENCE_v0.5.2/release_sealer_refusal.txt`, `exitCode=1` |
| **Sealer refusal reproduced by execution** | **Yes** — ran `scripts/seal_release.py` here; refused with `exitCode = 1` |
| Partial release artifacts left behind by the refused seal | **None** — correct transactional behaviour |

The sealer refusal is not a narrated claim. I executed `scripts/seal_release.py` in this sandbox and it refused independently, listing *my* environment's mismatches (Pillow 12.1.1, numpy 2.4.4, trimesh 4.12.2, pytest 9.1.1, requests 2.33.1) rather than replaying Sol's recorded list. It produced no ZIP, no checksum and no evidence file. That is the behaviour a transactional sealer should have, and it is the reason this submission is honest rather than broken.

*(One correction to my own working notes: an initial run appeared to exit 0. That was `tail`'s exit code through a pipe, not the sealer's. Measured without the pipe, the sealer exits 1. I am recording this because a false finding against a correctly-behaving gate would have been the worst possible outcome of this review.)*

---

## 4. What Sol did right, and it matters

This is a good failure, and I want to be explicit about that before the rejection stands.

Across four prior reviews, the recurring defect in this project has been **asserting what could be measured** — hardcoded evidence booleans, vacuous gates, predicted-green preflights. The obvious way for Sol to have handled a failing dependency check was to zip the tree, hand-write a checksum, and call it a release candidate. Instead:

- the **transactional sealer refused and produced nothing** — no partial ZIP, no orphan checksum;
- the refusal was **recorded with its exit code** as evidence rather than summarised;
- the package was **renamed `UNSEALED`** in the filename itself, so the failure is visible before anything is opened;
- `UNSEALED_REVIEW_NOTICE.md` states plainly *"Claude should review this exact package as a development candidate and should not treat it as release-accepted."*

That is precisely the discipline MBS-CR-0002 through -0004 were asking for, applied to the release process itself. The gate worked. Sol did not try to talk its way past it, and it did not predict a green result it could not produce — which is the specific error that produced MBS-46 and MBS-67.

---

## 5. The structural problem that will repeat unless it is fixed now

`scripts/seal_release.py` requires this exact set before it will produce anything:

```
Flask 3.1.1 · Werkzeug 3.1.7 · blinker 1.9.0 · Pillow 11.3.0 · numpy 2.3.5
trimesh 4.11.1 · pytest 8.4.1 · ruff 0.15.22 · requests 2.32.3
```

Sol's build environment could not supply Flask, Werkzeug, blinker or ruff at all, and had wrong versions of Pillow, pytest and requests. Mine could not either. **The sealer's own contract is unsatisfiable in the environment where Sol builds.**

This is not a bug in the sealer — the exactness is the point, and it is what makes the seal meaningful. But it means the sealing step cannot live with Sol. Left as it is, the next cycle produces another unsealed package for the same reason.

**The seal must be produced on Marty's Mac**, after `scripts/setup.command` installs the pinned set into the virtualenv, by running `scripts/seal_release.py` there. That is the only machine in this workflow that can satisfy the contract. Sol's deliverable should be the working tree; the sealed candidate is Marty's build step, and its output — ZIP, `.sha256`, `RELEASE_SEAL_EVIDENCE.json` — is what comes to me.

---

## 6. Why no findings were issued

I could review the source. I have it, it is internally consistent, and two advisory spot-checks came back clean: `from typing import Any` is now present at `app/openai_client.py:7` (the MBS-66 regression), and no Meshy, multiview, provider-adapter or two-sided-height-field code has leaked into this hotfix. The one `Hunyuan` string is a pre-existing provenance-form default in `index.html:161`, from the MBS-11 work — not v0.6 scope.

Those observations are **advisory only. They are not findings, they carry no MBS number, and they must not be cited as closures.**

The reason is the one this review lineage has been enforcing all along. A finding is only worth anything if it is bound to something that cannot change underneath it. `MBS-CR-0005` is quotable today because `d58a7ba9…c30c5` names an exact set of bytes. If I issue `MBS-76` against a loose directory, then in a week nobody — not Sol, not Marty, not me — can say which bytes it referred to, and "MBS-76 closed" becomes an assertion with no measurement behind it.

That is the same defect class as `componentCount = 1` and `neutralPoseRestoredBeforeExport: True`, relocated from the code into the review process. Issuing findings here would mean I had failed the standard I have been holding Sol to for four rounds. Consuming `MBS-CR-0006` on an unsealed tree would also make the next real review non-consecutive, which is a small permanent cost for no gain.

---

## 7. May Marty begin user testing?

**No — and this is explicitly not a judgement about quality.**

I have not reviewed the cost governance, the 36 pricing cells, the budget enforcement, the ledger, the cache, the Keychain handling, or the release sealer's success path. I do not know whether v0.5.2 is good. What I know is that there is no artifact whose identity can be fixed, so there is nothing to grant clearance *to*.

Two specific reasons user testing should wait:

1. **v0.5.2 is the release that decides whether the sidecar can spend money safely.** MBS-CR-0005 found no estimate, no cap, no cache, no idempotency and no `usage` capture. Until the budget gate has been adversarially reviewed against a fixed candidate, a user-testing session is a session with an unaudited payment path. The unverified thing is precisely the thing that spends.
2. **Testing an unsealed tree produces unciteable evidence.** If Marty finds something, we cannot say which build it was found in — which is the same trap that made the v0.5.1 preflight claim unfalsifiable.

The wait should be short. Nothing here suggests the work is wrong; the packaging step simply has not run yet.

---

## 8. Required to lift this rejection

On Marty's Mac:

```bash
scripts/setup.command                      # install the exact pinned set into the venv
scripts/seal_release.py                    # must exit 0 and produce all three artifacts
```

Re-submit when the sealer emits, together:

1. `SkyForge_Mesh_Builder_Sidecar_v0.5.2.zip`
2. `SkyForge_Mesh_Builder_Sidecar_v0.5.2.zip.sha256`
3. `RELEASE_SEAL_EVIDENCE.json` — containing the source SHA-256, the resolved dependency versions, the ruff result, and the pytest counts with **zero skips**
4. `BUILD_VERIFICATION_v0.5.2.md` regenerated by the sealer from the executed run, not hand-written
5. Items 5–9 as before

Three requests for the resubmission, each addressing something this cycle exposed:

- **Have the sealer record the machine it sealed on** — OS, Python version, resolved dependency versions — inside `RELEASE_SEAL_EVIDENCE.json`. The seal should state where it was produced, not just what it contains.
- **Have the sealer assert `skipped == 0` explicitly and record the number**, rather than only asserting `collected > 0`. A zero-skip claim should be a recorded integer. Sol's build verification for v0.5.1 predicted green for modules it could not run (MBS-67); the sealer is the right place to make that structurally impossible.
- **Keep the refusal evidence in the next package even when the seal succeeds.** A sealer that has been observed refusing is more trustworthy than one only ever observed succeeding, and `release_sealer_refusal.txt` is now part of the evidence that the gate is real.

I will run the full adversarial review — all sixteen verification areas, the complete MBS-CR-0005 disposition audit, and findings continuing at MBS-76 — against the sealed candidate, on the same day it arrives.

---

## 9. Summary

| Item | Result |
|---|---|
| Candidate SHA-256 | **None — no source ZIP exists** |
| Verdict | **REJECT — candidate identity failure** |
| Review performed | **None.** Gate checks only |
| Findings issued | **None.** `MBS-CR-0006` not consumed; series resumes at `MBS-76` when a sealed candidate arrives |
| MBS-CR-0005 disposition audit | **Not performed** — requires a bound candidate |
| User testing clearance | **Withheld**, pending a sealed candidate and its review |
| Blocking cause | Pinned dependency set unavailable in Sol's build environment; sealer correctly refused |
| Path forward | Seal on Marty's Mac after `setup.command`; resubmit the three identity artifacts |

The gate did its job. Sol respected it and said so plainly. The correct response from me is to respect it too, rather than to review the tree anyway because it happens to be in front of me — which would quietly teach the workflow that the seal is optional.
