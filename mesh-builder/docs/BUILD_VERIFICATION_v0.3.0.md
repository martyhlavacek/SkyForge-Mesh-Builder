# SkyForge Mesh Builder Sidecar v0.3.0 — Build Verification

## Verification environment

The build environment provides Python, Pillow, NumPy and Trimesh but does not provide Blender, Flask/Werkzeug or Ruff from its offline package index.

## Executed checks

| Check | Result |
|---|---|
| Python compilation for app/common/blender/tests/scripts | PASS |
| Pytest executable suite available in sandbox | **32 passed** |
| Flask endpoint module | **1 module skipped** because Flask/Werkzeug are unavailable in this sandbox |
| Expected complete installed result | **37 passed, zero skipped** |
| Real approved-gunship authority-to-mesh self-test | PASS |
| Independent OBJ edge-incidence parser | PASS |
| Independent Trimesh GLB reload | PASS |
| GLB watertight | true |
| GLB winding consistent | true |
| GLB textured visual | true |
| Deterministic repeat-generation test | PASS |
| Tampered generated-mesh checksum rejection | PASS |
| Blank authority rejection | PASS |
| Disconnected-noise cleanup | PASS |
| Production fallback-source prohibition | PASS |
| Blender execution | unavailable in this build environment |
| Ruff execution | unavailable in this build environment; configured and mandatory in `run_tests.command` |

## Real generated artifact

The included approved gunship authority generated:

```text
GLB SHA-256: 8f50f79048db931893985cb7cbfba5460959af544a9d15c5441c90ce99ad615e
OBJ SHA-256: 6f422cad17652ba64d38ed2dddb1e779b784cd514e80e22127632767a69a900c
Vertices: 15,052
Triangles: 30,100
Bodies: 1
Boundary edges: 0
Non-manifold edges: 0
Independent reloaded-GLB silhouette IoU: 0.952621
```

Evidence is retained under `docs/SELF_TEST_EVIDENCE_v0.3.0/`.

## Interpretation

Successful mesh generation is verified independently of Blender: the authority creates a real textured GLB that reloads as a single watertight, winding-consistent mesh and visibly preserves the gunship under software-rendered banking.

The remaining unexecuted step in this sandbox is Blender 5.2 import/render/export. The sidecar will not mark that step successful unless the Blender top-render IoU reaches 0.90 and all clean-export contracts pass.
