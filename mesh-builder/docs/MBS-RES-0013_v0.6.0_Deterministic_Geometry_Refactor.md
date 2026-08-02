# Superseded candidate resolution

This document describes the first v0.6.0 candidate reviewed in MBS-CR-0011. Its dispositions are superseded by `MBS-RES-0014_v0.6.0_CR0011_Remediation.md`.

# MBS-RES-0013 — v0.6.0 Deterministic Geometry Refactor

**Baseline:** sealed v0.5.3, SHA-256 `db7d55a4495bac3f338ddac5de4bca7624997be126c110384f58fc199f4586d3`  
**Scope:** deterministic geometry only; no provider integration

| Finding / requirement | Disposition | v0.6.0 evidence |
|---|---|---|
| MBS-70 asserted component count | **Closed in candidate** | `componentCount` is measured with `len(reloaded_glb.split(...))`; source is recorded as `independent_reloaded_glb_split`. |
| MBS-71 quantified 2.5D ceiling | **Addressed** | Constant underside removed; independent top/bottom fields and tapered seam added. Field gunship combined flat-belly/wall fraction falls from 0.636282 to 0.017681 in no-charge evidence. |
| MBS-72 albedo-derived geometry | **Closed in candidate** | Geometry consumes only mask, distance and planform axis. A regression test proves identical alpha planforms with orange vs blue albedo produce byte-identical OBJ geometry. |
| MBS-73 height gate not binding | **Accepted** | Existing ratio gate is preserved unchanged; representation changed first. |
| MBS-74 low work grid / Python scan | **Closed in candidate** | 384 work grid with exact separable EDT; 256 bounded export grid. |
| MBS-75 image-centre mirroring | **Partially addressed** | Geometry uses row-relative occupied-span centre before final bilateral stabilization. Full principal-axis estimation is deferred because the authority governance already requires strict top-down alignment. |
| Two-sided underside | **Implemented** | Independent upper/lower fields; lower surface is not constant or mirrored. |
| Edge convergence | **Implemented** | 0.006-world-unit manifold seam replaces tall vertical extrusion walls. |
| Measured edge audit | **Implemented** | Source and independently reloaded GLB audits are recorded and must agree. |
| New metrics | **Implemented** | Flat belly, vertical wall, combined artifact, section thickness, Euler number and genus. |
| Meshy/Hunyuan/multiview | **Deferred by scope** | No provider code included. |
| MBS-78/79/80 | **Open, non-blocking** | Pricing/authority-model findings unchanged; no cost code modified. |
