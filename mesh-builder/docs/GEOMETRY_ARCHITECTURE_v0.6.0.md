# Geometry Architecture — Mesh Builder Sidecar v0.6.0

## Representation

v0.5.3 used one top height field, a constant bottom plane and vertical perimeter walls. The remediated v0.6.0 candidate generates three planform-only fields:

- `centre(x,y)`: a small camber field;
- `top(x,y)`: an upper field using a broad distance hull, centreline crown and forward spine;
- `bottom(x,y)`: a genuinely distinct lower field using a steeper distance exponent, narrow keel, mid-aft belly bulge and chine term.

The lower field is not an offset or scalar copy of the upper field. The generator records a best-fit lower-to-upper scale, Pearson correlation and relative residual. Acceptance requires the residual to be at least 0.10; the three retained fixtures measure 0.230694–0.247570.

No image-centre mirroring is applied. Row-relative lateral position and a longitudinal coordinate are measured from the occupied planform.

## Mask and topology governance

Alpha-carrying authorities use `alpha_threshold_16` and are geometrically independent of RGB albedo. Opaque authorities use `corner_colour_distance_28`; RGB influences only foreground-mask derivation and this is reported explicitly.

After largest-component selection, enclosed background islands at the 384 work grid are measured. Holes up to 12 pixels are filled as threshold speckle. Larger holes remain visible to validation. The default `genusMax` is zero, so an intentional or accidental through-hole fails rather than silently shipping.

## Thickness and edge convergence

Exact Euclidean distance to the silhouette drives section thickness. Top and lower surfaces converge to a 0.006-world-unit manifold seam. The seam closes the mesh without recreating the tall vertical walls of v0.5.3.

## Resolution contract

- Work field: 384×384.
- Export grid: adaptively selected from 256, 224, 192 or 160.
- Preview grid: 128×128.

The largest export grid whose projected triangle count is at most 180,000 is selected and recorded. The exact separable Euclidean-distance transform remains dependency-free.

## Measurement provenance

Connected components, edge audit, Euler number, genus and area-weighted surface metrics are measured from the independently reloaded GLB after reconstruction into the target frame. Source and reload edge audits must agree.

## Preserved contracts

- +X right, +Y forward, +Z up internally.
- glTF encoding `(x,y,z) -> (x,z,-y)`.
- Independent OBJ and GLB reload validation.
- Blender-import coordinate and silhouette gates.
- Approved top-down authority remains the identity anchor.

## Representation limit

The model remains a deterministic two-surface planform representation. It can produce a sculpted underside and tapered sections, but cannot represent arbitrary overhangs, deep undercuts, detached nacelles or overlapping volumes at one planform coordinate. Those remain outside v0.6.0 and define the later provider-comparison boundary.
