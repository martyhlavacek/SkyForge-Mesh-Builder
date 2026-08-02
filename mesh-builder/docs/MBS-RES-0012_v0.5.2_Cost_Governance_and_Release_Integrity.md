# MBS-RES-0012 — v0.5.2 Cost Governance and Release Integrity

**Source review:** MBS-CR-0005  
**Scope:** v0.5.2 only  
**Status:** implementation complete; release unsealed because complete pinned preflight is unavailable in the present environment

## Scope controls

No two-sided height field, edge convergence, higher work grid, albedo-removal geometry change, measured component/genus metrics, Meshy adapter, Hunyuan adapter, or multiview generation was implemented.

## Finding disposition

| Finding | Disposition | v0.5.2 evidence |
|---|---|---|
| MBS-61 expensive obsolete defaults | **Resolved** | Default exploration is gpt-image-2 low landscape n=2; all four stages have governed economy profiles. Current official catalog/deprecation status was rechecked on 30 July 2026. |
| MBS-62 no cost governance | **Resolved** | Fail-closed estimator, per-request/asset/session budgets, confirmation threshold, reserve→call→reconcile ledger, digest lock, and cache. |
| MBS-63 quality hardcoded/absent | **Resolved** | Model, quality, size, and count are Settings fields per stage and are written to run metadata, ledger, cache, and provenance. |
| MBS-64 usage discarded | **Resolved** | Usage and request ID are captured; actual output/input token cost is reconciled where official rates and detailed usage exist. |
| MBS-65 timeout silent-money path | **Resolved** | Timeout, connection, and provider-5xx ambiguity becomes `possibly_charged`; reservation remains; identical automatic retry is denied. |
| MBS-66 Ruff F821 / missing `Any` | **Code resolved; release verification pending** | `Any` is imported. Ruff is mandatory in the sealer, but Ruff 0.15.22 is unavailable in the present host and is not predicted to pass. |
| MBS-67 two stale endpoint tests | **Resolved in code; full execution pending** | Semantic workflow conflicts remain 422, are validated before allocation, and tests assert 422 plus no workspace job residue. Full Flask suite unavailable on this host. |
| MBS-68 Keychain key in process arguments | **Resolved in code; macOS runtime verification pending** | Replaced `security ... -w <key>` with native Security.framework `SecItem*` calls. No subprocess argv, environment, shell, or temporary-file secret channel. |
| MBS-69 rejected jobs allocate state/leak paths | **Resolved** | Complete deterministic validation precedes job allocation; all browser error/status/settings/health payloads redact local paths; dynamic status and filename values use text nodes rather than HTML injection. |
| MBS-70 asserted component count | **Deferred to v0.6.0** | Explicitly outside cost-only v0.5.2. Must be measured from independently reloaded mesh. |
| MBS-71 quantified 2.5D ceiling | **Accepted and deferred to v0.6.0** | No attempt to tune around the representation limit in this hotfix. |
| MBS-72 albedo-derived geometry | **Accepted and deferred to v0.6.0** | Geometry intentionally unchanged to preserve v0.5.1 baseline. |
| MBS-73 height gate not binding | **Accepted; no v0.5.2 change** | Gate remains unchanged; representation will be addressed first in v0.6.0. |
| MBS-74 grid/O(n²) distance transform | **Accepted and deferred to v0.6.0** | Vectorized higher-resolution grid remains the next geometry epoch. |
| MBS-75 image-centre mirroring | **Accepted and deferred after core v0.6.0 work** | No symmetry-axis refactor in this hotfix. |

## Review recommendations adjusted by current official evidence

Claude recommended a deprecated mini model for authority and suggested provider idempotency. Current official documentation changes those details:

1. The deprecated mini/1/1.5 models are not selected as new defaults; all stages use current `gpt-image-2`.
2. `gpt-image-2` does not support transparent output. v0.5.2 does not assert transparency and keeps the validated opaque-mask path.
3. No official Images API `Idempotency-Key` support was found. Local content-addressed caching and in-flight locking are mandatory; no unsupported header is sent.
4. Automatic 429/5xx retries were rejected for this epoch. Without documented provider idempotency, one governed paid dispatch is safer; ambiguous requests require reconciliation rather than automatic repeat.

## Release disposition

The implementation is not promoted to a candidate until `scripts/seal_release.py` runs against the exact dependency set and records Ruff 0, complete pytest with zero skips/failures/errors, clean archive hygiene, and the final SHA-256. Consequently no candidate ZIP, SHA sidecar, or checksum-bound Claude package has been issued from this environment.

## Post-gate release-integrity addendum — MBS-GATE-0001

Claude correctly rejected the unsealed development package before review because it contained no sealed source ZIP, source checksum sidecar, or `RELEASE_SEAL_EVIDENCE.json`. No MBS-CR number or finding number was consumed. The rejection is preserved verbatim as `MBS-GATE-0001_v0.5.2_Candidate_Identity_Rejection.md`.

The Mac sealing path was then audited and corrected before resubmission:

- `RELEASE_SEAL_EVIDENCE.json` now records sealing UTC time, operating system and release, architecture, Python version and implementation, exact dependency versions, complete Ruff evidence, complete pytest evidence, the integer skipped count, and `zeroSkipsAsserted`.
- The generated build-verification document records the sealing OS, architecture, Python runtime, dependency set, and exact executed/skipped/failure/error counts.
- The previous refusal evidence remains a top-level review artifact even after a successful seal.
- The final Claude review package receives its own adjacent SHA-256 sidecar in addition to the checksum-bound source candidate inside it.
- `.venv` and `.git` are now treated correctly as local build state that may exist on the sealing machine but is never archived. Runtime `workspace`, `config.json`, caches, compiled Python residue, and secrets remain release-blocking.
- A one-click `Seal v0.5.2 for Claude.command` rebuilds a clean exact virtual environment and invokes the transactional sealer. It makes no paid OpenAI request.
- The sealer’s success-path regression test verifies the source ZIP, source checksum, evidence, binding, retained refusal, retained gate decision, generated review ZIP, and review-package checksum sidecar.

This addendum does not assert that a sealed candidate exists. Candidate identity is established only when the Mac sealer exits zero and emits the release set atomically.
