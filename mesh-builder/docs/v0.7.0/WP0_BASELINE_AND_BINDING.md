# WP0 — Baseline Lock and Binding Continuity

## Verified identity

- Outer handoff bundle SHA-256: `2a7ef75bcb12dccaeb50cb7f3c5579e540f56696fa51e61dafa0551de0c66bdf`.
- Internal `SHA256SUMS.txt`: all entries passed.
- Exact baseline ZIP SHA-256: `68516def22275b0cb6d1fa0513097adfa717b9df584f81915922f6e62e64d106`.
- Baseline source binding: 196 files, digest `8bdf6a8a5ab2f995578902c96faae2cbb923a940c546533bc6baf799e0cbf0d7`.

## Baseline execution evidence

- Python compileall: passed.
- Non-Flask baseline tests available in the sandbox: 73 passed.
- Full collection is blocked because the sandbox package index could not supply the exact pinned Flask distribution; two Flask test modules could not import.
- The geometry test module exceeded the sandbox execution ceiling after seven tests and is not represented as passed.
- Ruff 0.15.22 is unavailable in this sandbox and is not represented as passed.
- Live Blender is not available here and remains mandatory on all three fixtures before exact-candidate review.

These are environment limitations, not waivers. MBS-140 clean producer and probe environments, full Ruff, zero-skip tests, and MBS-139 three-fixture live Blender evidence remain release gates.

## Binding design

`PRODUCER_SOURCE_BINDING.json` binds every producer source file except itself and ignored runtime residue. It separately binds the declared exact-pin dependency contract. Changed, added, and removed files are independently rejected. The Sprite Foundry Import Probe will be a sibling release with a different schema, implementation, dependency file, and binding; it is outside the producer tree and producer binding.

## Stop conditions retained

No paid Meshy call, production credential, AI texture/remesh/multi-image operation, ground role, fallback geometry, weakened IoU floor, or user test is authorized.
