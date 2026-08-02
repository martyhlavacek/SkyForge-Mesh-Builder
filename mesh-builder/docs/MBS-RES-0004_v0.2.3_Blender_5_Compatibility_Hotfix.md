# MBS-RES-0004 — v0.2.3 Blender 5 compatibility hotfix

**Trigger:** Marty's first Experiment 00 job on Blender 5.2.0 LTS.

## Observed failure

Blender launched successfully but stopped before scene setup because v0.2.2
assigned `BLENDER_EEVEE_NEXT`. Blender 5.2 reported the available identifiers as
`BLENDER_EEVEE`, `BLENDER_WORKBENCH`, and `CYCLES`. Consequently no render or
export outputs were created, and the server correctly failed the output contract.

## Correction

`select_eevee_engine()` now probes the live Blender API in this order:

1. `BLENDER_EEVEE` — Blender 5.0+;
2. `BLENDER_EEVEE_NEXT` — Blender 4.2-4.x.

The selected engine is captured in `run_report.json`. The manifest, output
contract, canonical frame, experiment protocol, and schema versions remain
unchanged from reviewed v0.2.2.

## Scope

This is a narrow runtime-compatibility hotfix. It does not incorporate the
non-blocking CR-0004 changes reserved for the pre-Experiment-01 revision.
