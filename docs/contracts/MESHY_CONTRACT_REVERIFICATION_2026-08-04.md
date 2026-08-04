# Meshy Contract Re-verification — 2026-08-04

Retrieved at `2026-08-04T03:23:05Z`, immediately before implementation, from official Meshy documentation:

- Multi-Image to 3D API: <https://docs.meshy.ai/en/api/multi-image-to-3d>
- API pricing: <https://docs.meshy.ai/en/api/pricing>
- Asset retention: <https://docs.meshy.ai/en/api/asset-retention>
- API changelog: <https://docs.meshy.ai/en/api/changelog>

The official contract matched every committed preauthorization assumption:

- create: `POST /openapi/v1/multi-image-to-3d`;
- retrieve: `GET /openapi/v1/multi-image-to-3d/{id}`;
- one through four JPG, JPEG, or PNG inputs supplied as public URLs or Data URIs;
- Bearer authentication;
- `ai_model: meshy-6`;
- `should_texture: false`;
- `should_remesh: false`;
- `image_enhancement: false`;
- `auto_size: false`;
- `target_formats: ["glb"]`;
- Meshy-6 multi-image mesh generation without texture: 20 credits;
- this candidate's maximum future authorization: 20 credits;
- non-Enterprise API assets: maximum three-day retention;
- documented initial artifact hostname in the official task response example: `assets.meshy.ai`.

Any future material difference must fail closed and require a new contract review. The documentation does not authorize unknown redirect hosts. This verification did not authenticate, create or poll a task, download an artifact, or consume credits.
