# Manual Textured GLB Import decision

The paid Meshy API / Track S pilot is paused, not removed. Its provider, preauthorization, cost-governance,
review, evidence, and baseline code remains unchanged. Manual Meshy web generation is a separate external
authoring path. It never calls Meshy, reads a Meshy credential, or claims that SkyForge generated the source
geometry.

Mesh Builder owns ingestion, byte-for-byte quarantine of the original GLB, SHA-256 identity, fail-closed GLB
inspection, Blender normalization to +Y forward / +Z up / +X right, deterministic canonical scale, QA renders,
explicit approval, and VMP packaging. The original web generation is not deterministically reproducible. Its VMP
uses `approved_artifact_immutability`, provider `meshy_web`, external-source provenance, and material contract v2;
the local authority path retains its stricter deterministic v1 contracts.

The model leaves attachment points empty and unapproved for future Animation Studio work. It does not infer
cockpit, thruster, weapon, or effect sockets, and does not implement rigging, animation, effects, sprites, or game
integration.

## User procedure

1. Create or choose approved reference artwork.
2. Use the Meshy.ai web app manually.
3. Generate the model.
4. Apply the desired web-app texturing/PBR.
5. Export a self-contained GLB.
6. Import it through **Manual Textured GLB Import** and explicitly select its source orientation.
7. Normalize and review all QA views.
8. Approve the exact original and normalized SHA-256 pair, or reject it.
9. Export the validated package; export succeeds only after the independent Sprite Foundry Import Probe accepts it.
10. Preserve existing baselines and historical evidence.

The quarantine copy is read-only and is never packaged or overwritten. A changed normalized GLB invalidates its
approval. Authority silhouette IoU is recorded as not applicable when no semantically valid authority is supplied.

Import and inspection do not require Blender or an orientation declaration. Every successful inspection writes
`inspection/glb_inspection.json`, bound to the quarantined source SHA-256 and byte size. Reinspection, normalization,
approval, and export all reverify that source binding. Normalization separately requires an explicit source
forward/up mapping.

The manual UI binds to `127.0.0.1:8043` only. VMP v2 acceptance uses the independent sibling
`import-probe-v2/` implementation and its independently hashed schema copies; the historical bound v1 probe remains
unchanged. On the current test machine Blender 5.2.0 exits with signal 139 before the normalization script executes,
so Import → Inspect is usable but normalization must continue to be reported as unavailable/failed there.
