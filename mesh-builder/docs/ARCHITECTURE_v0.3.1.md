# Authority Mesh Architecture v0.3.1

## Coordinate pipeline

```text
Authority image
  → target mesh (+X right, +Y forward, +Z up)
  → glTF encoding (x, z, -y)
  → independent GLB reload
  → emulated Blender import (x, -z, y)
  → target-coordinate reconciliation
  → live Blender import and repeated orientation guard
  → neutral and banking renders
  → clean normalized export
```

The generator and Blender renderer no longer rely on an implicit assumption that raw GLB coordinates are Z-up. The coordinate conversion is an explicit, measured contract.

## Effects quarantine

No thruster, exhaust or destruction geometry is generated. Effect development is downstream of mesh-identity acceptance and cannot affect the silhouette or framing gates.

## Fail-closed boundaries

- Authority Mesh always uses fixed +Y forward/+Z up target coordinates.
- Provider Mesh retains explicit source-axis controls.
- A generated mesh with height-to-planform ratio above 0.45 after emulated or live Blender import is rejected.
- Both target and emulated-Blender silhouette IoU must be at least 0.94.
- Live Blender silhouette IoU must be at least 0.90.
