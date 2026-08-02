# v0.7.0 Source Diff Register

Baseline: exact v0.6.0 archive SHA-256 `68516def22275b0cb6d1fa0513097adfa717b9df584f81915922f6e62e64d106`.

| Work package | Change class | Authorized purpose | Geometry/governance effect |
|---|---|---|---|
| WP0 | Binding infrastructure and evidence | MBS-138 source/dependency continuity and tamper tests | No geometry algorithm change; governance files remain byte-identical |
| WP1 | Frozen contracts and schemas | MBS-134/135/137/141/142/143 and SF-AM-0001 amendment | Contract-only; no provider dispatch or geometry execution |

Every later work package must append its exact changed-file list and explain whether the executed Blender path is touched. Live Blender remains mandatory for all three fixtures before candidate review because the authorized plan will touch `app/pipeline.py` in WP2.

## WP1 exact change classes

- `contracts/vmp/v1/**`: frozen VMP, asset, provider, PEP, validation, authority, role, material, provenance, receipt, digest-profile schemas and positive/negative examples.
- `common/schema_validation.py`: schema-only validation utility.
- `common/canonical_json.py`: fail-closed RFC 8785 wrapper; no fallback canonicalizer.
- `scripts/generate_contract_schemas.py`: deterministic schema/example generator.
- `scripts/seal_release.py`, `requirements.txt`, `BUILD_INFO.json`: exact dependency and v0.7.0 release-contract declarations.
- `docs/v0.7.0/governance/SF-AM-0001_Rule_5_Socket_Ownership_Amendment.md`: required ownership amendment.
- `tests/test_frozen_contracts_v1.py`, `tests/test_canonical_json_contract.py`: schema, mutation, governance, ownership, dependency, determinism, and canonicalization gates.

No WP1 file changes the geometry algorithm, accepted fixture assets, OpenAI governance files, Keychain implementation, or Blender pipeline execution. The mandatory three-fixture live Blender run remains required because WP2 will touch `app/pipeline.py`.

## WP2-WP8 authorized change classes

### WP2 — provider-neutral local boundary

- `app/providers/base.py`, `models.py`, `registry.py`, `local_deterministic.py`: provider contract and behaviorally invisible adapter around the accepted deterministic generator.
- `app/server.py`: routes authority-mesh generation through the registered local provider.
- `tests/test_provider_boundary.py`: capability, role, zero-cost event, and exact fixture identity checks.

The geometry algorithm in `app/authority_mesh.py` is unchanged. Adapter invisibility is proven by same-environment legacy-direct comparison under the frozen WP2 semantic criteria; whole-file GLB hashes remain diagnostic because archive bytes can vary across operating systems without changing accepted mesh semantics.

### WP3 — explicit asset-v3 migration

- `app/asset_migration.py`: explicit, idempotent migration with no inferred provider or role semantics and byte-identical read-only legacy evidence.
- `tests/test_asset_migration.py`: unsupported-role, contradictory-semantic, approval, lineage, round-trip, idempotence, and read-only evidence gates.

Only `air_moving` is accepted. Legacy collision ellipses become non-authoritative hints that consumers must ignore for runtime collision.

### WP4 — deterministic VMP v1 producer

- `app/vmp_builder.py`: frozen VMP v1 required-file enforcement, canonical identity, normalized ZIP metadata, content index, checksums, authority licensing gate, and prohibited-content rejection.
- `tests/test_vmp_builder.py`: deterministic builds, semantic/transport identity, optional digest fields, sidecar-version supersession, and packaging attacks.

VMP v1 file structure is unchanged from the architecture freeze.

### WP5 — independent consumer probe

The Sprite Foundry Import Probe is deliberately outside the producer source tree. It has its own source binding, dependency contract, copied frozen schemas, archive/GLB/texture validators, Import Receipt emitter, valid vectors, and 18-mutation battery. The producer invokes it only as a separately configured subprocess.

### WP6 — mock provider and authoritative reservation ledger

