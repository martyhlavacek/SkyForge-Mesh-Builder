from __future__ import annotations

import hashlib
import json
import shutil
import threading
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from common.image_pricing import ImageCostEstimate, calculate_actual_cost, estimate_output_cost
from common.spend_ledger import BudgetExceeded, LedgerUnavailable, SpendLedger

from .openai_client import AmbiguousOpenAIError, GeneratedImage, ImageGenerationResponse, StageSettings

_DIGEST_LOCKS: dict[str, threading.Lock] = {}
_DIGEST_LOCKS_GUARD = threading.RLock()


class ConfirmationRequired(RuntimeError):
    pass


class DuplicatePossiblyCharged(RuntimeError):
    pass


class CacheIntegrityError(DuplicatePossiblyCharged):
    pass


@dataclass(frozen=True)
class GovernedImageResult:
    images: list[GeneratedImage]
    request_digest: str
    cache_hit: bool
    estimate: ImageCostEstimate
    spend_record: dict[str, Any]
    usage: dict[str, Any] | None
    request_id: str | None


def request_digest(
    *,
    model: str,
    quality: str,
    size: str,
    candidate_count: int,
    resolved_prompt: str,
    reference_image_sha256: str | None,
) -> str:
    canonical = json.dumps(
        {
            'model': model,
            'quality': quality,
            'size': size,
            'candidateCount': candidate_count,
            'resolvedPrompt': resolved_prompt,
            'referenceImageSha256': reference_image_sha256,
        },
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def _lock_for(digest: str) -> threading.Lock:
    with _DIGEST_LOCKS_GUARD:
        return _DIGEST_LOCKS.setdefault(digest, threading.Lock())


def _cache_root(workspace_root: Path, digest: str) -> Path:
    return workspace_root / '_concepts' / '_cache' / digest


def _read_cache(workspace_root: Path, digest: str) -> tuple[list[GeneratedImage], dict[str, Any]] | None:
    root = _cache_root(workspace_root, digest)
    if not root.exists():
        return None
    metadata_path = root / 'metadata.json'
    if not metadata_path.is_file():
        raise CacheIntegrityError(
            'An identical completed request has an incomplete local cache; paid regeneration is denied'
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        images = []
        for item in metadata['images']:
            path = root / item['filename']
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != item['sha256']:
                raise CacheIntegrityError(
                    'An identical completed request has a corrupted local cache; paid regeneration is denied'
                )
            images.append(GeneratedImage(data, item['mimeType'], 'content_addressed_cache'))
        if not images:
            raise CacheIntegrityError(
                'An identical completed request has an empty local cache; paid regeneration is denied'
            )
        return images, metadata
    except CacheIntegrityError:
        raise
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise CacheIntegrityError(
            'An identical completed request has an unreadable local cache; paid regeneration is denied'
        ) from exc


def _write_cache(
    workspace_root: Path,
    digest: str,
    response: ImageGenerationResponse,
    *,
    stage: str,
    stage_settings: StageSettings,
) -> None:
    final = _cache_root(workspace_root, digest)
    if final.exists():
        return
    parent = final.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp = parent / f'.{digest}.{uuid.uuid4().hex}.tmp'
    temp.mkdir(parents=False, exist_ok=False)
    try:
        image_records = []
        for index, image in enumerate(response.images, start=1):
            filename = f'image_{index:02d}.png'
            data = image.bytes_data
            (temp / filename).write_bytes(data)
            image_records.append({
                'filename': filename,
                'mimeType': image.mime_type,
                'sha256': hashlib.sha256(data).hexdigest(),
            })
        (temp / 'metadata.json').write_text(
            json.dumps(
                {
                    'schemaVersion': 'skyforge.image-cache.v1',
                    'requestDigest': digest,
                    'stage': stage,
                    'model': stage_settings.model,
                    'quality': stage_settings.quality,
                    'size': stage_settings.size,
                    'candidateCount': stage_settings.candidate_count,
                    'usage': response.usage,
                    'requestId': response.request_id,
                    'images': image_records,
                },
                indent=2,
            ) + '\n',
            encoding='utf-8',
        )
        temp.replace(final)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def estimate_request(
    *,
    stage_settings: StageSettings,
    reference_image_count: int,
) -> ImageCostEstimate:
    return estimate_output_cost(
        stage_settings.model,
        stage_settings.quality,
        stage_settings.size,
        stage_settings.candidate_count,
        reference_image_count=reference_image_count,
    )


def estimate_display_payload(
    *,
    workspace_root: Path,
    session_id: str,
    asset_id: str,
    stage_name: str,
    stage_settings: StageSettings,
    reference_image_count: int,
    budget: dict[str, Any],
) -> dict[str, Any]:
    estimate = estimate_request(stage_settings=stage_settings, reference_image_count=reference_image_count)
    ledger = SpendLedger(workspace_root / '_concepts' / 'spend_ledger.json', session_id=session_id)
    ledger.assert_writable()
    totals = ledger.totals(asset_id=asset_id)
    threshold = Decimal(str(budget['confirmationThresholdUsd']))
    estimated = estimate.estimated_output_usd
    reasons = []
    if estimated > Decimal(str(budget['perRequestUsdMax'])):
        reasons.append('per-request budget would be exceeded')
    if Decimal(totals['assetUsd']) + estimated > Decimal(str(budget['perAssetUsdMax'])):
        reasons.append('per-asset budget would be exceeded')
    if Decimal(totals['sessionUsd']) + estimated > Decimal(str(budget['perSessionUsdMax'])):
        reasons.append('per-session budget would be exceeded')
    return {
        'stage': stage_name,
        'estimate': estimate.to_dict(),
        'requiresConfirmation': estimated > threshold,
        'confirmationThresholdUsd': f'{threshold:.6f}',
        'cumulativeAssetSpendUsd': totals['assetUsd'],
        'cumulativeSessionSpendUsd': totals['sessionUsd'],
        'budget': {key: f'{Decimal(str(value)):.6f}' for key, value in budget.items()},
        'allowed': not reasons,
        'denialReasons': reasons,
    }


def execute_governed_request(
    *,
    workspace_root: Path,
    session_id: str,
    asset_id: str,
    stage_name: str,
    stage_settings: StageSettings,
    budget: dict[str, Any],
    resolved_prompt: str,
    reference_image_sha256: str | None,
    confirmed: bool,
    transport: Callable[[], ImageGenerationResponse],
) -> GovernedImageResult:
    estimate = estimate_request(
        stage_settings=stage_settings,
        reference_image_count=1 if reference_image_sha256 else 0,
    )
    if estimate.estimated_output_usd > Decimal(str(budget['confirmationThresholdUsd'])) and not confirmed:
        raise ConfirmationRequired('Estimated charge exceeds the confirmation threshold')
    digest = request_digest(
        model=stage_settings.model,
        quality=stage_settings.quality,
        size=stage_settings.size,
        candidate_count=stage_settings.candidate_count,
        resolved_prompt=resolved_prompt,
        reference_image_sha256=reference_image_sha256,
    )
    ledger = SpendLedger(workspace_root / '_concepts' / 'spend_ledger.json', session_id=session_id)

    with _lock_for(digest):
        cached = _read_cache(workspace_root, digest)
        if cached is not None:
            images, cache_metadata = cached
            cache_record = ledger.record_cache_hit(
                request_digest=digest,
                asset_id=asset_id,
                stage=stage_name,
                model=stage_settings.model,
                quality=stage_settings.quality,
                size=stage_settings.size,
                candidate_count=stage_settings.candidate_count,
                pricing_retrieval_date=estimate.pricing_retrieved,
                pricing_source=estimate.pricing_source,
            )
            return GovernedImageResult(
                images=images,
                request_digest=digest,
                cache_hit=True,
                estimate=estimate,
                spend_record=cache_record,
                usage=cache_metadata.get('usage'),
                request_id=cache_metadata.get('requestId'),
            )
        if ledger.unresolved_for_digest(digest):
            raise DuplicatePossiblyCharged(
                'An identical request is unresolved, possibly charged, or lacks a durable cache; automatic resubmission is denied'
            )
        reservation = ledger.reserve(
            request_digest=digest,
            asset_id=asset_id,
            stage=stage_name,
            model=stage_settings.model,
            quality=stage_settings.quality,
            size=stage_settings.size,
            candidate_count=stage_settings.candidate_count,
            estimated_output_cost_usd=estimate.estimated_output_usd,
            pricing_retrieval_date=estimate.pricing_retrieved,
            pricing_source=estimate.pricing_source,
            lower_bound=estimate.lower_bound,
            budget=budget,
        )
        reservation_id = reservation['reservationId']
        ledger.mark_attempt(reservation_id)
        try:
            response = transport()
        except AmbiguousOpenAIError as exc:
            ledger.possibly_charged(reservation_id, reason=str(exc))
            raise
        except Exception as exc:
            # A provider HTTP response with a deterministic rejection is treated as
            # not charged. Network ambiguity is represented only by the dedicated
            # AmbiguousOpenAIError class above and is never retried automatically.
            ledger.failed_not_charged(reservation_id, reason=type(exc).__name__)
            raise
        actual_cost, cost_status, cost_details = calculate_actual_cost(
            estimate,
            response.usage,
            actual_image_count=len(response.images),
        )
        spend_record = ledger.reconcile(
            reservation_id,
            usage=response.usage,
            actual_cost_usd=actual_cost,
            cost_status=cost_status,
            request_id=response.request_id,
            cost_details=cost_details,
        )
        try:
            _write_cache(workspace_root, digest, response, stage=stage_name, stage_settings=stage_settings)
            spend_record = ledger.mark_cache_stored(reservation_id)
        except Exception as exc:
            # A billed response whose cache cannot be committed must block an
            # identical resubmission; classify it separately from provider failure.
            spend_record = ledger.mark_cache_unavailable(reservation_id, reason=type(exc).__name__)
        return GovernedImageResult(
            images=response.images,
            request_digest=digest,
            cache_hit=False,
            estimate=estimate,
            spend_record=spend_record,
            usage=response.usage,
            request_id=response.request_id,
        )


__all__ = [
    'BudgetExceeded',
    'CacheIntegrityError',
    'ConfirmationRequired',
    'DuplicatePossiblyCharged',
    'GovernedImageResult',
    'LedgerUnavailable',
    'estimate_display_payload',
    'execute_governed_request',
    'request_digest',
]
