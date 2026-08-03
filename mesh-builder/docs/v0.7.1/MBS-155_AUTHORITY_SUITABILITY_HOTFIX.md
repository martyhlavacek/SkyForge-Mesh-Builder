# MBS-155 — Manual authority suitability fail-closed hotfix

## Field defect

A three-quarter beauty image was uploaded through the manual authority field in the exact reviewed
v0.7.0 build. It passed downstream silhouette and topology gates and generated a mesh. Those gates
proved only that the mesh matched the uploaded silhouette; they did not prove that the source image
was a valid orthographic top-down authority.

## v0.7.1 correction

Before job allocation, provider execution, Blender launch, or API spend, every manual authority is
validated for:

- minimum image size and bounded foreground coverage;
- safe edge margins and a dominant connected foreground component;
- bilateral planform silhouette agreement;
- stable row-weighted centreline;
- nose-up vertical major-axis alignment;
- bounded bilateral colour/lighting difference;
- explicit user certification that the upload is a strict top-down authority.

Governed Concept Lab authorities are revalidated and their complete lineage is checked against the
beauty run metadata, profile, asset ID, filenames, image records, and SHA-256 bytes.

Every accepted job stores `source/authority_suitability_report.json`, binds its SHA-256 into the job
manifest, and exposes no exceptional bypass. The exact user-reported beauty image is shipped only as
a rejecting regression fixture.


## Field-evidence identity

The v0.7.0 review package contains the same decoded 1024 x 1024 RGBA pixels as the user-supplied
three-quarter beauty fixture, but the server re-encoded the PNG when copying it into the job source
folder. The two PNG byte streams therefore have different SHA-256 values even though their decoded
pixels are identical.

v0.7.1 evidence binds both identities:

- the exact original fixture byte SHA-256;
- the exact re-encoded authority byte SHA-256 stored in the v0.7.0 package;
- a width-, height-, and decoded-RGBA-pixel SHA-256 shared by both images.

This prevents PNG compression metadata from being mistaken for an image-content change while still
binding every shipped byte stream independently.

## Scope boundary

The deterministic gate is intentionally conservative and supports the current bilateral, nose-up,
`air_moving` craft profiles only. It is not a general computer-vision classifier and does not authorize
asymmetric craft, arbitrary rotations, ground assets, or perspective references.
