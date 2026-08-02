# MBS-RES-0014 — v0.6.0 CR-0011 Remediation

**Reviewed candidate:** `c6dd2d463e5f5ab39573877a89aa1325d46e7daec7b416afbe896f5eba1ffe61`  
**Reviewer:** Claude, MBS-CR-0011  
**Scope:** deterministic geometry and release verification only

| Finding | Disposition in this candidate | Evidence |
|---|---|---|
| MBS-85 Ruff import order | **Fixed; independently re-run required** | Function-local NumPy import moved into the sorted third-party import block. Ruff 0.15.22 remains unavailable in the authoring sandbox; Claude must execute it. |
| MBS-86 scaled-mirror underside | **Closed in candidate** | Lower field now has its own distance exponent, narrow keel, mid-aft belly bulge and chine basis. Image-centre `fliplr` stabilization was removed. Measured lower-vs-upper relative residual is 0.230694–0.247570, above the new 0.10 gate, versus approximately 0.01 in the reviewed candidate. |
| MBS-87 speckle genus | **Closed in candidate** | Small enclosed holes at the 384 grid are measured and filled up to 12 pixels; larger holes are retained and fail `genusMax = 0`. Field fixture: 16 holes / 38 pixels filled, Euler 2, genus 0. |
| MBS-88 negative controls | **Closed in candidate** | New tests prove source/reload disagreement fails and prove component count is read from the reloaded GLB by injecting a two-component reload proxy. |
| MBS-89 path-dependent albedo report | **Closed in candidate** | Alpha path reports `none`; opaque colour-distance path reports `foreground_mask_derivation_only`. Both source and geometry records carry the scope. |
| MBS-90 no adaptive grid | **Closed in candidate** | Export grid selects the largest of 256/224/192/160 that remains at or below 180,000 projected triangles; selected size and projected count are recorded. |
| MBS-91 uncalibrated gates | **Recalibrated** | Tightened to height 0.28, flat belly 0.06, vertical wall 0.045, combined artifact 0.10 and tip/root 0.40. Candidate maxima are 0.1688, 0.0298, 0.0082, 0.0380 and 0.2074 respectively. |
| MBS-92 split topology provenance | **Closed in candidate** | Geometry metrics are computed from the independently reloaded GLB reconstructed into the target frame; provenance is explicit. |
| MBS-93 image-centre mirroring | **Closed in candidate** | `np.fliplr` stabilization is removed entirely. Geometry follows the governed mask and row-relative coordinates without forced image-centre reflection. |
| MBS-94 non-reproducible seals | **Closed in candidate** | Source and Claude-package ZIP entries use a fixed timestamp, sorted order, fixed compression and preserved mode bits. A test proves two source seals are byte-identical. |
| MBS-95 live Blender unavailable | **Open / blocking until executed** | `Run v0.6.0 Live Blender Preflight.command` performs three fixture runs, live neutral/banked renders, silhouette/export gates and produces one checksummed evidence ZIP. It has not been executed in this environment because Blender is unavailable. |

## Scope protection

No OpenAI pricing, budgets, ledger, cache, Keychain, provider, multiview, thruster, fallback, animation or gameplay code was changed. MBS-78, MBS-79 and MBS-80 remain open and non-blocking.
