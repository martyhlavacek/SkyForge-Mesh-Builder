# BUILD VERIFICATION — Mesh Builder Sidecar v0.5.2

**Date:** 30 July 2026  
**Status:** **IMMUTABLE ADVERSARIAL-REVIEW CANDIDATE; NOT CLEARED FOR USER TESTING**

## Purpose

This source tree is packaged as an immutable checksum-bound candidate for Claude's independent adversarial review. Candidate identity is supplied by the outer review package through:

- `SkyForge_Mesh_Builder_Sidecar_v0.5.2.zip`;
- its `.sha256` sidecar;
- `RELEASE_SEAL_EVIDENCE.json`;
- `CLAUDE_REVIEW_BINDING_v0.5.2.json`.

The source SHA-256 is intentionally not embedded inside this source tree because doing so would create a circular archive hash.

## Executed checks

| Check | Result |
|---|---|
| Exact v0.5.1 baseline checksum verification | PASS — `d58a7ba93f498fe0f843e8afc4fbdd7ee076faf22b3b159498b749e2608c30c5` |
| Baseline package inventory | PASS — 25/25 files |
| Python compilation | PASS |
| Jinja template parsing | PASS |
| JavaScript syntax | PASS |
| Available no-charge pytest modules | PASS — **70 passed, 0 skipped, 0 failed** |
| Paid OpenAI calls | **0** |
| v0.6 implementation | **0** |

## Checks not executable on this build host

The restricted build host cannot obtain the exact pinned Flask, Werkzeug, blinker, Pillow, pytest, Ruff and requests artifacts. A complete target-dependency preflight is therefore **unavailable**, not passed or predicted to pass.

A direct complete-suite attempt was executed and stopped during collection because Flask is unavailable. Raw output is included in the outer review package. Claude should treat this as a release-integrity review item, not as a candidate-identity failure.

## User-testing rule

Marty must not install, launch, or test this candidate. User testing remains withheld until:

1. Claude completes the independent review against the exact source SHA-256;
2. all blocking findings are resolved in a new exact candidate; and
3. the complete target dependency preflight is green with zero skips.
