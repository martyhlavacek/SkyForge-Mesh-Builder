# SkyForge Sprite Foundry Import Probe v0.1.1

This is the independently packaged consumer-side validator for Project SkyForge Validated Mesh Package v1 (`.sfmeshpack`). It is not a producer library and must run from its own exact dependency environment with the Mesh Builder source absent from `PYTHONPATH`.

v0.1.1 is the MBS-147 diagnostic and release-evidence hotfix. It rejects ZIP file/parent path collisions before decoding, reports unlisted members relative to the package root, and emits primary source/release double-build evidence during sealing. No VMP v1 acceptance rule is relaxed.

## Implemented scope

- independent exact source/dependency binding, verified by the command-line entrypoint before any package is read;
- copied and hash-bound frozen VMP v1 schemas and contract documents;
- quarantine extraction with path, count, size, ratio, duplicate, symlink and prohibited-content limits before decoding;
- RFC 8785 JCS semantic package digest validation;
- strict schema and frozen required-file validation;
- GLB 2 structural, coordinate, topology, texture and external-reference checks;
- authority embedding and hash-only reverification rules;
- MBS-134 calibration-envelope checks;
- MBS-141 absent/present/null digest-field behavior;
- MBS-142 exact manufacturing-axis ownership checks;
- MBS-143 producer-version semantic identity handling;
- consumer-issued Import Receipt generation;
- valid embedded-authority and hash-only package vectors;
- full mutation battery with intended rejection codes.

## Independence and safety

The probe imports no Mesh Builder producer module, performs no network request, reads no provider credential, and does not trust a producer readiness boolean. Its Import Receipt is the authoritative boundary decision. Collision hints remain non-authoritative.

Run:

```text
python scripts/run_import_probe.py package.sfmeshpack --receipt IMPORT_RECEIPT.json
```

The exact probe binding must verify before the command accepts any package. User testing is not authorized by this package.
