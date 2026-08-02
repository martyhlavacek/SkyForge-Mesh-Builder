from __future__ import annotations

import json
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app import image_governance
from app.image_governance import estimate_display_payload, execute_governed_request
from app.openai_client import AmbiguousOpenAIError, GeneratedImage, ImageGenerationResponse, StageSettings
from common.spend_ledger import BudgetExceeded, LedgerUnavailable, SpendLedger

BUDGET = {
    'perRequestUsdMax': 0.05,
    'perAssetUsdMax': 0.50,
    'perSessionUsdMax': 2.00,
    'confirmationThresholdUsd': 0.02,
}
STAGE = StageSettings('gpt-image-2', 'low', '1024x1024', 2)


def response(request_id: str = 'req_fixture') -> ImageGenerationResponse:
    return ImageGenerationResponse(
        images=[
            GeneratedImage(b'fixture-image-one', 'image/png', 'b64_json'),
            GeneratedImage(b'fixture-image-two', 'image/png', 'b64_json'),
        ],
        usage={
            'input_tokens': 300,
            'output_tokens': 392,
            'total_tokens': 692,
            'input_tokens_details': {'text_tokens': 100, 'image_tokens': 200},
        },
        request_id=request_id,
    )


def run(tmp_path: Path, transport, *, stage: StageSettings = STAGE, budget=BUDGET, prompt='resolved'):
    return execute_governed_request(
        workspace_root=tmp_path,
        session_id='session-1',
        asset_id='enemy.test',
        stage_name='authorityDraft',
        stage_settings=stage,
        budget=budget,
        resolved_prompt=prompt,
        reference_image_sha256='a' * 64,
        confirmed=True,
        transport=transport,
    )


def ledger_entries(tmp_path: Path):
    path = tmp_path / '_concepts' / 'spend_ledger.json'
    return json.loads(path.read_text(encoding='utf-8'))['entries']


def test_cost_estimate_display_payload_has_preflight_cost_and_totals(tmp_path: Path):
    payload = estimate_display_payload(
        workspace_root=tmp_path,
        session_id='session-1',
        asset_id='enemy.test',
        stage_name='authorityDraft',
        stage_settings=STAGE,
        reference_image_count=1,
        budget=BUDGET,
    )
    assert payload['estimate']['estimatedOutputUsd'] == '0.012000'
    assert payload['estimate']['lowerBound'] is True
    assert payload['cumulativeAssetSpendUsd'] == '0.000000'
    assert payload['cumulativeSessionSpendUsd'] == '0.000000'
    assert payload['allowed'] is True


def test_over_budget_rejection_never_calls_transport(tmp_path: Path):
    calls = 0

    def transport():
        nonlocal calls
        calls += 1
        return response()

    expensive = StageSettings('gpt-image-2', 'high', '1024x1024', 1)
    with pytest.raises(BudgetExceeded):
        run(tmp_path, transport, stage=expensive)
    assert calls == 0


def test_unwritable_ledger_rejection_never_calls_transport(tmp_path: Path, monkeypatch):
    calls = 0

    def transport():
        nonlocal calls
        calls += 1
        return response()

    def deny_write(self, payload):
        raise LedgerUnavailable('fixture ledger unwritable')

    monkeypatch.setattr(SpendLedger, '_write', deny_write)
    with pytest.raises(LedgerUnavailable, match='unwritable'):
        run(tmp_path, transport)
    assert calls == 0


def test_reservation_usage_capture_and_reconciliation(tmp_path: Path):
    result = run(tmp_path, response)
    assert result.cache_hit is False
    entry = ledger_entries(tmp_path)[0]
    assert entry['reconciliationStatus'] == 'reconciled'
    assert entry['attemptCount'] == 1
    assert entry['requestId'] == 'req_fixture'
    assert entry['cacheStatus'] == 'stored'
    assert entry['actualOpenAIUsage']['input_tokens'] == 300
    assert entry['calculatedActualCostUsd'] == '0.013860'
    assert entry['actualCostDetails']['imageInputTokens'] == 200
    assert entry['actualCostDetails']['outputPriceBasis'] == 'official_output_token_rate'
    assert entry['actualCostDetails']['outputTokens'] == 392
    assert entry['cumulativeAssetSpendUsd'] == '0.013860'
    assert entry['cumulativeSessionSpendUsd'] == '0.013860'


