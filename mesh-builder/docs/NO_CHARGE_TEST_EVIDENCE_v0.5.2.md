# No-Charge Test Evidence — v0.5.2

## Paid-call statement

No live OpenAI image-generation or edit request was made during development or testing. Every transport-path test uses an in-memory fixture or a mock that raises a controlled exception.

## Executed result in the current environment

```text
70 passed across eight independently executed module commands
0 skipped
0 paid calls
```

This is the available 70-test non-Flask subset of the 82 test functions in source, not the complete release preflight. See `BUILD_VERIFICATION_v0.5.2.md` for the unavailable dependency-bound checks.

## Covered no-charge assertions

- all 36 official governed output-price cells;
- unknown model/quality/size rejection;
- output-only authority lower-bound estimate payload;
- output- and input-token actual-cost reconciliation;
- over-budget rejection with transport call count remaining zero;
- unwritable-ledger rejection with transport call count remaining zero;
- reservation creation, attempt count, usage capture, request ID, reconciliation, and cumulative totals;
- timeout and provider 5xx ambiguity retained as `possibly_charged` with no automatic retry;
- one transport call across two identical completed requests;
- a deleted or corrupted completed cache blocks a second paid dispatch;
- concurrent duplicate suppression;
- no plaintext API key in ledger, cache, source examples, provider errors, or configuration;
- no concept-run allocation for rejected concept validation;
- no job allocation for 422 workflow conflicts;
- no package/workspace/job/log/home/Blender absolute path in browser payloads;
- release sealer rejects version mismatches, skips, failures, archive residue, and failed commands.

## Critical transport-denial pattern

The budget and ledger tests use a transport function that increments a counter. The request is expected to raise before transport and the test asserts that the counter is still exactly zero. This proves the gate is placed before the billed call rather than merely reporting a denial after dispatch.

## Post-gate sealer regression

After MBS-GATE-0001, `tests/test_release_sealing.py` was rerun with **4 passed, 0 skipped, 0 failed**. The success fixture now verifies machine provenance, explicit `skipped: 0`, `zeroSkipsAsserted: true`, retained refusal evidence, retained gate decision, source checksum binding, and the outer Claude-package checksum sidecar. The hygiene fixture verifies that a local `.venv` is allowed as build state but excluded from the source archive, while runtime workspace and compiled residue remain blocking. No paid transport was invoked.
