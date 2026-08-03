# MBS-RES-0006 — v0.3.1 Coordinate Contract and Thruster Removal

## Trigger

The first v0.3.0 live Blender run failed with silhouette IoU `0.266629`. The local authority-generation contact sheet was correct, while the live Blender render showed an edge-on, vertically oriented craft.

## Root cause

The internal mesh used target coordinates (+X right, +Y forward, +Z up), but those coordinates were written directly into a glTF file. glTF is Y-up. Blender's importer converted the coordinates as:

```text
glTF (x, y, z) → Blender (x, -z, y)
```

That conversion moved the craft's long forward Y dimension into Blender Z. The failed job's live measurement was `heightToPlanformRatio=1.254237`, compared with the intended generated ratio of approximately `0.168`.

The v0.3.0 self-test was inadequate because it reloaded the GLB with trimesh and projected raw X/Y coordinates. It did not model glTF semantics or Blender's import conversion.

## Corrective implementation

v0.3.1:

- encodes target coordinates into glTF as `(x, z, -y)`;
- independently reloads the generated GLB;
- applies the exact Blender-import conversion to the reloaded mesh;
- compares reconstructed bounds with the original target mesh;
- measures silhouette identity after that conversion;
- refuses to start Blender when the reconstructed craft is vertically oriented;
- repeats the height-to-planform guard inside the live Blender script;
- forces +Y forward/+Z up for Authority Mesh jobs;
- removes user-selectable authority-mesh axes;
- removes thruster generation, UI, settings and anchors.

## Exact failed-run authority result after correction

- target silhouette IoU: `0.959283`;
- emulated Blender-import silhouette IoU: `0.955508`;
- reconstructed bounds delta: `0.000000048`;
- reconstructed height-to-planform ratio: `0.167919993`;
- boundary edges: `0`;
- non-manifold edges: `0`;
- watertight and winding-consistent: `true`.

## Thruster disposition

The cones were review-only Blender primitives placed from bounding-box heuristics, not detected engine sockets. They were premature and visually misleading. v0.3.1 contains no cone creation and exposes no thruster control. The asset record explicitly marks thrusters disabled.
