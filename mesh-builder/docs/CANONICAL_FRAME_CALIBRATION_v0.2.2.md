# Canonical Frame Calibration — v0.2.2

The mesh-builder sidecar uses one orthographic frame across all governed craft profiles. It never zooms an individual craft to fill the frame, because that would erase the intended bomber/gunship/fighter/interceptor/drone size distinction.

## Evidence basis

The CR-0003 probe swept:

- five craft profiles;
- camera pitches `0°`, `20°`, `36°`;
- banks `−18°`, `0°`, `+18°`;
- thrusters off and on.

The maximum measured requirement was `8.364180`. Relative to the base span and largest profile, the minimum viable margin was:

```text
8.364180 / (5.5 × 1.15) = 1.322400
```

v0.2.2 governs a margin of `1.400000`:

```text
5.5 × 1.15 × 1.40 = 8.855000
```

This leaves `0.490820` world units, approximately 5.5% of the frame, above the measured fallback-fixture maximum.

## Runtime behaviour

The manifest records the calibration object. Blender separately measures the actual required frame for the current craft and bank/pitch settings. If the live requirement exceeds `8.855000`, the job fails with a clipping error. The camera is not silently refitted.

That failure means the current geometry does not fit the governed review frame. It does not by itself mean the provider is rejected; the result must be interpreted under the experiment protocol.
