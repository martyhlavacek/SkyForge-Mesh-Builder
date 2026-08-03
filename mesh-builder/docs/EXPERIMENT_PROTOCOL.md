# SkyForge Authority-to-Mesh Experiment Protocol v0.3.1

## Objective

Verify that the approved top-down gunship authority produces a correctly oriented, identity-preserving, static 2.5D mesh through the complete glTF → Blender 5.x path.

## Gate sequence

1. Read and hash the authority pixels.
2. Generate a watertight target-coordinate mesh (+X right, +Y forward, +Z up).
3. Encode glTF coordinates as `(x, z, -y)`.
4. Reload the GLB independently.
5. Emulate Blender's glTF import conversion `(x, y, z) → (x, -z, y)`.
6. Require reconstructed bounds delta ≤ `1e-5`.
7. Require reconstructed height-to-planform ratio ≤ `0.45`.
8. Require target and emulated-Blender silhouette IoU ≥ `0.94`.
9. Import in live Blender and repeat the height/orientation guard.
10. Render neutral and ±18° bank frames without effects.
11. Require live Blender top-render silhouette IoU ≥ `0.90`.
12. Export only the neutral craft hierarchy.

## Effects policy

Thrusters, exhaust cones, destruction effects and anchors are disabled. They must not be reintroduced until the generated craft passes visual identity, orientation and banking review.

## Acceptance

A run is not accepted merely because files were produced. The authority, generated top view and live Blender neutral/banked views must visibly represent the same craft. Numeric gates support that judgement; they do not replace it.
