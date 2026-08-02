# SF-AM-0001 — Rule 5 Socket Ownership Amendment

**Amendment version:** 1.0.0  
**Effective contract:** `skyforge.manufacturing-axes.v1`  
**Status:** required v0.7.0 governing-document amendment

Mesh Foundry MAY emit approved or candidate 3D sockets in normalized mesh coordinates.
Sprite Foundry owns projection of those 3D sockets into every authored sprite frame and
stores the resulting per-frame 2D sockets in the Gameplay Sprite Package. Gameplay
integration validates and consumes the 2D sockets and may reject them, but does not own
projection and does not reach back into Mesh Foundry.

The versioned machine-readable ownership enumeration is `contracts/vmp/v1/schemas/manufacturing_axes.schema.json`. The independent Import Probe must compare the package declaration with that enumeration and reject any mismatch.