def test_timeout_retains_reservation_as_possibly_charged_and_is_not_retried(tmp_path: Path):
    calls = 0

    def timeout():
        nonlocal calls
        calls += 1
        raise AmbiguousOpenAIError('fixture timeout may have charged')

    with pytest.raises(AmbiguousOpenAIError):
        run(tmp_path, timeout)
    assert calls == 1
    entry = ledger_entries(tmp_path)[0]
    assert entry['reconciliationStatus'] == 'possibly_charged'
    assert entry['reservedCostUsd'] == '0.012000'
    assert entry['attemptCount'] == 1
    with pytest.raises(RuntimeError, match='possibly charged'):
        run(tmp_path, timeout)
    assert calls == 1


def test_cache_hit_causes_one_transport_call_across_identical_requests(tmp_path: Path):
    calls = 0

    def transport():
        nonlocal calls
        calls += 1
        return response()

    first = run(tmp_path, transport)
    second = run(tmp_path, transport)
    assert calls == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.spend_record['calculatedActualCostUsd'] == '0.000000'
    entries = ledger_entries(tmp_path)
    assert [entry['cacheStatus'] for entry in entries] == ['stored', 'hit']


def test_concurrent_duplicate_suppression_returns_second_from_cache(tmp_path: Path):
    calls = 0
    entered = threading.Event()

    def transport():
        nonlocal calls
        calls += 1
        entered.set()
        time.sleep(0.15)
        return response()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(run, tmp_path, transport)
        assert entered.wait(timeout=2)
        second_future = pool.submit(run, tmp_path, transport)
        first = first_future.result(timeout=5)
        second = second_future.result(timeout=5)
    assert calls == 1
    assert {first.cache_hit, second.cache_hit} == {False, True}


def test_no_secrets_are_written_to_ledger_or_cache(tmp_path: Path):
    secret = 'sk-do-not-write-this'
    run(tmp_path, response, prompt=f'resolved prompt without credential {secret.replace(secret, "redacted")}')
    for path in tmp_path.rglob('*'):
        if path.is_file():
            assert secret.encode() not in path.read_bytes()


def test_billed_cache_write_failure_keeps_actual_spend_and_blocks_duplicate(tmp_path: Path, monkeypatch):
    def fail_cache(*_args, **_kwargs):
        raise OSError('fixture cache failure')

    monkeypatch.setattr(image_governance, '_write_cache', fail_cache)
    result = run(tmp_path, response)
    assert result.spend_record['reconciliationStatus'] == 'reconciled_cache_unavailable'
    assert result.spend_record['calculatedActualCostUsd'] == '0.013860'
    assert result.spend_record['cumulativeAssetSpendUsd'] == '0.013860'
    with pytest.raises(RuntimeError, match='lacks a durable cache'):
        run(tmp_path, response)


def test_corrupted_completed_cache_fails_closed_without_second_transport(tmp_path: Path):
    calls = 0

    def transport():
        nonlocal calls
        calls += 1
        return response()

    first = run(tmp_path, transport)
    cache_image = (
        tmp_path
        / '_concepts'
        / '_cache'
        / first.request_digest
        / 'image_01.png'
    )
    cache_image.write_bytes(b'corrupted')
    with pytest.raises(RuntimeError, match='corrupted local cache'):
        run(tmp_path, transport)
    assert calls == 1


def test_deleted_completed_cache_blocks_second_paid_transport(tmp_path: Path):
    calls = 0

    def transport():
        nonlocal calls
        calls += 1
        return response()

    first = run(tmp_path, transport)
    cache_root = tmp_path / '_concepts' / '_cache' / first.request_digest
    shutil.rmtree(cache_root)
    with pytest.raises(RuntimeError, match='unresolved'):
        run(tmp_path, transport)
    assert calls == 1
