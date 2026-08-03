# WP1 — Frozen VMP v1 Contracts

## Scope

This work package encodes the structurally frozen VMP v1 boundary before emitter or provider-dispatch code exists. It adds no geometry generation, provider transport, paid operation, texturing, remeshing, multi-image processing, or ground-role behavior.

## Binding decisions

- **MBS-134:** `frame_contract.schema.json` requires a calibration envelope and `known_limitations.schema.json` requires the explicit exclusion of thrusters, muzzle flashes, shadows, debris, and other Sprite Foundry effects from calibrated hull headroom.
- **MBS-135:** `skyforge.vmp-content-digest.v1` freezes RFC 8785 JCS, SHA-256, the exhaustive participating manifest-field list, and `unknownFieldPolicy: excluded`.
- **MBS-137:** authority embedding is fail closed. Embedded authority requires affirmative `permitted`; `unknown` and `prohibited` require hash-only packaging and reduced independent re-verification.
- **MBS-141:** optional digest fields are omitted when absent; explicit null is prohibited. Positive absent/present and negative-null vectors are included.
- **MBS-142:** the v0.6.0 governance file hashes are recorded for byte-identity comparison. Manufacturing-axis ownership is a versioned exact enumeration suitable for independent probe comparison.
- **MBS-143:** `producer.sidecarVersion` participates in semantic identity. A no-op producer-version rebuild must supersede the prior digest with `reasonCode: producer_version_rebuild`.
- **MBS-136:** request-correspondence fields are frozen in `provider_task_record.schema.json`; this does not close the finding against a real provider and does not authorize paid dispatch.

## Dependency posture

The producer declares exact pins for `jsonschema==4.26.0` and `rfc8785==0.1.4`. Canonicalization fails closed when the exact JCS implementation is unavailable. Official JCS vector execution remains a clean-environment gate; it is not waived by schema-only tests in the current sandbox.

## Frozen structure

The schema index is `contracts/vmp/v1/SCHEMA_INDEX.json`. Every schema uses JSON Schema draft 2020-12 and rejects undeclared root fields. Optional files remain optional; the required VMP directory structure is unchanged.
