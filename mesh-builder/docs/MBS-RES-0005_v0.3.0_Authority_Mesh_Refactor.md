# MBS-RES-0005 — v0.3.0 Authority Mesh Refactor

**Trigger:** User rejection of the v0.2.3 fallback result because the approved authority image had not generated the rendered mesh.

**Disposition:** Correct. The former run was only a renderer/export smoke test and was incorrectly described as a gunship pass.

## Architectural correction

The production fallback mesh has been removed. The default workflow is now:

```text
approved authority pixels
→ foreground mask and content hash
→ deterministic spacecraft height field
→ watertight textured OBJ
→ independent GLB export and reload
→ strict local identity/topology gates
→ Blender render and clean export
→ strict Blender silhouette gate
```

Authority Mesh mode rejects an uploaded mesh, so an external object cannot silently substitute for local generation.

## Fail-closed evidence

The manifest records `mesh.origin = generated_from_authority`, the authority hash, the generated GLB hash and the generation report path. Before Blender starts, the pipeline verifies:

- the authority pixels were consumed;
- report and manifest authority hashes match;
- report and manifest mesh hashes match;
- topology and identity gates passed;
- the generated GLB is present and unchanged;
- no fallback is permitted.

After Blender, a second identity gate requires top-render silhouette IoU ≥ 0.90.

## Real control result

Input: `samples/approved_gunship_authority.png`

Output:

- `authority_generated_mesh.glb`;
- 15,052 vertices;
- 30,100 triangles;
- one body;
- zero boundary edges;
- zero non-manifold edges;
- watertight and winding-consistent after independent Trimesh reload;
- deterministic generator-stage independent reloaded-GLB silhouette IoU 0.952621;
- visible top, bank-left and bank-right previews preserving the approved gunship.

## Deferred scope

This is a SkyForge-specific textured 2.5D mesh generator. It does not claim general unseen-view reconstruction or semantic moving-part inference. Those remain separate provider and research tracks.
