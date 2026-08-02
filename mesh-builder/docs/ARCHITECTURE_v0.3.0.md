# Authority Mesh Architecture v0.3.0

## Generator

`app/authority_mesh.py` performs deterministic local generation:

1. Decode the uploaded image.
2. Prefer alpha; otherwise derive foreground from corner-colour distance.
3. Close one-pixel gaps and retain the largest connected silhouette.
4. Fit the silhouette to a governed 160×160 generation grid.
5. Derive a symmetric height field from interior distance, luminance and cockpit-colour cues.
6. Emit shared-vertex top, bottom and boundary surfaces.
7. Project the authority as the albedo texture.
8. Audit edge incidence.
9. Export OBJ/MTL and textured GLB.
10. Reload the GLB independently through Trimesh.
11. Emit software previews and the generation report.

## Transaction boundary

Blender cannot start until `verify_generation_contract()` reconciles authority and mesh hashes and confirms every local gate. Blender output cannot be packaged until `verify_required_outputs()` confirms the second identity gate and clean export evidence.

## Mesh semantics

The local generator produces one static craft body. Thruster effects are review-only and excluded from the silhouette and normalized GLB. Semantic parts and destruction eligibility remain unavailable unless a later mesh arrives with meaningful object boundaries.
