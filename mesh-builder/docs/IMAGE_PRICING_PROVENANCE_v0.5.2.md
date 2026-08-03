# Image Pricing Provenance — v0.5.2

**Retrieval date:** 30 July 2026  
**Authority:** OpenAI official developer documentation

## Sources

- Output-image cost table: `https://developers.openai.com/api/docs/guides/image-generation#calculating-costs`
- Model/token pricing: `https://developers.openai.com/api/docs/pricing`
- Image model capability/catalog pages under `https://developers.openai.com/api/docs/models/`

## Governed output table

`common/image_pricing.py` encodes all 36 cells published for:

- `gpt-image-2`;
- `gpt-image-1.5`;
- `gpt-image-1`;
- `gpt-image-1-mini`;

across low/medium/high and 1024×1024, 1024×1536, and 1536×1024.

The older models remain in the provenance table because their official cells still exist and saved user settings must be estimated honestly or rejected. They are not the v0.5.2 defaults. The official model catalog marks `gpt-image-1.5`, `gpt-image-1`, and `gpt-image-1-mini` deprecated; current defaults therefore use `gpt-image-2`.

## Current default cells

| Stage | Cell | Unit × count | Estimate |
|---|---|---:|---:|
| Beauty exploration | gpt-image-2 / low / 1536×1024 | $0.005 × 2 | $0.010 |
| Beauty refinement | gpt-image-2 / medium / 1536×1024 | $0.041 × 1 | $0.041 |
| Authority draft | gpt-image-2 / low / 1024×1024 | $0.006 × 2 | $0.012 output-only lower bound |
| Authority final | gpt-image-2 / low / 1024×1024 | $0.006 × 1 | $0.006 output-only lower bound |

## Token rates used only for actual reconciliation

| Model | Text input / 1M | Image input / 1M | Image output / 1M |
|---|---:|---:|---:|
| gpt-image-2 | $5.00 | $8.00 | $30.00 |
| gpt-image-1.5 | $5.00 | $8.00 | $32.00 |
| gpt-image-1 | $5.00 | $10.00 | $40.00 |
| gpt-image-1-mini | $2.00 | $2.50 | $8.00 |

These rates are not used to invent a pre-call reference-image token count. They are applied only to usage reported by OpenAI.

## Capability disposition

OpenAI’s current guide explicitly states that `gpt-image-2` does not support transparent backgrounds. v0.5.2 therefore:

- does not claim transparency;
- sends `background=auto` for authority edits;
- retains the accepted opaque-background mask path;
- records `transparentBackgroundClaimed: false` in provenance.

## Fail-closed rule

Any unknown model, quality, size, candidate count, or missing official rate required for a confident calculation is rejected or retained as an explicitly lower-bound status. There is no silent model substitution or fallback price.