- `common/provider_credit_ledger.py`, `app/providers/mock_provider.py`, `mock_operation.py`: reserve-before-dispatch, single-writer locking, stale-lock recovery, unique orphan adoption, ambiguous orphan blocking, immutable adjudication, capture-failure handling, and hard credit caps.
- `scripts/run_mock_provider_fault_matrix.py`, `tests/test_provider_credit_ledger.py`: primary fault and concurrency evidence.

MBS-136 remains explicitly open against a real paid provider; paid dispatch is not enabled.

### WP7 — isolated Meshy public test mode

- `app/providers/meshy_test_mode.py`, `scripts/run_meshy_test_mode_diagnostic.py`: zero-credit transport/lifecycle diagnostic using only the public test key and strict API/asset allowlists.
- `tests/test_meshy_test_mode.py`: submit-once, SSE/poll fallback, timeout, sanitization, no-Keychain, zero-paid-ledger, and no-promotion checks.

The diagnostic does not implement `MeshProvider`, is not registered in the normal workflow, and cannot emit an approved asset or VMP.

### WP8 — integrated VMP export, independent receipt, release and review gates

- `common/glb_facts.py`: producer-side GLB 2 facts and external-reference rejection.
- `app/vmp_job_export.py`: rendered local-job assembly, frozen 0.94 Blender floor, permission-conditional authority handling, deterministic VMP build, separate Import Probe invocation, and exact receipt binding.
- `app/pipeline.py`: preserves a stable rendered timestamp and the 0.94 floor; runtime pruning recognizes the separate VMP area.
- `app/server.py`, `app/templates/index.html`, `app/static/style.css`: visible provider/role/collision status and a second exact-artifact VMP approval action. No paid provider control appears.
- `scripts/run_live_blender_preflight.py`: mandatory all-three-fixture local adapter → Blender → deterministic VMP → independent probe path plus hash-only vector.
- `scripts/seal_release.py`: separately deterministic producer source/release seal with exact dependency, Ruff, zero-skip, binding, hygiene, and mode/timestamp perturbation gates.
- `scripts/assemble_claude_candidate.py`: fail-closed outer review-package assembly requiring all primary evidence and preserving `userTestingCleared: false`.
- `scripts/run_local_adapter_evidence.py`, `run_migration_evidence.py`, `run_governance_identity.py`: primary fixture, migration, and governance evidence collectors.
- `Run v0.7.0 Live Blender Preflight.command`, `Seal v0.7.0 for Claude.command`: versioned release entrypoints using separate producer/probe environments.
- `tests/test_vmp_job_export.py`, `test_candidate_assembler.py`, updated release/server/runtime tests: exact exporter and review-package rejection gates.

`app/pipeline.py` and the executed VMP/Blender orchestration are touched, so MBS-139 requires live Blender reports for all three fixtures before the exact candidate may be assembled. The candidate assembler refuses to create an outer review ZIP without those reports.


### WP8 qualification remediation — cross-platform equivalence evidence

- `common/mesh_equivalence.py`: implements the frozen WP2 comparison contract: exact indices, X/Z float32 values, UV float32 values, decoded texture pixels, topology, counts, bounds, frame evidence and gate results; Y deltas are bounded at max `1e-5` and RMS `1e-6`.
- `scripts/run_local_adapter_evidence.py`: generates both the unwrapped legacy-direct output and the `LocalDeterministicProvider` output in the same clean environment, then records transport hashes diagnostically and gates on semantic equivalence, authority identity, zero cost and accepted generation gates.
- `scripts/run_live_blender_preflight.py`: repeats the same legacy-direct-versus-adapter comparison before the mandatory Blender/VMP/Import Probe path.
- `scripts/assemble_claude_candidate.py`: requires the semantic-equivalence v2 evidence and exact cleared authority hashes; it no longer treats a Linux-produced whole-file GLB SHA as a portable macOS acceptance criterion.
- `tests/test_mesh_equivalence.py`, `tests/test_candidate_assembler.py`: positive and negative semantic-evidence gates.

No geometry algorithm, Blender threshold, authority image, VMP structure, provider capability, cost control or governance rule changed.
