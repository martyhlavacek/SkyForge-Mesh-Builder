# MBS-RES-0007 — v0.4.0 OpenAI Concept Workflow Reinstatement

## Objective

Restore the earlier OpenAI image-generation entry point so that SkyForge can once again:

1. generate one or more 3/4 beauty concepts;
2. allow a human to approve one concept aesthetically;
3. generate one or more top-down authority candidates from that exact approved beauty concept;
4. select an approved top-down authority;
5. run the accepted authority-to-mesh generator.

## Changes implemented

- Added `app/openai_client.py` for OpenAI Images API request construction.
- Added `app/concept_workflow.py` for concept-run storage and file serving.
- Added Concept Lab UI and client-side selection flow to `app/templates/index.html`.
- Added server routes:
  - `GET /api/openai/health`
  - `POST /api/concepts/beauty`
  - `POST /api/concepts/authority`
  - `GET /api/concepts/files/<run_id>/<filename>`
- Updated `/api/jobs` so a selected generated authority can be consumed directly by the authority-mesh generator.
- Preserved the fail-closed authority-mesh gates from v0.3.1.
- Kept thrusters disabled.

## Known limitations

- Live OpenAI concept generation was not executed in the sandbox build environment.
- The geometry path remains deterministic 2.5D extrusion, so delicate winged craft are not yet materially improved in side-angle depth.
- The sidecar does not yet auto-score beauty-to-authority style continuity; selection is still human-governed.

## Recommended next live test

Run a full beauty-to-authority-to-mesh loop on at least:

- a military gunship;
- a fighter;
- an interceptor; and later
- a more delicate winged craft to identify the 2.5D geometry limitations for the next refactor.
