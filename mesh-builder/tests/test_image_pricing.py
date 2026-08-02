from __future__ import annotations

from decimal import Decimal

import pytest

from common.image_pricing import (
    OUTPUT_IMAGE_USD,
    PricingUnavailable,
    calculate_actual_cost,
    estimate_output_cost,
    governed_cells,
)

EXPECTED = {
    ('gpt-image-2', 'low', '1024x1024'): '0.006',
    ('gpt-image-2', 'low', '1024x1536'): '0.005',
    ('gpt-image-2', 'low', '1536x1024'): '0.005',
    ('gpt-image-2', 'medium', '1024x1024'): '0.053',
    ('gpt-image-2', 'medium', '1024x1536'): '0.041',
    ('gpt-image-2', 'medium', '1536x1024'): '0.041',
    ('gpt-image-2', 'high', '1024x1024'): '0.211',
    ('gpt-image-2', 'high', '1024x1536'): '0.165',
    ('gpt-image-2', 'high', '1536x1024'): '0.165',
    ('gpt-image-1.5', 'low', '1024x1024'): '0.009',
    ('gpt-image-1.5', 'low', '1024x1536'): '0.013',
    ('gpt-image-1.5', 'low', '1536x1024'): '0.013',
    ('gpt-image-1.5', 'medium', '1024x1024'): '0.034',
    ('gpt-image-1.5', 'medium', '1024x1536'): '0.050',
    ('gpt-image-1.5', 'medium', '1536x1024'): '0.050',
    ('gpt-image-1.5', 'high', '1024x1024'): '0.133',
    ('gpt-image-1.5', 'high', '1024x1536'): '0.200',
    ('gpt-image-1.5', 'high', '1536x1024'): '0.200',
    ('gpt-image-1', 'low', '1024x1024'): '0.011',
    ('gpt-image-1', 'low', '1024x1536'): '0.016',
    ('gpt-image-1', 'low', '1536x1024'): '0.016',
    ('gpt-image-1', 'medium', '1024x1024'): '0.042',
    ('gpt-image-1', 'medium', '1024x1536'): '0.063',
    ('gpt-image-1', 'medium', '1536x1024'): '0.063',
    ('gpt-image-1', 'high', '1024x1024'): '0.167',
    ('gpt-image-1', 'high', '1024x1536'): '0.250',
    ('gpt-image-1', 'high', '1536x1024'): '0.250',
    ('gpt-image-1-mini', 'low', '1024x1024'): '0.005',
    ('gpt-image-1-mini', 'low', '1024x1536'): '0.006',
    ('gpt-image-1-mini', 'low', '1536x1024'): '0.006',
    ('gpt-image-1-mini', 'medium', '1024x1024'): '0.011',
    ('gpt-image-1-mini', 'medium', '1024x1536'): '0.015',
    ('gpt-image-1-mini', 'medium', '1536x1024'): '0.015',
    ('gpt-image-1-mini', 'high', '1024x1024'): '0.036',
    ('gpt-image-1-mini', 'high', '1024x1536'): '0.052',
    ('gpt-image-1-mini', 'high', '1536x1024'): '0.052',
}


def test_every_governed_pricing_cell_matches_official_snapshot():
    assert len(EXPECTED) == 36
    assert set(OUTPUT_IMAGE_USD) == set(EXPECTED)
    assert {key: f'{value:.3f}' for key, value in OUTPUT_IMAGE_USD.items()} == EXPECTED
    cells = governed_cells()
    assert len(cells) == 36
    assert all(cell['retrievalDate'] == '2026-07-30' for cell in cells)
    assert all(cell['source'].startswith('https://developers.openai.com/') for cell in cells)


def test_unknown_price_combination_fails_closed():
    with pytest.raises(PricingUnavailable, match='No governed official price'):
        estimate_output_cost('future-image-model', 'low', '1024x1024', 1)
    with pytest.raises(PricingUnavailable):
        estimate_output_cost('gpt-image-2', 'ultra', '1024x1024', 1)
    with pytest.raises(PricingUnavailable):
        estimate_output_cost('gpt-image-2', 'low', '2048x2048', 1)


def test_output_estimate_is_separate_and_authority_is_lower_bound():
    beauty = estimate_output_cost('gpt-image-2', 'low', '1536x1024', 2)
    authority = estimate_output_cost(
        'gpt-image-2', 'low', '1024x1024', 2, reference_image_count=1
    )
    assert beauty.estimated_output_usd == Decimal('0.010')
    assert beauty.lower_bound is False
    assert authority.estimated_output_usd == Decimal('0.012')
    assert authority.lower_bound is True
    assert authority.to_dict()['referenceInputCostKnown'] is False


def test_actual_usage_reconciliation_prices_output_and_input_tokens():
    estimate = estimate_output_cost(
        'gpt-image-2', 'low', '1024x1024', 2, reference_image_count=1
    )
    usage = {
        'output_tokens': 392,
        'input_tokens_details': {'text_tokens': 100, 'image_tokens': 200},
    }
    actual, status, details = calculate_actual_cost(
        estimate, usage, actual_image_count=2
    )
    assert actual == Decimal('0.01386')
    assert status == 'reconciled_from_usage'
    assert details['outputImageUsd'] == '0.011760'
    assert details['inputTokenUsd'] == '0.002100'
    assert details['outputPriceBasis'] == 'official_output_token_rate'


def test_missing_usage_keeps_output_table_fallback_explicit():
    estimate = estimate_output_cost(
        'gpt-image-2', 'low', '1024x1024', 2, reference_image_count=1
    )
    actual, status, details = calculate_actual_cost(
        estimate, None, actual_image_count=2
    )
    assert actual == Decimal('0.012')
    assert status == 'output_image_table_fallback_no_usage'
    assert details['outputPriceBasis'] == 'official_output_image_table_fallback'
