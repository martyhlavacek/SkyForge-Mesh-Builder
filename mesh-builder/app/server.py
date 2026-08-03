from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file, session
from PIL import Image, ImageDraw

from common.mesh_math import canonical_frame_calibration, clamp_float, clamp_int, validate_orientation

from .authority_mesh import GENERATOR_ID, GENERATOR_VERSION
from .authority_validation import AuthoritySuitabilityError, require_authority_suitability
from .concept_workflow import (
    build_image_record,
    concepts_root,
    create_concept_run,
    save_generated_image,
    write_run_metadata,
)
from .image_governance import (
    BudgetExceeded,
    ConfirmationRequired,
    DuplicatePossiblyCharged,
    LedgerUnavailable,
    estimate_display_payload,
    execute_governed_request,
)
from .openai_client import (
    AmbiguousOpenAIError,
    OpenAIImageError,
    generate_authority_candidates,
    generate_beauty_candidates,
    load_openai_settings,
    test_openai_connection,
)
from .pipeline import (
    ALLOWED_IMAGE,
    ALLOWED_MESH,
    create_job,
    job_paths,
    load_profiles,
    package_job,
    prune_workspace,
    read_job_status,
    resolve_blender_path,
    save_upload,
    sha256_file,
    start_job_thread,
    write_job_status,
    write_manifest,
)
from .providers import ProviderRequest, resolve_provider
from .settings_store import (
    delete_keychain_key,
    sanitize_and_save_settings,
    save_keychain_key,
    settings_payload,
    test_blender_executable,
)
from .vmp_job_export import (
    JobVmpExportError,
    JobVmpExportRequest,
    export_rendered_job_vmp,
    resolve_import_probe_command,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = PACKAGE_ROOT / 'workspace'
VERSION = '0.7.1'
EXPERIMENTS = {
    'authority_mesh': 'Authority Mesh — local deterministic generation',
    'provider_mesh': 'Provider Mesh — imported provider evaluation',
}


class UnprocessableRequest(ValueError):
    """A syntactically valid request that violates the selected workflow contract."""


def _public_error(value: object, *private_roots: Path) -> str:
    """Return a browser-safe error message with local filesystem paths redacted."""
    message = str(value).strip() or 'Request failed'
    candidates = [str(path.resolve()) for path in private_roots]
    candidates.append(str(Path.home().resolve()))
    for candidate in sorted(set(candidates), key=len, reverse=True):
        if candidate and candidate != '/':
            message = message.replace(candidate, '[LOCAL_PATH]')
    message = re.sub(r'(?<![A-Za-z0-9:])(?:/[A-Za-z0-9._~!$&()*+,;=:@%+-]+)+', '[LOCAL_PATH]', message)
    message = re.sub(r'(?i)\b[A-Z]:\\[^\r\n\t<>"|?*]+', '[LOCAL_PATH]', message)
    return message



def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _beauty_prompt(profile: dict[str, Any], user_prompt: str) -> str:
    return (
        f"Create a single SkyForge spacecraft concept beauty image of exactly one craft in a strict 3/4 front beauty-shot presentation. "
        f"Craft profile: {profile['name']}. Use a slightly elevated fixed camera angle with the ship centered and fully visible inside frame. "
        f"Do not crop any wing, fin, engine, or weapon extremities. Use a moderate lens with no extreme wide-angle distortion and no dramatic perspective exaggeration. "
        f"Use controlled studio-style lighting with one clear consistent light direction so the form is readable, with no heavy rim-light washout, no harsh underlighting, and no deep shadow ambiguity. "
        f"Use a simple dark or neutral background only. Do not include text or UI, and add no cinematic clutter: no smoke, motion blur, lens flare, explosions, starscape clutter, extra vehicles, characters, or environmental props. "
        f"Preserve a clean late-1990s PC-shmup aesthetic inspired by Tyrian, Raptor, and Star Gunner, with readable shapes suitable for a vertical shooter and easy later conversion into a top-down authority view. "
        f"User intent: {user_prompt.strip()}"
    )


def _authority_prompt(profile: dict[str, Any]) -> str:
    return (
        f"Transform the provided approved beauty-shot spacecraft concept into a strict top-down authority render of the exact same craft for SkyForge mesh generation. "
        f"Craft profile: {profile['name']}. This must be the same ship, not a redesign or reinterpretation. Preserve the exact planform identity, silhouette, fuselage, wings, cockpit, engines, weapons, and faction styling from the approved beauty concept. "
        f"Render the craft in a true overhead top-down view using orthographic or near-orthographic presentation, with zero roll and the nose oriented upward in frame. "
        f"Keep the ship centered, fully visible, and surrounded by a small clean margin. Use a plain neutral background only. Use minimal neutral lighting for clear readability with no dramatic shading, no atmospheric effects, no glow, no cast-shadow clutter, no perspective tricks, and no decorative effects. "
        f"Do not include text, UI, extra objects, or background scenery."
    )


def _copy_generated_authority(root: Path, workspace_root: Path, generated_path: str, destination: Path) -> Path:
    concept_base = concepts_root(workspace_root).resolve()
    source = (concept_base / generated_path).resolve() if not generated_path.startswith('/') else Path(generated_path).resolve()
    try:
        source.relative_to(concept_base)
    except ValueError as exc:
        raise ValueError('Selected authority image is outside the concept workspace') from exc
    if not source.is_file():
        raise ValueError('Selected authority image is missing')
    suffix = source.suffix.lower()
    if suffix not in ALLOWED_IMAGE:
        raise ValueError('Selected authority image has an unsupported file type')
    copied = destination / source.name
    shutil.copy2(source, copied)
    return copied


def _validate_asset_id(value: str) -> str:
    asset_id = value.strip() or 'concept.asset'
    if len(asset_id) > 120 or any(character not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-' for character in asset_id):
        raise ValueError('assetId may contain only letters, numbers, dot, underscore and hyphen')
    return asset_id


def _validate_upload_declared(file_storage: Any, allowed: set[str], *, field_name: str) -> None:
    if file_storage is None or not file_storage.filename:
        raise ValueError(f'{field_name} is required')
    suffix = Path(file_storage.filename).suffix.lower()
    if suffix not in allowed:
        raise ValueError(f'{field_name} has an unsupported file type')


def _validate_image_upload_stream(file_storage: Any) -> None:
    _validate_upload_declared(file_storage, ALLOWED_IMAGE, field_name='Authority image')
    try:
        with Image.open(file_storage.stream) as image:
            image.verify()
    except Exception as exc:
        raise ValueError('Authority image is invalid or unreadable') from exc
    finally:
        file_storage.stream.seek(0)


def _validate_uploaded_authority(file_storage: Any, *, certified: bool) -> dict[str, Any]:
    _validate_image_upload_stream(file_storage)
    suffix = Path(file_storage.filename or 'authority.png').suffix.lower() or '.png'
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix) as temporary:
            shutil.copyfileobj(file_storage.stream, temporary)
            temporary.flush()
            report = require_authority_suitability(
                Path(temporary.name),
                source_kind='manual_upload',
                lineage={'certifiedByUser': certified},
            )
    finally:
        file_storage.stream.seek(0)
    return report


def _generated_authority_lineage(
    source: Path,
    *,
    profile_id: str,
    asset_id: str,
) -> dict[str, Any]:
    run_root = source.parent.parent
    concept_base = run_root.parent.resolve()
    metadata_path = run_root / 'metadata.json'
    metadata = _load_json(metadata_path)
    if metadata.get('schemaVersion') != 'skyforge.concept-run.v2':
        raise ValueError('Selected authority is missing governed concept-run metadata')
    if metadata.get('runType') != 'authority' or metadata.get('stage') not in {'authorityDraft', 'authorityFinal'}:
        raise ValueError('Selected concept image is not a governed top-down authority run')
    if metadata.get('runId') != run_root.name:
        raise ValueError('Selected authority run identifier does not match its folder')
    if metadata.get('profileId') != profile_id:
        raise ValueError('Selected authority craft profile does not match the mesh job')
    if metadata.get('assetId') != asset_id:
        raise ValueError('Selected authority asset ID does not match the mesh job')

    authority_records = [
        record
        for record in metadata.get('images', [])
        if isinstance(record, dict) and record.get('filename') == source.name
    ]
    source_hash = sha256_file(source)
    if len(authority_records) != 1:
        raise ValueError('Selected authority must match exactly one governed concept-run record')
    matching = authority_records[0]
    if matching.get('path') != f'images/{source.name}' or matching.get('sha256') != source_hash:
        raise ValueError('Selected authority filename or bytes do not match the governed concept-run record')

    source_beauty = metadata.get('sourceBeauty')
    if not isinstance(source_beauty, dict) or not all(source_beauty.get(key) for key in ('runId', 'filename', 'sha256')):
        raise ValueError('Selected authority is missing its approved beauty lineage')
    beauty_root = (concept_base / str(source_beauty['runId'])).resolve()
    try:
        beauty_root.relative_to(concept_base)
    except ValueError as exc:
        raise ValueError('Approved beauty lineage is outside the concept workspace') from exc
    beauty_metadata = _load_json(beauty_root / 'metadata.json')
    if beauty_metadata.get('schemaVersion') != 'skyforge.concept-run.v2' or beauty_metadata.get('runType') != 'beauty':
        raise ValueError('Approved beauty lineage metadata is missing or invalid')
    if beauty_metadata.get('runId') != beauty_root.name:
        raise ValueError('Approved beauty run identifier does not match its folder')
    if beauty_metadata.get('profileId') != profile_id or beauty_metadata.get('assetId') != asset_id:
        raise ValueError('Approved beauty lineage does not match the authority profile and asset')
    beauty_path = (beauty_root / 'images' / str(source_beauty['filename'])).resolve()
    try:
        beauty_path.relative_to((beauty_root / 'images').resolve())
    except ValueError as exc:
        raise ValueError('Approved beauty lineage filename is invalid') from exc
    beauty_records = [
        record
        for record in beauty_metadata.get('images', [])
        if isinstance(record, dict) and record.get('filename') == beauty_path.name
    ]
    if not beauty_path.is_file():
        raise ValueError('Approved beauty lineage image is missing')
    if len(beauty_records) != 1:
        raise ValueError('Approved beauty lineage must match exactly one governed image record')
    beauty_record = beauty_records[0]
    beauty_hash = sha256_file(beauty_path)
    if beauty_record.get('path') != f'images/{beauty_path.name}' or beauty_record.get('sha256') != beauty_hash:
        raise ValueError('Approved beauty lineage record does not match its image bytes')
    if source_beauty.get('sha256') != beauty_hash:
        raise ValueError('Authority metadata does not match the approved beauty image hash')

    return {
        'verified': True,
        'runId': metadata.get('runId'),
        'stage': metadata.get('stage'),
        'profileId': metadata.get('profileId'),
        'assetId': metadata.get('assetId'),
        'authorityFilename': source.name,
        'authoritySha256': source_hash,
        'sourceBeauty': {
            'runId': beauty_root.name,
            'filename': beauty_path.name,
            'sha256': beauty_hash,
        },
    }


def _resolve_generated_authority(workspace_root: Path, generated_path: str) -> Path:
    concept_base = (workspace_root / '_concepts').resolve()
    source = (concept_base / generated_path).resolve()
    try:
        source.relative_to(concept_base)
    except ValueError as exc:
        raise ValueError('Selected authority image is outside the concept workspace') from exc
    if not source.is_file() or source.suffix.lower() not in ALLOWED_IMAGE:
        raise ValueError('Selected authority image is missing or unsupported')
    return source


def create_app(package_root: Path | None = None, workspace: Path | None = None) -> Flask:
    root = (package_root or PACKAGE_ROOT).resolve()
    workspace_root = (workspace or DEFAULT_WORKSPACE).resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / '_archives').mkdir(parents=True, exist_ok=True)
    (workspace_root / '_vmp').mkdir(parents=True, exist_ok=True)
    concepts_root(workspace_root)

    app = Flask(__name__)
    app.secret_key = os.environ.get('SKYFORGE_SESSION_SECRET') or secrets.token_hex(32)
    app.config.update(
        MAX_CONTENT_LENGTH=250 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Strict',
        PACKAGE_ROOT=root,
        WORKSPACE=workspace_root,
    )

    def csrf_token() -> str:
        token = session.get('csrf_token')
        if not token:
            token = secrets.token_urlsafe(32)
            session['csrf_token'] = token
        return token

    def require_csrf() -> None:
        supplied = request.headers.get('X-SkyForge-CSRF', '')
        expected = session.get('csrf_token', '')
        if not supplied or not expected or not secrets.compare_digest(supplied, expected):
            raise PermissionError('Invalid or missing CSRF token')

    def spend_session_id() -> str:
        value = session.get('spend_session_id')
        if not value:
            value = secrets.token_hex(16)
            session['spend_session_id'] = value
        return str(value)

    @app.get('/')
    def index():
        profiles = load_profiles(root)
        blender = resolve_blender_path(root)
        openai_settings = load_openai_settings(root)
        current_settings = settings_payload(root, str(blender) if blender else None)
        return render_template(
            'index.html',
            profiles=profiles,
            experiments=EXPERIMENTS,
            csrf_token=csrf_token(),
            blender_available=bool(blender),
            version=VERSION,
            today=date.today().isoformat(),
            openai_available=openai_settings.configured,
            openai_model=openai_settings.image_model,
            beauty_count_default=openai_settings.beauty_count_default,
            authority_count_default=openai_settings.authority_count_default,
            current_settings=current_settings,
        )

    @app.get('/api/health')
    def health():
        blender = resolve_blender_path(root)
        openai_settings = load_openai_settings(root)
        return jsonify({
            'ok': True,
            'version': VERSION,
            'blenderAvailable': bool(blender),
            'openaiConfigured': openai_settings.configured,
            'openaiModel': openai_settings.image_model,
        })

    @app.get('/api/openai/health')
    def openai_health():
        settings = load_openai_settings(root)
        return jsonify({
            'ok': True,
            'configured': settings.configured,
            'stages': {
                name: {
                    'model': stage.model,
                    'quality': stage.quality,
                    'size': stage.size,
                    'candidateCount': stage.candidate_count,
                }
                for name, stage in settings.stages.items()
            },
        })

    @app.get('/api/settings')
    def get_settings():
        blender = resolve_blender_path(root)
        return jsonify({'ok': True, 'settings': settings_payload(root, str(blender) if blender else None)})

    @app.post('/api/settings')
    def save_settings_route():
        try:
            require_csrf()
            payload = request.get_json(silent=True) or {}
            openai_payload = payload.get('openai') if isinstance(payload.get('openai'), dict) else {}
            blender_payload = payload.get('blender') if isinstance(payload.get('blender'), dict) else {}
            api_key = str(openai_payload.get('apiKey') or '').strip()
            remove_key = bool(openai_payload.get('removeApiKey'))
            if remove_key and api_key:
                raise ValueError('Choose either a replacement API key or removal, not both')
            if remove_key:
                delete_keychain_key()
            elif api_key:
                save_keychain_key(api_key)
            sanitize_and_save_settings(
                root,
                blender_path=str(blender_payload.get('path') or ''),
                stages=openai_payload.get('stages') if isinstance(openai_payload.get('stages'), dict) else {},
                budget=openai_payload.get('budget') if isinstance(openai_payload.get('budget'), dict) else {},
            )
            if remove_key:
                message = 'Settings saved and the OpenAI API key was removed from macOS Keychain.'
            elif api_key:
                message = 'Settings saved and the OpenAI API key was stored in macOS Keychain.'
            else:
                message = 'Settings saved. The existing API key was left unchanged.'
            return jsonify({'ok': True, 'message': message, 'settings': settings_payload(root, str(resolve_blender_path(root)) if resolve_blender_path(root) else None)})
        except PermissionError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 403
        except (ValueError, RuntimeError) as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 400
        except Exception:
            app.logger.exception('Settings save failed')
            return jsonify({'ok': False, 'error': 'Settings save failed. Check the server log.'}), 500

    @app.post('/api/settings/test-openai')
    def test_openai_route():
        try:
            require_csrf()
            payload = request.get_json(silent=True) or {}
            supplied_key = str(payload.get('apiKey') or '').strip()
            if supplied_key:
                key = supplied_key
            else:
                configured = load_openai_settings(root)
                key = configured.api_key or ''
            return jsonify(test_openai_connection(key))
        except PermissionError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 403
        except (ValueError, OpenAIImageError) as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 400
        except Exception:
            app.logger.exception('OpenAI connection test failed')
            return jsonify({'ok': False, 'error': 'OpenAI connection test failed. Check the server log.'}), 500

    @app.post('/api/settings/test-blender')
    def test_blender_route():
        try:
            require_csrf()
            payload = request.get_json(silent=True) or {}
            requested_path = str(payload.get('path') or '').strip()
            if not requested_path:
                detected = resolve_blender_path(root)
                requested_path = str(detected) if detected else ''
            return jsonify(test_blender_executable(requested_path))
        except PermissionError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 403
        except (ValueError, RuntimeError) as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 400
        except Exception:
            app.logger.exception('Blender connection test failed')
            return jsonify({'ok': False, 'error': 'Blender connection test failed. Check the server log.'}), 500

    @app.post('/api/concepts/estimate')
    def concept_estimate():
        try:
            require_csrf()
            payload = request.get_json(silent=True) or {}
            settings = load_openai_settings(root)
            stage_name = str(payload.get('stage') or '').strip()
            if stage_name not in settings.stages:
                raise ValueError('Unknown governed image stage')
            asset_id = _validate_asset_id(str(payload.get('assetId') or 'concept.asset'))
            reference_count = 1 if stage_name.startswith('authority') else 0
            estimate = estimate_display_payload(
                workspace_root=workspace_root,
                session_id=spend_session_id(),
                asset_id=asset_id,
                stage_name=stage_name,
                stage_settings=settings.stage(stage_name),
                reference_image_count=reference_count,
                budget=settings.budget,
            )
            return jsonify({'ok': True, **estimate})
        except PermissionError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 403
        except (ValueError, BudgetExceeded, LedgerUnavailable) as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 400

    @app.post('/api/concepts/beauty')
    def concept_beauty():
        try:
            require_csrf()
            settings = load_openai_settings(root)
            if not settings.configured:
                raise OpenAIImageError('OpenAI image generation is not configured. Save the API key in Settings first.')
            stage_name = request.form.get('stage', 'beautyExplore').strip()
            if stage_name not in {'beautyExplore', 'beautyRefine'}:
                raise ValueError('Beauty stage must be beautyExplore or beautyRefine')
            stage = settings.stage(stage_name)
            profiles = load_profiles(root)
            profile_id = request.form.get('profileId', '').strip()
            profile = next((item for item in profiles if item.get('id') == profile_id), None)
            if profile is None:
                raise ValueError('Unknown craft profile')
            asset_id = _validate_asset_id(request.form.get('assetId', ''))
            user_prompt = request.form.get('userPrompt', '').strip()
            if not user_prompt:
                raise ValueError('Beauty prompt is required')
            if len(user_prompt) > 6000:
                raise ValueError('Beauty prompt is too long')
            resolved_prompt = _beauty_prompt(profile, user_prompt)
            result = execute_governed_request(
                workspace_root=workspace_root,
                session_id=spend_session_id(),
                asset_id=asset_id,
                stage_name=stage_name,
                stage_settings=stage,
                budget=settings.budget,
                resolved_prompt=resolved_prompt,
                reference_image_sha256=None,
                confirmed=request.form.get('costConfirmed') == 'true',
                transport=lambda: generate_beauty_candidates(
                    settings,
                    prompt=resolved_prompt,
                    model=stage.model,
                    quality=stage.quality,
                    size=stage.size,
                    count=stage.candidate_count,
                ),
            )
            run_root = create_concept_run(workspace_root, kind='beauty', profile_id=profile_id, asset_id=asset_id)
            images = []
            for index, image in enumerate(result.images, start=1):
                path = save_generated_image(run_root, 'beauty', index, image.bytes_data)
                images.append(build_image_record(run_root, path, f'Beauty {index}', {'source': image.source}))
            metadata = {
                'schemaVersion': 'skyforge.concept-run.v2',
                'runType': 'beauty',
                'stage': stage_name,
                'runId': run_root.name,
                'profileId': profile_id,
                'assetId': asset_id,
                'openai': {
                    'model': stage.model,
                    'quality': stage.quality,
                    'size': stage.size,
                    'candidateCount': stage.candidate_count,
                    'requestDigest': result.request_digest,
                    'requestId': result.request_id,
                    'cacheHit': result.cache_hit,
                    'usage': result.usage,
                    'estimate': result.estimate.to_dict(),
                    'spend': result.spend_record,
                },
                'userPrompt': user_prompt,
                'resolvedPrompt': resolved_prompt,
                'createdAt': date.today().isoformat(),
                'images': images,
            }
            write_run_metadata(run_root, metadata)
            return jsonify({
                'ok': True,
                'runId': run_root.name,
                'images': images,
                'metadata': metadata,
                'cost': {
                    'estimatedOutputUsd': result.estimate.to_dict()['estimatedOutputUsd'],
                    'cacheHit': result.cache_hit,
                    'cumulativeAssetSpendUsd': result.spend_record['cumulativeAssetSpendUsd'],
                    'cumulativeSessionSpendUsd': result.spend_record['cumulativeSessionSpendUsd'],
                },
            })
        except PermissionError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 403
        except (BudgetExceeded, LedgerUnavailable, ConfirmationRequired) as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 402
        except DuplicatePossiblyCharged as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 409
        except AmbiguousOpenAIError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 502
        except (ValueError, OpenAIImageError) as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 400
        except Exception:
            app.logger.exception('Beauty generation failed')
            return jsonify({'ok': False, 'error': 'Beauty generation failed. Check the server log.'}), 500

    @app.post('/api/concepts/authority')
    def concept_authority():
        try:
            require_csrf()
            settings = load_openai_settings(root)
            if not settings.configured:
                raise OpenAIImageError('OpenAI image generation is not configured. Save the API key in Settings first.')
            stage_name = request.form.get('stage', 'authorityDraft').strip()
            if stage_name not in {'authorityDraft', 'authorityFinal'}:
                raise ValueError('Authority stage must be authorityDraft or authorityFinal')
            stage = settings.stage(stage_name)
            profiles = load_profiles(root)
            profile_id = request.form.get('profileId', '').strip()
            profile = next((item for item in profiles if item.get('id') == profile_id), None)
            if profile is None:
                raise ValueError('Unknown craft profile')
            asset_id = _validate_asset_id(request.form.get('assetId', ''))
            beauty_run_id = request.form.get('beautyRunId', '').strip()
            beauty_filename = request.form.get('beautyFilename', '').strip()
            if not beauty_run_id or not beauty_filename:
                raise ValueError('An approved beauty concept must be selected first')
            beauty_base = (workspace_root / '_concepts').resolve()
            beauty_root = (beauty_base / beauty_run_id).resolve()
            try:
                beauty_root.relative_to(beauty_base)
            except ValueError as exc:
                raise ValueError('Selected beauty concept is outside the concept workspace') from exc
            beauty_path = (beauty_root / 'images' / beauty_filename).resolve()
            try:
                beauty_path.relative_to(beauty_root / 'images')
            except ValueError as exc:
                raise ValueError('Selected beauty filename is invalid') from exc
            if not beauty_path.is_file() or beauty_path.suffix.lower() not in ALLOWED_IMAGE:
                raise ValueError('Selected beauty concept is missing or unsupported')
            reference_sha = sha256_file(beauty_path)
            resolved_prompt = _authority_prompt(profile)
            result = execute_governed_request(
                workspace_root=workspace_root,
                session_id=spend_session_id(),
                asset_id=asset_id,
                stage_name=stage_name,
                stage_settings=stage,
                budget=settings.budget,
                resolved_prompt=resolved_prompt,
                reference_image_sha256=reference_sha,
                confirmed=request.form.get('costConfirmed') == 'true',
                transport=lambda: generate_authority_candidates(
                    settings,
                    prompt=resolved_prompt,
                    reference_image=beauty_path,
                    model=stage.model,
                    quality=stage.quality,
                    size=stage.size,
                    count=stage.candidate_count,
                ),
            )
            run_root = create_concept_run(workspace_root, kind='authority', profile_id=profile_id, asset_id=asset_id)
            images = []
            for index, image in enumerate(result.images, start=1):
                path = save_generated_image(run_root, 'authority', index, image.bytes_data)
                images.append(build_image_record(run_root, path, f'Authority {index}', {'source': image.source}))
            metadata = {
                'schemaVersion': 'skyforge.concept-run.v2',
                'runType': 'authority',
                'stage': stage_name,
                'runId': run_root.name,
                'profileId': profile_id,
                'assetId': asset_id,
                'openai': {
                    'model': stage.model,
                    'quality': stage.quality,
                    'size': stage.size,
                    'candidateCount': stage.candidate_count,
                    'background': 'auto',
                    'transparentBackgroundClaimed': False,
                    'requestDigest': result.request_digest,
                    'requestId': result.request_id,
                    'cacheHit': result.cache_hit,
                    'usage': result.usage,
                    'estimate': result.estimate.to_dict(),
                    'spend': result.spend_record,
                },
                'sourceBeauty': {'runId': beauty_run_id, 'filename': beauty_filename, 'sha256': reference_sha},
                'resolvedPrompt': resolved_prompt,
                'createdAt': date.today().isoformat(),
                'images': images,
            }
            write_run_metadata(run_root, metadata)
            return jsonify({
                'ok': True,
                'runId': run_root.name,
                'images': images,
                'metadata': metadata,
                'cost': {
                    'estimatedOutputUsd': result.estimate.to_dict()['estimatedOutputUsd'],
                    'lowerBound': True,
                    'cacheHit': result.cache_hit,
                    'cumulativeAssetSpendUsd': result.spend_record['cumulativeAssetSpendUsd'],
                    'cumulativeSessionSpendUsd': result.spend_record['cumulativeSessionSpendUsd'],
                },
            })
        except PermissionError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 403
        except (BudgetExceeded, LedgerUnavailable, ConfirmationRequired) as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 402
        except DuplicatePossiblyCharged as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 409
        except AmbiguousOpenAIError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 502
        except (ValueError, OpenAIImageError) as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 400
        except Exception:
            app.logger.exception('Authority generation failed')
            return jsonify({'ok': False, 'error': 'Authority generation failed. Check the server log.'}), 500

    @app.get('/api/concepts/files/<run_id>/<filename>')
    def concept_file(run_id: str, filename: str):
        base = concepts_root(workspace_root).resolve()
        run_root = (base / run_id).resolve()
        try:
            run_root.relative_to(base)
        except ValueError:
            return jsonify({'ok': False, 'error': 'Run not found'}), 404
        path = (run_root / 'images' / filename).resolve()
        try:
            path.relative_to(run_root / 'images')
        except ValueError:
            return jsonify({'ok': False, 'error': 'Image not found'}), 404
        if not path.is_file():
            return jsonify({'ok': False, 'error': 'Image not found'}), 404
        return send_file(path)

    @app.post('/api/authority/validate')
    def validate_authority_upload():
        try:
            require_csrf()
            profiles = load_profiles(root)
            profile_id = request.form.get('profileId', '').strip()
            if not any(item.get('id') == profile_id for item in profiles):
                raise ValueError('Unknown craft profile')
            certified = request.form.get('manualAuthorityCertified') == 'on'
            report = _validate_uploaded_authority(
                request.files.get('authority'),
                certified=certified,
            )
            return jsonify({
                'ok': True,
                'passed': True,
                'certificationRequired': not certified,
                'report': report,
            })
        except PermissionError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 403
        except AuthoritySuitabilityError as exc:
            return jsonify({
                'ok': False,
                'passed': False,
                'error': _public_error(exc, root, workspace_root),
                'report': exc.report,
            }), 422
        except ValueError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 400

    @app.post('/api/jobs')
    def jobs():
        try:
            require_csrf()
            profiles = load_profiles(root)
            profile_id = request.form.get('profileId', '')
            profile = next((item for item in profiles if item.get('id') == profile_id), None)
            if profile is None:
                raise ValueError(f'Unknown craft profile: {profile_id or "missing"}')
            asset_id = request.form.get('assetId', '').strip()
            if not asset_id:
                raise ValueError('assetId is required')
            experiment_id = request.form.get('experiment', '').strip()
            if experiment_id not in EXPERIMENTS:
                raise ValueError(f'Unknown experiment: {experiment_id or "missing"}')

            if experiment_id == 'authority_mesh':
                forward_axis, up_axis = '+Y', '+Z'
            else:
                forward_axis, up_axis = validate_orientation(
                    request.form.get('forwardAxis', '+Y'),
                    request.form.get('upAxis', '+Z'),
                )
            maximum_profile_scale = max(float(item['scale']) for item in profiles)
            profile_path = root / 'profiles' / 'craft_profiles.json'
            frame_calibration = canonical_frame_calibration(
                maximum_profile_scale, len(profiles), sha256_file(profile_path)
            )
            settings = {
                'bankDegrees': clamp_float(request.form.get('bankDegrees', '18'), 0, 35, 'bankDegrees'),
                'masterResolution': clamp_int(
                    request.form.get('masterResolution', '384'), 256, 512, 'masterResolution'
                ),
                'cameraPitchDegrees': clamp_float(
                    request.form.get('cameraPitchDegrees', '20'), 0, 45, 'cameraPitchDegrees'
                ),
                'forwardAxis': forward_axis,
                'upAxis': up_axis,
                'profileScale': float(profile['scale']),
                'canonicalOrthoScale': frame_calibration['canonicalOrthoScale'],
                'canonicalFrameCalibration': frame_calibration,
                'renderSamples': 64,
                'destruction': {
                    'requested': False,
                    'implemented': False,
                    'reason': 'Deferred until object-boundary eligibility is measured; no UI control is exposed in v0.7.1.',
                },
            }
            if experiment_id == 'authority_mesh':
                distribution_approved = request.form.get('approveForSpriteFoundry') == 'on'
                commercial_use_asserted = request.form.get('assetCommercialUseAsserted') == 'on'
                authority_permission = request.form.get('authorityRedistributionPermission', 'unknown').strip()
                authority_terms_basis = request.form.get('authorityTermsBasis', '').strip()
                asset_version = request.form.get('assetVersion', '').strip()
                if distribution_approved:
                    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', asset_version):
                        raise ValueError('VMP assetVersion must use numeric semantic version form, for example 1.0.0')
                    if authority_permission not in {'permitted', 'unknown', 'prohibited'}:
                        raise ValueError('Authority redistribution permission is invalid')
                    if not authority_terms_basis:
                        raise ValueError('Authority terms basis is required for Sprite Foundry distribution')
                    if not commercial_use_asserted:
                        raise ValueError('Commercial-use assertion is required for Sprite Foundry distribution')
                generator = {
                    'provider': 'SkyForge Authority Two-Sided Field',
                    'providerVersion': GENERATOR_VERSION,
                    'generatorId': GENERATOR_ID,
                    'license': 'Project SkyForge internal deterministic generator',
                    'licenseUrl': None,
                    'retrievedDate': date.today().isoformat(),
                    'approvedForDistribution': distribution_approved,
                }
                vmp_export_policy = {
                    'assetVersion': asset_version or '1.0.0',
                    'assetRole': 'air_moving',
                    'providerId': 'local_deterministic',
                    'authorityRedistributionPermission': authority_permission,
                    'authorityTermsBasis': authority_terms_basis,
                    'assetCommercialUseAsserted': commercial_use_asserted,
                    'approvalScope': 'current_rendered_artifact_only',
                }
            else:
                vmp_export_policy = None
                retrieved_date = request.form.get('retrievedDate', '').strip() or date.today().isoformat()
                try:
                    date.fromisoformat(retrieved_date)
                except ValueError as exc:
                    raise ValueError('Generator retrievedDate must use YYYY-MM-DD') from exc
                generator = {
                    'provider': request.form.get('provider', '').strip(),
                    'providerVersion': request.form.get('providerVersion', '').strip(),
                    'license': request.form.get('license', '').strip(),
                    'licenseUrl': request.form.get('licenseUrl', '').strip() or None,
                    'retrievedDate': retrieved_date,
                    'approvedForDistribution': request.form.get('approvedForDistribution') == 'on',
                }
                for field in ('provider', 'providerVersion', 'license'):
                    if not generator[field]:
                        raise ValueError(f'Generator {field} is required')

            # Validate every deterministic request rule before allocating a job directory.
            selected_authority = request.form.get('authorityGeneratedPath', '').strip()
            selected_authority_source = None
            authority_validation: dict[str, Any]
            if selected_authority:
                selected_authority_source = _resolve_generated_authority(workspace_root, selected_authority)
                lineage = _generated_authority_lineage(
                    selected_authority_source,
                    profile_id=profile_id,
                    asset_id=asset_id,
                )
                authority_validation = require_authority_suitability(
                    selected_authority_source,
                    source_kind='governed_generated',
                    lineage=lineage,
                )
            else:
                if request.form.get('manualAuthorityCertified') != 'on':
                    raise UnprocessableRequest(
                        'Confirm that the manual upload is a strict top-down authority before validation'
                    )
                authority_validation = _validate_uploaded_authority(
                    request.files.get('authority'), certified=True
                )
            mesh_upload = request.files.get('mesh')
            if experiment_id == 'authority_mesh' and mesh_upload and mesh_upload.filename:
                raise UnprocessableRequest('Authority Mesh mode generates its own mesh; remove the mesh upload')
            if experiment_id == 'provider_mesh':
                try:
                    _validate_upload_declared(mesh_upload, ALLOWED_MESH, field_name='Provider mesh')
                except ValueError as exc:
                    raise UnprocessableRequest(_public_error(exc, root, workspace_root)) from exc

            prune_workspace(workspace_root)
            job = create_job(workspace_root, profile, asset_id)
            try:
                if selected_authority_source is not None:
                    authority = job.source / selected_authority_source.name
                    shutil.copy2(selected_authority_source, authority)
                else:
                    authority = save_upload(
                        request.files.get('authority'), job.source, ALLOWED_IMAGE, validate_image=True
                    )
                authority_validation_path = job.source / 'authority_suitability_report.json'
                _write_json(authority_validation_path, authority_validation)
                generation_report = None
                if experiment_id == 'authority_mesh':
                    provider = resolve_provider('local_deterministic')
                    capture = provider.execute(ProviderRequest(
                        request_id=job.root.name,
                        operation='authority_to_mesh',
                        asset_id=asset_id,
                        asset_role='air_moving',
                        authority_path=authority,
                        output_dir=job.source / 'generated',
                    ))
                    mesh = capture.mesh_path
                    generation_report = capture.report_path
                    mesh_origin = 'generated_from_authority'
                    for evidence in (*capture.preview_paths, capture.report_path):
                        shutil.copy2(evidence, job.output / evidence.name)
                    shutil.copy2(job.source / 'generated' / 'provider_events.jsonl', job.logs / 'provider_events.jsonl')
                else:
                    mesh = save_upload(mesh_upload, job.source, ALLOWED_MESH)
                    mesh_origin = 'uploaded_provider'
                    placeholder = {
                        'schemaVersion': 'skyforge.authority-mesh-generation.v1',
                        'mode': 'uploaded_provider',
                        'gateResults': {'passed': True, 'checks': {'providerMeshUploaded': True}},
                    }
                    (job.output / 'authority_mesh_generation_report.json').write_text(
                        json.dumps(placeholder, indent=2), encoding='utf-8'
                    )
                    sample = Image.new('RGBA', (384, 384), (24, 29, 36, 255))
                    draw = ImageDraw.Draw(sample)
                    draw.text(
                        (24, 180),
                        'Provider mesh uploaded; local authority field not used.',
                        fill=(240, 244, 248, 255),
                    )
                    for name in (
                        'authority_mesh_generation_contact_sheet.png',
                        'authority_mesh_preview_top.png',
                        'authority_mesh_preview_bank_left.png',
                        'authority_mesh_preview_bank_right.png',
                        'authority_mesh_glb_silhouette.png',
                        'authority_mesh_blender_import_silhouette.png',
                    ):
                        sample.save(job.output / name)
                manifest = write_manifest(
                    job,
                    profile,
                    asset_id,
                    authority,
                    mesh,
                    mesh_origin,
                    generation_report,
                    experiment_id,
                    EXPERIMENTS[experiment_id],
                    settings,
                    generator,
                    authority_validation_path,
                )
                # Append concept workflow provenance if the user selected generated concept imagery.
                concept_provenance = {
                    'selectedAuthorityGeneratedPath': selected_authority or None,
                    'beautyRunId': request.form.get('beautyRunId', '').strip() or None,
                    'beautyFilename': request.form.get('beautyFilename', '').strip() or None,
                    'authorityRunId': request.form.get('authorityRunId', '').strip() or None,
                    'authorityFilename': request.form.get('authorityFilename', '').strip() or None,
                    'conceptPrompt': request.form.get('conceptPrompt', '').strip() or None,
                }
                if any(concept_provenance.values()) or vmp_export_policy is not None:
                    payload = _load_json(manifest)
                    if any(concept_provenance.values()):
                        payload['conceptWorkflow'] = concept_provenance
                    if vmp_export_policy is not None:
                        payload['vmpExportPolicy'] = vmp_export_policy
                    _write_json(manifest, payload)
                write_job_status(job, 'prepared', manifest='manifest.json', experiment=experiment_id)
            except Exception as exc:
                error_message = _public_error(exc, root, workspace_root)
                shutil.rmtree(job.root, ignore_errors=True)
                return jsonify({'ok': False, 'error': error_message}), 422

            blender = resolve_blender_path(root)
            if blender:
                status = 'queued'
                write_job_status(job, status)
                start_job_thread(root, job, manifest, blender)
            else:
                status = 'prepared'

            return jsonify({
                'ok': True,
                'status': status,
                'jobId': job.root.name,
                'statusUrl': f'/api/jobs/{job.root.name}',
                'download': f'/api/jobs/{job.root.name}/download',
                'warning': None if blender else 'Blender is not configured. The job was prepared but not rendered.',
            }), 202 if blender else 201
        except PermissionError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 403
        except (UnprocessableRequest, AuthoritySuitabilityError) as exc:
            payload = {'ok': False, 'error': _public_error(exc, root, workspace_root)}
            if isinstance(exc, AuthoritySuitabilityError):
                payload['authoritySuitability'] = exc.report
            return jsonify(payload), 422
        except ValueError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 400
        except Exception:
            app.logger.exception('Job creation failed')
            return jsonify({'ok': False, 'error': 'Internal job creation failure. Check the server log.'}), 500

    @app.get('/api/jobs/<job_id>')
    def job_status(job_id: str):
        job = job_paths(workspace_root, job_id)
        if job is None:
            return jsonify({'ok': False, 'error': 'Job not found'}), 404
        payload = read_job_status(job)
        manifest = _load_json(job.root / 'manifest.json')
        policy = manifest.get('vmpExportPolicy') if isinstance(manifest.get('vmpExportPolicy'), dict) else {}
        experiment_id = (manifest.get('experiment') or {}).get('id')
        provider_label = (
            'Local deterministic — zero provider cost'
            if experiment_id == 'authority_mesh'
            else 'Uploaded provider mesh — evaluation only'
        )
        probe_configured = resolve_import_probe_command(root) is not None
        vmp_record = payload.get('vmp') if isinstance(payload.get('vmp'), dict) else {}
        vmp_ready = bool(
            vmp_record.get('probeAccepted') is True
            and isinstance(vmp_record.get('archiveName'), str)
            and (workspace_root / '_vmp' / vmp_record['archiveName']).is_file()
        )
        eligible = bool(
            payload.get('status') == 'rendered'
            and experiment_id == 'authority_mesh'
            and (manifest.get('distributionGate') or {}).get('approved') is True
            and policy.get('assetRole') == 'air_moving'
            and probe_configured
        )
        error = _public_error(payload.get('error') or '', root, workspace_root) if payload.get('error') else ''
        public_payload = {
            key: payload[key]
            for key in ('schemaVersion', 'status', 'assetId', 'profileId', 'createdAt', 'updatedAt', 'renderedAt', 'experiment', 'verification')
            if key in payload
        }
        public_payload.update({
            'ok': payload.get('status') != 'failed',
            'jobId': job_id,
            'error': error or None,
            'providerLabel': provider_label,
            'assetRole': 'air_moving',
            'assetRoleLabel': 'Airborne — moving',
            'collisionAuthority': 'non_authoritative_hint_only',
            'downloadReady': payload.get('status') == 'rendered',
            'download': f'/api/jobs/{job_id}/download' if payload.get('status') == 'rendered' else None,
            'vmpEligible': eligible,
            'vmpProbeConfigured': probe_configured,
            'vmpReady': vmp_ready,
            'vmp': ({
                'packageId': vmp_record.get('packageId'),
                'packageContentDigest': vmp_record.get('packageContentDigest'),
                'archiveSha256': vmp_record.get('archiveSha256'),
                'probeAccepted': vmp_record.get('probeAccepted'),
                'authorityReverification': vmp_record.get('authorityReverification'),
                'download': f'/api/jobs/{job_id}/vmp/download',
            } if vmp_ready else None),
        })
        return jsonify(public_payload)

    @app.post('/api/jobs/<job_id>/vmp')
    def export_vmp(job_id: str):
        try:
            require_csrf()
            job = job_paths(workspace_root, job_id)
            if job is None:
                return jsonify({'ok': False, 'error': 'Job not found'}), 404
            body = request.get_json(silent=True) or {}
            if body.get('approveCurrentArtifact') is not True:
                raise ValueError('Explicit approval of the current rendered artifact is required')
            manifest = _load_json(job.root / 'manifest.json')
            policy = manifest.get('vmpExportPolicy')
            if not isinstance(policy, dict):
                raise ValueError('This job has no VMP export policy')
            command = resolve_import_probe_command(root)
            if command is None:
                raise ValueError('Independent Sprite Foundry Import Probe is not configured')
            export_request = JobVmpExportRequest(
                asset_version=str(policy.get('assetVersion') or ''),
                authority_redistribution_permission=str(
                    policy.get('authorityRedistributionPermission') or ''
                ),
                authority_terms_basis=str(policy.get('authorityTermsBasis') or ''),
                asset_commercial_use_asserted=policy.get('assetCommercialUseAsserted') is True,
            )
            vmp_dir = workspace_root / '_vmp'
            vmp_dir.mkdir(parents=True, exist_ok=True)
            archive = vmp_dir / f'{job.root.name}.sfmeshpack'
            result = export_rendered_job_vmp(
                root, job, export_request, archive, import_probe_command=command
            )
            current = read_job_status(job)
            rendered_at = current.get('renderedAt') or current.get('updatedAt')
            record = {
                'archiveName': archive.name,
                'receiptName': result.receipt_path.name,
                'packageId': result.build.package_id,
                'packageContentDigest': result.build.package_content_digest,
                'archiveSha256': result.build.archive_sha256,
                'probeAccepted': True,
                'authorityReverification': result.receipt.get('authorityReverification'),
                'importerVersion': result.receipt.get('importerVersion'),
                'receiptId': result.receipt.get('receiptId'),
            }
            write_job_status(job, 'rendered', renderedAt=rendered_at, vmp=record)
            return jsonify({
                'ok': True,
                'jobId': job_id,
                'packageId': result.build.package_id,
                'packageContentDigest': result.build.package_content_digest,
                'archiveSha256': result.build.archive_sha256,
                'probeAccepted': True,
                'authorityReverification': result.receipt.get('authorityReverification'),
                'download': f'/api/jobs/{job_id}/vmp/download',
            })
        except PermissionError as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 403
        except (ValueError, JobVmpExportError) as exc:
            return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)}), 409
        except Exception:
            app.logger.exception('VMP export failed')
            return jsonify({'ok': False, 'error': 'VMP export failed. Check the server log.'}), 500

    @app.get('/api/jobs/<job_id>/vmp/download')
    def download_vmp(job_id: str):
        job = job_paths(workspace_root, job_id)
        if job is None:
            return jsonify({'ok': False, 'error': 'Job not found'}), 404
        record = read_job_status(job).get('vmp')
        if not isinstance(record, dict) or record.get('probeAccepted') is not True:
            return jsonify({'ok': False, 'error': 'No independently accepted VMP is available'}), 409
        expected_name = f'{job.root.name}.sfmeshpack'
        if record.get('archiveName') != expected_name:
            return jsonify({'ok': False, 'error': 'VMP record is invalid'}), 409
        archive = (workspace_root / '_vmp' / expected_name).resolve()
        try:
            archive.relative_to((workspace_root / '_vmp').resolve())
        except ValueError:
            return jsonify({'ok': False, 'error': 'VMP record is invalid'}), 409
        if not archive.is_file() or sha256_file(archive) != record.get('archiveSha256'):
            return jsonify({'ok': False, 'error': 'VMP archive failed identity verification'}), 409
        return send_file(archive, as_attachment=True, download_name=archive.name)

    @app.get('/api/jobs/<job_id>/download')
    def download(job_id: str):
        job = job_paths(workspace_root, job_id)
        if job is None:
            return jsonify({'ok': False, 'error': 'Job not found'}), 404
        if read_job_status(job).get('status') != 'rendered':
            return jsonify({'ok': False, 'error': 'Job is not rendered and verified'}), 409
        try:
            archive = package_job(job, workspace_root / '_archives')
        except RuntimeError:
            app.logger.exception('Verified job package is unavailable')
            return jsonify({'ok': False, 'error': 'Verified package is unavailable'}), 409
        return send_file(archive, as_attachment=True, download_name=archive.name)

    return app


app = create_app()

if __name__ == '__main__':
    app.run('127.0.0.1', int(os.environ.get('PORT', '5179')), debug=False, threaded=True)
