from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

PRICING_RETRIEVED = '2026-07-30'
PRICING_SOURCE = 'https://developers.openai.com/api/docs/guides/image-generation#calculating-costs'
PRICING_SOURCE_KIND = 'OpenAI official image-generation output-image cost table'

# Official USD output-image unit costs retrieved 2026-07-30. Data is deliberately
# exhaustive and fail-closed: adding a model to Settings does not make it priced.
OUTPUT_IMAGE_USD: dict[tuple[str, str, str], Decimal] = {
    ('gpt-image-2', 'low', '1024x1024'): Decimal('0.006'),
    ('gpt-image-2', 'low', '1024x1536'): Decimal('0.005'),
    ('gpt-image-2', 'low', '1536x1024'): Decimal('0.005'),
    ('gpt-image-2', 'medium', '1024x1024'): Decimal('0.053'),
    ('gpt-image-2', 'medium', '1024x1536'): Decimal('0.041'),
    ('gpt-image-2', 'medium', '1536x1024'): Decimal('0.041'),
    ('gpt-image-2', 'high', '1024x1024'): Decimal('0.211'),
    ('gpt-image-2', 'high', '1024x1536'): Decimal('0.165'),
    ('gpt-image-2', 'high', '1536x1024'): Decimal('0.165'),
    ('gpt-image-1.5', 'low', '1024x1024'): Decimal('0.009'),
    ('gpt-image-1.5', 'low', '1024x1536'): Decimal('0.013'),
    ('gpt-image-1.5', 'low', '1536x1024'): Decimal('0.013'),
    ('gpt-image-1.5', 'medium', '1024x1024'): Decimal('0.034'),
    ('gpt-image-1.5', 'medium', '1024x1536'): Decimal('0.050'),
    ('gpt-image-1.5', 'medium', '1536x1024'): Decimal('0.050'),
    ('gpt-image-1.5', 'high', '1024x1024'): Decimal('0.133'),
    ('gpt-image-1.5', 'high', '1024x1536'): Decimal('0.200'),
    ('gpt-image-1.5', 'high', '1536x1024'): Decimal('0.200'),
    ('gpt-image-1', 'low', '1024x1024'): Decimal('0.011'),
    ('gpt-image-1', 'low', '1024x1536'): Decimal('0.016'),
    ('gpt-image-1', 'low', '1536x1024'): Decimal('0.016'),
    ('gpt-image-1', 'medium', '1024x1024'): Decimal('0.042'),
    ('gpt-image-1', 'medium', '1024x1536'): Decimal('0.063'),
    ('gpt-image-1', 'medium', '1536x1024'): Decimal('0.063'),
    ('gpt-image-1', 'high', '1024x1024'): Decimal('0.167'),
    ('gpt-image-1', 'high', '1024x1536'): Decimal('0.250'),
    ('gpt-image-1', 'high', '1536x1024'): Decimal('0.250'),
    ('gpt-image-1-mini', 'low', '1024x1024'): Decimal('0.005'),
    ('gpt-image-1-mini', 'low', '1024x1536'): Decimal('0.006'),
    ('gpt-image-1-mini', 'low', '1536x1024'): Decimal('0.006'),
    ('gpt-image-1-mini', 'medium', '1024x1024'): Decimal('0.011'),
    ('gpt-image-1-mini', 'medium', '1024x1536'): Decimal('0.015'),
    ('gpt-image-1-mini', 'medium', '1536x1024'): Decimal('0.015'),
    ('gpt-image-1-mini', 'high', '1024x1024'): Decimal('0.036'),
    ('gpt-image-1-mini', 'high', '1024x1536'): Decimal('0.052'),
    ('gpt-image-1-mini', 'high', '1536x1024'): Decimal('0.052'),
}

# Official per-million input token rates used only when a response supplies usage.
# A missing rate is not guessed; reconciliation stays output-only/lower-bound.
IMAGE_OUTPUT_TOKEN_USD_PER_MILLION: dict[str, Decimal] = {
    'gpt-image-2': Decimal('30.00'),
    'gpt-image-1.5': Decimal('32.00'),
    'gpt-image-1': Decimal('40.00'),
    'gpt-image-1-mini': Decimal('8.00'),
}

INPUT_TOKEN_USD_PER_MILLION: dict[str, dict[str, Decimal]] = {
    'gpt-image-2': {'text': Decimal('5.00'), 'image': Decimal('8.00')},
    'gpt-image-1': {'text': Decimal('5.00'), 'image': Decimal('10.00')},
    'gpt-image-1.5': {'text': Decimal('5.00'), 'image': Decimal('8.00')},
    'gpt-image-1-mini': {'text': Decimal('2.00'), 'image': Decimal('2.50')},
}


class PricingUnavailable(ValueError):
    """Raised when a request is not represented by official governed pricing."""


