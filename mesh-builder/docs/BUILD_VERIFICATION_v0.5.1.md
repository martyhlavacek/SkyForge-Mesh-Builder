# BUILD VERIFICATION — SkyForge Mesh Builder Sidecar v0.5.1

## Scope

This hotfix addresses the first live OpenAI-generated interceptor authority failure in v0.5.0.

The returned job failed during preparation, before Blender, because the opaque light-background mask path squared signed 16-bit colour differences. Dark craft pixels could overflow before the square root, yielding NaNs and a malformed mask. The generated OBJ then contained 16 non-manifold edges and was correctly rejected by the independent topology gate.

## Corrections

- Foreground colour-distance arithmetic moved from signed `int16` to `float32` before subtraction and squaring.
- Exact returned OpenAI interceptor authority added as `samples/interceptor_openai_authority_regression.png`.
- Regression test verifies:
  - no invalid-value runtime warning;
  - opaque-background mask path is exercised;
  - silhouette IoU clears 0.94;
  - Blender-import emulation IoU clears 0.94;
  - zero boundary edges;
  - zero non-manifold edges;
  - independently reloaded GLB is watertight.
- Job-preparation exceptions now write:
  - the exact exception type and message to `job.json`;
  - a full traceback to `logs/preparation_error.log`;
  - actionable job and log paths in the HTTP error response.

## Verification performed

- Python compilation: **PASS**
- Regression suite: **43 passed, 2 skipped**
- Exact interceptor authority regeneration: **PASS**
- Generated target-coordinate silhouette IoU: **0.948011**
- Emulated Blender-import silhouette IoU: **0.953241**
- Boundary edges: **0**
- Non-manifold edges: **0**
- GLB reload watertight: **PASS**
- GLB reload winding consistency: **PASS**
- Blender-import bounds delta: **0.000000048**
- Shell syntax for all `.command` files: **PASS**

## Environment limits

Two Flask-dependent modules remain skipped in this sandbox because Flask/Werkzeug are not available from the sandbox package index. They are expected to run after the target Mac launcher installs the pinned requirements.

Live Blender execution of this exact interceptor mesh was not available in the build environment. The pre-Blender geometry and emulated glTF-to-Blender coordinate gates pass.
