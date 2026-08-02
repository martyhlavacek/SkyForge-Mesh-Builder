# MBS-144 — Interceptor profile and live-Blender baseline disclosure

The v0.6.0 / MBS-CR-0016 preflight incorrectly rendered all three fixtures through the
`enemy_gunship` profile at scale `1.0`. v0.7.0 corrected fixture resolution so the interceptor
uses its registered `enemy_interceptor` profile at scale `0.72`.

The geometry did not change. The generated interceptor GLB remains semantically and, within the
same environment, byte-identical to the cleared deterministic output. The smaller registered
profile occupies fewer pixels in the 96 px gameplay frame, so the measured live-Blender silhouette
IoU changed from `0.968064` to `0.952496`.

Forward live-Blender baselines for the registered per-fixture profiles are:

| Fixture | Profile | Scale | Forward baseline IoU | Release floor |
|---|---|---:|---:|---:|
| approved_gunship | enemy_gunship | 1.0 | 0.975865 | 0.94 |
| field_gunship | enemy_gunship | 1.0 | 0.947415 | 0.94 |
| interceptor | enemy_interceptor | 0.72 | 0.952496 | 0.94 |

The exact-candidate assembler verifies that the live report names the registered profile and records
these values within a `1e-6` tolerance. Any future movement must be disclosed and recalibrated rather
than silently accepted.
