# MBS-CR-0027 Focused Pre-Smoke Security Review Request

Review the exact candidate commit and the checksum-bound `SkyForge_v0.8.1_PRE_SMOKE_PREAUTH_EVIDENCE.zip`. This is a no-spend preauthorization review, not authorization for a live Meshy operation.

## Required review focus

1. Confirm the committed official-contract snapshot supports the endpoint, retrieval route, image types/count, Data URI/public URL input, `meshy-6`, all five geometry-only request options, GLB target, Bearer authentication, 20-credit estimate/cap, three-day non-Enterprise retention, and initial `assets.meshy.ai` artifact hostname.
2. Confirm production approves exactly `assets.meshy.ai`, uses a real operating-system resolver, and rejects every other host, deceptive variant, unsafe port, credentialed URL, IP literal, localhost, empty/malformed/mixed/non-global DNS result, unknown redirect, and unsafe final response URL.
3. Confirm the URL preflight uses only policy validation and optional bounded HEAD requests, never downloads bytes, never reads a Meshy key, and redacts signed queries and fragments.
4. Confirm provider POST authorization, duplicate-spend prevention, polling and network kill switches remain intact.
5. Confirm no human-approved same-craft top/front/right bundle exists and that fixtures and single-view evidence are not misrepresented as live authority or Meshy output.
6. Confirm the dry-run projection is explicitly unsendable, missing its bundle/profile, capped at 20 credits, and records `paidOperationPerformed: false` and `providerTaskId: null`.
7. Reproduce Producer Ruff/tests, focused reconstruction tests, both bindings, Import Probe isolation/historical comparison, policy matrices, secret scan, deterministic evidence rerun, and evidence-manifest verification.
8. Confirm v0.7.1, geometry_v2, UI, VMP, server, pipeline, and Import Probe are unchanged.

Return a checksum-bound verdict against the exact commit. Do not execute a provider task, request an API key, download an artifact, consume credits, or begin visual testing. If accepted, state only that the candidate is ready for the separate authority-bundle and explicit-authorization gates; do not characterize a live smoke task as authorized.
