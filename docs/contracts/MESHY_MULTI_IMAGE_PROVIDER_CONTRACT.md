# Meshy Multi-Image Provider Contract Snapshot

**Retrieved:** 3 August 2026  
**Status:** External and time-sensitive. Re-verify official documentation before a live call.

## Endpoint

- `POST https://api.meshy.ai/openapi/v1/multi-image-to-3d`
- `GET https://api.meshy.ai/openapi/v1/multi-image-to-3d/{id}`

## Relevant current contract

The official API currently accepts one to four JPG/JPEG/PNG images through public URLs or base64 Data URIs. Images should depict the same object from different angles.

Relevant parameters include `ai_model`, `should_texture`, `enable_pbr`, `texture_resolution`, `should_remesh`, `topology`, `target_polycount`, `save_pre_remeshed_model`, `image_enhancement`, `remove_lighting`, `target_formats`, `auto_size`, and `multi_view_thumbnails`.

## Approved future smoke profile

```json
{
  "image_urls": [
    "<top data URI>",
    "<front data URI>",
    "<right data URI>"
  ],
  "ai_model": "meshy-6",
  "should_texture": false,
  "should_remesh": false,
  "image_enhancement": false,
  "auto_size": false,
  "target_formats": ["glb"]
}
```

## Current credit assumptions

At retrieval time official pricing lists:

- Meshy-6 Multi-Image to 3D without texture: 20 credits;
- with texture: 30 credits;
- with 8K texture: 35 credits.

The implementation candidate must spend zero credits. A future geometry smoke test has a proposed maximum of 20 credits and must fail closed if the current estimate differs.

## Authentication and secrecy

Authentication uses a Bearer API key. Do not commit it, persist the Authorization header, or expose the key in logs, evidence, exceptions, command arguments, or manifests. Reuse accepted secure credential handling where possible.

## Task and retention behavior

The create response returns a task ID. Persist it immediately. Completed tasks may include status, progress, model URLs, thumbnails, task errors, and consumed credits.

Official documentation currently states non-Enterprise API assets are retained for at most three days. Download and hash successful outputs immediately; never use provider URLs as durable storage.

## Failure handling

Handle 400, 401, 402, and 429 explicitly. Polling can use bounded backoff. Creating another paid task must never be an automatic retry.

## Official references

- https://docs.meshy.ai/en/api/multi-image-to-3d
- https://docs.meshy.ai/en/api/pricing
- https://docs.meshy.ai/en/api/rate-limits
- https://docs.meshy.ai/en/api/asset-retention
- https://docs.meshy.ai/en/api/authentication