@dataclass(frozen=True)
class ImageCostEstimate:
    model: str
    quality: str
    size: str
    candidate_count: int
    unit_output_usd: Decimal
    estimated_output_usd: Decimal
    reference_image_count: int
    reference_input_cost_known: bool
    lower_bound: bool
    pricing_retrieved: str = PRICING_RETRIEVED
    pricing_source: str = PRICING_SOURCE

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ('unit_output_usd', 'estimated_output_usd'):
            payload[key] = f'{payload[key]:.6f}'
        return {
            'model': payload['model'],
            'quality': payload['quality'],
            'size': payload['size'],
            'candidateCount': payload['candidate_count'],
            'unitOutputUsd': payload['unit_output_usd'],
            'estimatedOutputUsd': payload['estimated_output_usd'],
            'referenceImageCount': payload['reference_image_count'],
            'referenceInputCostKnown': payload['reference_input_cost_known'],
            'lowerBound': payload['lower_bound'],
            'pricingRetrieved': payload['pricing_retrieved'],
            'pricingSource': payload['pricing_source'],
        }


def estimate_output_cost(
    model: str,
    quality: str,
    size: str,
    candidate_count: int,
    *,
    reference_image_count: int = 0,
) -> ImageCostEstimate:
    if not isinstance(candidate_count, int) or not 1 <= candidate_count <= 4:
        raise PricingUnavailable('Candidate count must be between 1 and 4')
    key = (model.strip(), quality.strip(), size.strip())
    try:
        unit = OUTPUT_IMAGE_USD[key]
    except KeyError as exc:
        raise PricingUnavailable(
            f'No governed official price for model={key[0]!r}, quality={key[1]!r}, size={key[2]!r}'
        ) from exc
    reference_count = max(0, int(reference_image_count))
    return ImageCostEstimate(
        model=key[0],
        quality=key[1],
        size=key[2],
        candidate_count=candidate_count,
        unit_output_usd=unit,
        estimated_output_usd=unit * candidate_count,
        reference_image_count=reference_count,
        reference_input_cost_known=False,
        lower_bound=reference_count > 0,
    )


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def calculate_actual_cost(
    estimate: ImageCostEstimate,
    usage: dict[str, Any] | None,
    *,
    actual_image_count: int,
) -> tuple[Decimal, str, dict[str, Any]]:
    """Reconcile actual cost from usage when the response provides it.

    Output tokens are priced from the official per-model image-output token
    rate. Input text/image tokens are added only when the response supplies a
    detailed breakdown and official rates exist. If usage is missing or
    incomplete, output cost falls back to the governed per-image table and the
    result stays explicitly lower-bound.
    """
    usage_payload = usage if isinstance(usage, dict) else {}
    output_rate = IMAGE_OUTPUT_TOKEN_USD_PER_MILLION.get(estimate.model)
    raw_output_tokens = usage_payload.get('output_tokens') or usage_payload.get('outputTokens')
    output_tokens = _nonnegative_int(raw_output_tokens)

    if output_tokens > 0 and output_rate is not None:
        output_cost = Decimal(output_tokens) * output_rate / Decimal(1_000_000)
        output_basis = 'official_output_token_rate'
    else:
        output_cost = estimate.unit_output_usd * max(0, int(actual_image_count))
        output_basis = 'official_output_image_table_fallback'

    details: dict[str, Any] = {
        'outputImageUsd': f'{output_cost:.6f}',
        'outputPriceBasis': output_basis,
        'outputTokens': output_tokens,
        'outputTokenRateUsdPerMillion': (
            f'{output_rate:.6f}' if output_rate is not None else None
        ),
        'inputTokenUsd': '0.000000',
        'inputTokenRatesAvailable': estimate.model in INPUT_TOKEN_USD_PER_MILLION,
    }
    if not usage_payload:
        return output_cost, 'output_image_table_fallback_no_usage', details

    rates = INPUT_TOKEN_USD_PER_MILLION.get(estimate.model)
    input_details = (
        usage_payload.get('input_tokens_details')
        or usage_payload.get('inputTokensDetails')
        or {}
    )
    if not isinstance(input_details, dict) or not rates:
        status = (
            'output_usage_missing_official_input_rate'
            if not rates
            else 'output_usage_without_input_breakdown'
        )
        return output_cost, status, details

    text_tokens = _nonnegative_int(
        input_details.get('text_tokens') or input_details.get('textTokens')
    )
    image_tokens = _nonnegative_int(
        input_details.get('image_tokens') or input_details.get('imageTokens')
    )
    input_cost = (
        Decimal(text_tokens) * rates['text'] / Decimal(1_000_000)
        + Decimal(image_tokens) * rates['image'] / Decimal(1_000_000)
    )
    details.update({
        'textInputTokens': text_tokens,
        'imageInputTokens': image_tokens,
        'inputTokenUsd': f'{input_cost:.6f}',
    })
    if output_basis == 'official_output_token_rate':
        status = 'reconciled_from_usage'
    else:
        status = 'reconciled_input_usage_output_image_table_fallback'
    return output_cost + input_cost, status, details


def governed_cells() -> list[dict[str, str]]:
    return [
        {
            'model': model,
            'quality': quality,
            'size': size,
            'unitCostUsd': f'{cost:.6f}',
            'retrievalDate': PRICING_RETRIEVED,
            'source': PRICING_SOURCE,
        }
        for (model, quality, size), cost in sorted(OUTPUT_IMAGE_USD.items())
    ]
