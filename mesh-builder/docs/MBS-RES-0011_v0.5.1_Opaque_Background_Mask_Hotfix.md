# MBS-RES-0011 — v0.5.1 Opaque-Background Mask Hotfix

## Evidence received

The failed live job contained:

- a valid OpenAI-generated top-down interceptor authority;
- `authority_albedo.png`;
- an OBJ and MTL;
- no GLB, manifest, generation report, or Blender logs.

This established that failure occurred inside local authority-mesh generation, after OBJ creation and before Blender invocation.

## Reproduction

The exact returned authority reproduced:

```text
RuntimeWarning: invalid value encountered in sqrt
RuntimeError: Independent GLB export validation rejected the generated OBJ topology
```

Independent audit of the failed OBJ:

- vertices: 15,266;
- triangles: 30,812;
- connected components: 1;
- boundary edges: 0;
- non-manifold edges: 16;
- watertight: false.

## Root cause

The opaque-background mask calculation used signed 16-bit arrays:

```python
(pixels - bg) ** 2
```

A dark pixel against a light background can have a channel difference near 240. Squaring 240 exceeds the positive range of signed 16-bit integers, so the result overflowed before summation and square root. This generated negative values and NaNs, causing dark outline pixels to be inconsistently excluded from the silhouette.

## Fix

The calculation now converts source and background colours to `float32`, computes a float delta, and squares in float arithmetic.

## Result on the exact authority

- mask method: `corner_colour_distance_28`;
- vertices: 16,030;
- triangles: 32,056;
- boundary edges: 0;
- non-manifold edges: 0;
- target silhouette IoU: 0.948011;
- Blender-import emulation IoU: 0.953241;
- watertight GLB reload: true;
- winding consistent: true;
- all local generation gates: pass.

## Diagnostic improvement

Preparation failures no longer collapse to the generic message `Job preparation failed`. Future pre-Blender failures preserve the exact exception in `job.json` and a full traceback in `logs/preparation_error.log`.
