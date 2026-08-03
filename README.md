# Project SkyForge Mesh Builder

This is the private Project SkyForge Mesh Builder sidecar repository.

- `mesh-builder/` contains the accepted producer.
- `import-probe/` contains the independent Sprite Foundry consumer/probe.
- ChatGPT implements.
- Claude performs independent adversarial review against exact commits.
- Marty performs user testing only after an exact commit has passed CI and Claude review.

No paid Meshy or other provider work is authorized. MBS-136 remains open against a real provider. MBS-150 through MBS-154 remain open geometry-quality findings, and MBS-158 and MBS-159 remain open macOS launcher/setup usability findings. The accepted v0.7.1 baseline contains no geometry fix for MBS-150 through MBS-154.

The accepted source identities and the corrected Import Probe provenance are recorded in `BASELINE_LOCK.json` and `docs/baseline/BOOTSTRAP_PROVENANCE_CORRECTION_001.md`.
