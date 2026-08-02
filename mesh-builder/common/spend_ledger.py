from __future__ import annotations

import json
import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

_LEDGER_LOCK = threading.RLock()


class LedgerUnavailable(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _money(value: Decimal | str | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.000001'))


def _money_string(value: Decimal | str | float | int) -> str:
    return f'{_money(value):.6f}'


class SpendLedger:
    def __init__(self, path: Path, *, session_id: str) -> None:
        self.path = path
        self.session_id = session_id

    def _empty(self) -> dict[str, Any]:
        return {'schemaVersion': 'skyforge.image-spend-ledger.v1', 'entries': []}

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise LedgerUnavailable('Spend ledger cannot be read safely') from exc
        if not isinstance(payload, dict) or not isinstance(payload.get('entries'), list):
            raise LedgerUnavailable('Spend ledger schema is invalid')
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_name(f'.{self.path.name}.{uuid.uuid4().hex}.tmp')
            with temp.open('w', encoding='utf-8') as stream:
                json.dump(payload, stream, indent=2, sort_keys=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            temp.replace(self.path)
        except OSError as exc:
            try:
                temp.unlink(missing_ok=True)
            except (OSError, UnboundLocalError):
                pass
            raise LedgerUnavailable('Spend ledger cannot be written; generation denied') from exc

    @staticmethod
    def _entry_cost(entry: dict[str, Any]) -> Decimal:
        status = entry.get('reconciliationStatus')
        if status == 'cache_hit':
            return Decimal('0')
        if status in {'reconciled', 'reconciled_lower_bound', 'reconciled_cache_unavailable'} and entry.get('calculatedActualCostUsd') is not None:
            return _money(entry['calculatedActualCostUsd'])
        return _money(entry.get('reservedCostUsd') or entry.get('estimatedOutputCostUsd') or 0)

    def totals(self, *, asset_id: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, str]:
        ledger = payload or self._read()
        asset = Decimal('0')
        session = Decimal('0')
        for entry in ledger['entries']:
            cost = self._entry_cost(entry)
            if entry.get('sessionId') == self.session_id:
                session += cost
            if asset_id is not None and entry.get('assetId') == asset_id:
                asset += cost
        return {'assetUsd': _money_string(asset), 'sessionUsd': _money_string(session)}

    def unresolved_for_digest(self, request_digest: str) -> bool:
        with _LEDGER_LOCK:
            payload = self._read()
            return any(
                entry.get('requestDigest') == request_digest
                and entry.get('reconciliationStatus') in {
                    'reserved',
                    'possibly_charged',
                    'reconciled',
                    'reconciled_lower_bound',
                    'reconciled_cache_unavailable',
                }
                for entry in payload['entries']
            )

    def assert_writable(self) -> None:
        with _LEDGER_LOCK:
            payload = self._read()
            self._write(payload)

    def reserve(
        self,
        *,
        request_digest: str,
        asset_id: str,
        stage: str,
        model: str,
        quality: str,
        size: str,
        candidate_count: int,
        estimated_output_cost_usd: Decimal,
        pricing_retrieval_date: str,
        pricing_source: str,
        lower_bound: bool,
        budget: dict[str, Any],
    ) -> dict[str, Any]:
        with _LEDGER_LOCK:
            payload = self._read()
            totals = self.totals(asset_id=asset_id, payload=payload)
            estimate = _money(estimated_output_cost_usd)
            per_request = _money(budget['perRequestUsdMax'])
            per_asset = _money(budget['perAssetUsdMax'])
            per_session = _money(budget['perSessionUsdMax'])
            if estimate > per_request:
                raise BudgetExceeded(f'Estimated charge ${estimate:.3f} exceeds per-request maximum ${per_request:.2f}')
            if _money(totals['assetUsd']) + estimate > per_asset:
                raise BudgetExceeded(f'Estimated charge would exceed the ${per_asset:.2f} per-asset maximum')
            if _money(totals['sessionUsd']) + estimate > per_session:
                raise BudgetExceeded(f'Estimated charge would exceed the ${per_session:.2f} per-session maximum')
            entry = {
                'reservationId': uuid.uuid4().hex,
                'requestDigest': request_digest,
                'sessionId': self.session_id,
                'assetId': asset_id,
                'stage': stage,
                'model': model,
                'quality': quality,
                'size': size,
                'candidateCount': candidate_count,
                'estimatedOutputCostUsd': _money_string(estimate),
                'reservedCostUsd': _money_string(estimate),
                'pricingRetrievalDate': pricing_retrieval_date,
                'pricingSource': pricing_source,
                'estimateLowerBound': bool(lower_bound),
                'actualOpenAIUsage': None,
                'calculatedActualCostUsd': None,
                'requestId': None,
                'cacheStatus': 'miss',
                'attemptCount': 0,
                'reconciliationStatus': 'reserved',
                'createdAt': utc_now(),
                'updatedAt': utc_now(),
            }
            payload['entries'].append(entry)
            cumulative = self.totals(asset_id=asset_id, payload=payload)
            entry['cumulativeAssetSpendUsd'] = cumulative['assetUsd']
            entry['cumulativeSessionSpendUsd'] = cumulative['sessionUsd']
            self._write(payload)
            return deepcopy(entry)

    def _update(self, reservation_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        with _LEDGER_LOCK:
            payload = self._read()
            entry = next((item for item in payload['entries'] if item.get('reservationId') == reservation_id), None)
            if entry is None:
                raise LedgerUnavailable('Spend reservation no longer exists')
            entry.update(updates)
            entry['updatedAt'] = utc_now()
            totals = self.totals(asset_id=entry.get('assetId'), payload=payload)
            entry['cumulativeAssetSpendUsd'] = totals['assetUsd']
            entry['cumulativeSessionSpendUsd'] = totals['sessionUsd']
            self._write(payload)
            return deepcopy(entry)

    def mark_attempt(self, reservation_id: str) -> dict[str, Any]:
        with _LEDGER_LOCK:
            payload = self._read()
            entry = next((item for item in payload['entries'] if item.get('reservationId') == reservation_id), None)
            if entry is None:
                raise LedgerUnavailable('Spend reservation no longer exists')
            count = int(entry.get('attemptCount') or 0) + 1
        return self._update(reservation_id, {'attemptCount': count})

    def reconcile(
        self,
        reservation_id: str,
        *,
        usage: dict[str, Any] | None,
        actual_cost_usd: Decimal,
        cost_status: str,
        request_id: str | None,
        cost_details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status = 'reconciled' if cost_status == 'reconciled_from_usage' else 'reconciled_lower_bound'
        return self._update(reservation_id, {
            'actualOpenAIUsage': usage,
            'calculatedActualCostUsd': _money_string(actual_cost_usd),
            'requestId': request_id,
            'actualCostCalculationStatus': cost_status,
            'actualCostDetails': cost_details or {},
            'reconciliationStatus': status,
        })

    def mark_cache_stored(self, reservation_id: str) -> dict[str, Any]:
        return self._update(reservation_id, {'cacheStatus': 'stored'})

    def mark_cache_unavailable(self, reservation_id: str, *, reason: str) -> dict[str, Any]:
        return self._update(reservation_id, {
            'reconciliationStatus': 'reconciled_cache_unavailable',
            'cacheStatus': 'write_failed',
            'cacheFailureReason': reason[:240],
        })

    def possibly_charged(self, reservation_id: str, *, reason: str) -> dict[str, Any]:
        return self._update(reservation_id, {
            'reconciliationStatus': 'possibly_charged',
            'failureClass': 'ambiguous_network_failure',
            'failureReason': reason[:240],
        })

    def failed_not_charged(self, reservation_id: str, *, reason: str) -> dict[str, Any]:
        return self._update(reservation_id, {
            'reservedCostUsd': '0.000000',
            'reconciliationStatus': 'failed_not_charged',
            'failureReason': reason[:240],
        })

    def record_cache_hit(
        self,
        *,
        request_digest: str,
        asset_id: str,
        stage: str,
        model: str,
        quality: str,
        size: str,
        candidate_count: int,
        pricing_retrieval_date: str,
        pricing_source: str,
    ) -> dict[str, Any]:
        with _LEDGER_LOCK:
            payload = self._read()
            entry = {
                'reservationId': uuid.uuid4().hex,
                'requestDigest': request_digest,
                'sessionId': self.session_id,
                'assetId': asset_id,
                'stage': stage,
                'model': model,
                'quality': quality,
                'size': size,
                'candidateCount': candidate_count,
                'estimatedOutputCostUsd': '0.000000',
                'reservedCostUsd': '0.000000',
                'pricingRetrievalDate': pricing_retrieval_date,
                'pricingSource': pricing_source,
                'actualOpenAIUsage': None,
                'calculatedActualCostUsd': '0.000000',
                'requestId': None,
                'cacheStatus': 'hit',
                'attemptCount': 0,
                'reconciliationStatus': 'cache_hit',
                'createdAt': utc_now(),
                'updatedAt': utc_now(),
            }
            payload['entries'].append(entry)
            totals = self.totals(asset_id=asset_id, payload=payload)
            entry['cumulativeAssetSpendUsd'] = totals['assetUsd']
            entry['cumulativeSessionSpendUsd'] = totals['sessionUsd']
            self._write(payload)
            return deepcopy(entry)
