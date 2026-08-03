# Mac Sealing Instructions — Mesh Builder Sidecar v0.5.2

This is a release-build step, not user testing. It makes no OpenAI image or edit request and spends no API credits.

## One-click path

1. Extract the Mac sealing kit.
2. Open the extracted `SkyForge_Mesh_Builder_Sidecar_v0.5.2` folder.
3. Double-click `Seal v0.5.2 for Claude.command`.
4. macOS may require Control-click → Open the first time.

The command deliberately creates a clean `.venv`, installs the exact versions in `requirements.txt`, runs Ruff, executes the complete pytest suite with JUnit evidence, asserts zero skipped tests, checks archive hygiene, and creates the release set only if every gate is green.

The local `.venv` and any `.git` metadata are permitted as build-machine state but are excluded from all release archives. Runtime workspace data, `config.json`, caches, compiled Python files, and other forbidden residue remain release-blocking.

## Successful output

A successful run opens this sibling folder:

```text
SkyForge_Mesh_Builder_Sidecar_v0.5.2_RELEASE
```

Send Claude exactly these two files from that folder:

1. `SkyForge_Mesh_Builder_Claude_Review_Package_v0.5.2.zip`
2. `SkyForge_Mesh_Builder_Claude_Review_Package_v0.5.2.zip.sha256`

The review ZIP contains the sealed source ZIP, its source checksum sidecar, `RELEASE_SEAL_EVIDENCE.json`, generated build verification, checksum binding, all required review documents, the prior sealer-refusal evidence, and `MBS-GATE-0001`.

## Failure behavior

If dependency installation, Ruff, pytest, zero-skip enforcement, archive hygiene, ZIP validation, or checksum generation fails, no release directory is created. Preserve the terminal output and return it to ChatGPT. Do not manually zip the tree or create a checksum as a substitute.
