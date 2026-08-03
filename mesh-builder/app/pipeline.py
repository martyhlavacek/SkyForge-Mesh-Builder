from __future__ import annotations

import atexit
import hashlib
import json
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageStat

from common.mesh_math import is_valid_job_id

ALLOWED_MESH = {'.glb', '.gltf', '.obj', '.fbx'}
ALLOWED_IMAGE = {'.png', '.jpg', '.jpeg', '.webp'}
MAX_IMAGE_DIMENSION = 8192
MIN_IMAGE_DIMENSION = 32
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
OPAQUE_BG_DISTANCE_THRESHOLD = 28
REVIEW_SIZES = (96, 64)
FIT_CANVAS_SIZE = 512
FIT_CANVAS_MARGIN = 28

RENDER_REQUIRED_OUTPUTS = [
    'normalized.blend',
    'normalized.glb',
    'preview_neutral_master.png',
    'preview_bank_left_master.png',
    'preview_bank_right_master.png',
    'silhouette_top_master.png',
    'asset.json',
    'run_report.json',
]

GENERATION_REQUIRED_OUTPUTS = [
    'authority_mesh_generation_report.json',
    'authority_mesh_generation_contact_sheet.png',
    'authority_mesh_preview_top.png',
    'authority_mesh_preview_bank_left.png',
    'authority_mesh_preview_bank_right.png',
    'authority_mesh_glb_silhouette.png',
    'authority_mesh_blender_import_silhouette.png',
]

POSTPROCESS_REQUIRED_OUTPUTS = [
    'preview_neutral_96_lanczos.png',
    'preview_bank_left_96_lanczos.png',
    'preview_bank_right_96_lanczos.png',
    'preview_neutral_64_lanczos.png',
    'preview_bank_left_64_lanczos.png',
    'preview_bank_right_64_lanczos.png',
    'preview_neutral_96_nearest.png',
    'preview_bank_left_96_nearest.png',
    'preview_bank_right_96_nearest.png',
    'preview_neutral_64_nearest.png',
    'preview_bank_left_64_nearest.png',
    'preview_bank_right_64_nearest.png',
    'review_sheet_neutral_96.png',
    'review_sheet_neutral_64.png',
    'review_sheet_terrain_proxy_96.png',
    'review_sheet_terrain_proxy_64.png',
    'authority_mask.png',
    'silhouette_comparison.png',
    'review.json',
]

_STATUS_LOCK = threading.RLock()
_JOB_SEMAPHORE = threading.BoundedSemaphore(1)
_ACTIVE_PROCESSES: dict[str, subprocess.Popen[str]] = {}
_ACTIVE_PROCESSES_LOCK = threading.RLock()


@dataclass(frozen=True)
class JobPaths:
    root: Path
    source: Path
    output: Path
    logs: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(name: str) -> str:
    leaf = Path(name.replace('\\', '/')).name
    cleaned = ''.join(character if character.isalnum() or character in '._-' else '_' for character in leaf)
    cleaned = cleaned.lstrip('.')
    return cleaned[:120] or 'asset'


def load_profiles(package_root: Path) -> list[dict[str, Any]]:
    path = package_root / 'profiles' / 'craft_profiles.json'
    profiles = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(profiles, list) or not profiles:
        raise RuntimeError('No craft profiles are configured')
    return profiles


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding='utf-8')
    temp.replace(path)


def create_job(workspace: Path, profile: dict[str, Any], asset_id: str) -> JobPaths:
    job_id = f"{safe_name(asset_id)}-{uuid.uuid4().hex[:8]}"
    root = workspace / job_id
    source, output, logs = root / 'source', root / 'output', root / 'logs'
    for path in (source, output, logs):
        path.mkdir(parents=True, exist_ok=False)
    job = JobPaths(root, source, output, logs)
    write_job_status(job, 'created')
    payload = read_job_status(job)
    payload.update({
        'schemaVersion': 'skyforge.mesh-job.v3.0',
        'jobId': job_id,
        'assetId': asset_id,
        'profileId': profile['id'],
        'createdAt': utc_now(),
    })
    _write_json(root / 'job.json', payload)
    return job


def job_paths(workspace: Path, job_id: str) -> JobPaths | None:
    if not is_valid_job_id(job_id):
        return None
    base = workspace.resolve()
    root = (workspace / job_id).resolve()
    try:
        root.relative_to(base)
    except ValueError:
        return None
    if not root.is_dir():
        return None
    return JobPaths(root, root / 'source', root / 'output', root / 'logs')


def read_job_status(job: JobPaths) -> dict[str, Any]:
    path = job.root / 'job.json'
    if not path.exists():
        return {'status': 'unknown'}
    return json.loads(path.read_text(encoding='utf-8'))


def write_job_status(job: JobPaths, status: str, *, error: str | None = None, **extra: Any) -> None:
    with _STATUS_LOCK:
        current = read_job_status(job)
        now = utc_now()
        current['status'] = status
        current['updatedAt'] = now
        if status == 'rendered' and 'renderedAt' not in current:
            current['renderedAt'] = now
        if error:
            current['error'] = error
        else:
            current.pop('error', None)
        current.update(extra)
        _write_json(job.root / 'job.json', current)


def _validate_image(path: Path) -> None:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
                raise ValueError(f'Authority image must be at least {MIN_IMAGE_DIMENSION}×{MIN_IMAGE_DIMENSION}')
            if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                raise ValueError(f'Authority image must not exceed {MAX_IMAGE_DIMENSION}×{MAX_IMAGE_DIMENSION}')
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Authority image is not a valid supported image') from exc


def save_upload(file_storage: Any, dest_dir: Path, allowed: set[str], *, validate_image: bool = False) -> Path:
    if file_storage is None:
        raise ValueError('Required upload is missing')
    name = safe_name(file_storage.filename or 'upload')
    suffix = Path(name).suffix.lower()
    if suffix not in allowed:
        raise ValueError(f'Unsupported file type: {suffix or "none"}')
    destination = (dest_dir / name).resolve()
    destination.relative_to(dest_dir.resolve())
    file_storage.save(destination)
    if destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise ValueError('Uploaded file is empty')
    if destination.stat().st_size > MAX_UPLOAD_BYTES:
        destination.unlink(missing_ok=True)
        raise ValueError('Uploaded file exceeds the 250 MB limit')
    if validate_image:
        try:
            _validate_image(destination)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    return destination


def write_manifest(
    job: JobPaths,
    profile: dict[str, Any],
    asset_id: str,
    authority: Path,
    mesh: Path,
    mesh_origin: str,
    generation_report: Path | None,
    experiment_id: str,
    experiment_label: str,
    settings: dict[str, Any],
    generator: dict[str, Any],
    authority_validation_report: Path | None = None,
) -> Path:
    authority_hash = sha256_file(authority)
    generator_record = dict(generator)
    generator_record['inputAuthoritySha256'] = authority_hash
    manifest = {
        'schemaVersion': 'skyforge.mesh-builder.v3.0',
        'assetId': asset_id,
        'profile': profile,
        'experiment': {'id': experiment_id, 'label': experiment_label},
        'authority': {
            'path': authority.name,
            'sha256': authority_hash,
            'role': 'approved_top_down_authority',
            'suitabilityReport': (
                None
                if authority_validation_report is None
                else str(authority_validation_report.relative_to(job.source))
            ),
            'suitabilityReportSha256': (
                None if authority_validation_report is None else sha256_file(authority_validation_report)
            ),
        },
        'mesh': {
            'path': str(mesh.relative_to(job.source)),
            'sha256': sha256_file(mesh),
            'origin': mesh_origin,
            'generatedFromAuthority': mesh_origin == 'generated_from_authority',
            'generationReport': (
                None if generation_report is None else str(generation_report.relative_to(job.source))
            ),
            'generationReportSha256': None if generation_report is None else sha256_file(generation_report),
        },
        'generator': generator_record,
        'settings': settings,
        'measurementSettings': {
            'reviewSizes': list(REVIEW_SIZES),
            'authorityMaskMethod': 'alpha_threshold_else_corner_difference',
            'authorityMaskThreshold': OPAQUE_BG_DISTANCE_THRESHOLD,
            'fitCanvas': FIT_CANVAS_SIZE,
            'fitMargin': FIT_CANVAS_MARGIN,
            'fitResample': 'NEAREST',
            'silhouetteIoUInvariantTo': ['translation', 'uniform_scale'],
            'silhouetteIoUSensitiveTo': ['aspect_ratio', 'shape', 'rotation'],
        },
        'identityAcceptance': {
            'blenderSilhouetteIoUMin': 0.94 if mesh_origin == 'generated_from_authority' else 0.72,
            'generatedMeshMustUseAuthority': mesh_origin == 'generated_from_authority',
            'fallbackFixturesAllowed': False,
        },
        'requiredConsumedSettings': sorted(settings),
        'requiredOutputs': GENERATION_REQUIRED_OUTPUTS + RENDER_REQUIRED_OUTPUTS + POSTPROCESS_REQUIRED_OUTPUTS,
        'reviewProtocol': 'docs/EXPERIMENT_PROTOCOL.md',
        'distributionGate': {
            'approved': bool(generator.get('approvedForDistribution', False)),
            'warning': None if generator.get('approvedForDistribution') else 'Experimental use only; distribution approval is missing.',
        },
    }
    path = job.root / 'manifest.json'
    _write_json(path, manifest)
    return path


def resolve_blender_path(package_root: Path) -> Path | None:
    candidates: list[str] = []
    environment_path = os.environ.get('SKYFORGE_BLENDER_PATH')
    if environment_path:
        candidates.append(environment_path)
    config_path = package_root / 'config.json'
    if config_path.exists():
        try:
            configured = json.loads(config_path.read_text(encoding='utf-8')).get('blenderPath')
            if configured:
                candidates.append(configured)
        except (OSError, json.JSONDecodeError):
            pass
    candidates.extend([
        '/Applications/Blender.app/Contents/MacOS/Blender',
        shutil.which('blender') or '',
    ])
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser().resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def terminate_active_processes() -> None:
    with _ACTIVE_PROCESSES_LOCK:
        processes = list(_ACTIVE_PROCESSES.values())
    for process in processes:
        try:
            _terminate_process(process)
        except Exception:
            pass


atexit.register(terminate_active_processes)


def _handle_termination(signum: int, _frame: object) -> None:
    terminate_active_processes()
    raise SystemExit(128 + signum)


if threading.current_thread() is threading.main_thread():
    signal.signal(signal.SIGTERM, _handle_termination)


def run_blender(
    blender_path: Path,
    package_root: Path,
    job: JobPaths,
    manifest: Path,
    timeout_seconds: int = 900,
) -> None:
    blender_path = blender_path.expanduser().resolve()
    if not blender_path.is_file() or not os.access(blender_path, os.X_OK):
        raise RuntimeError('Configured Blender executable is missing or not executable')
    script = package_root / 'blender' / 'build_asset.py'
    command = [
        str(blender_path), '--background', '--factory-startup', '--python', str(script), '--',
        '--manifest', str(manifest), '--job-root', str(job.root),
    ]
    stdout_path = job.logs / 'blender.stdout.log'
    stderr_path = job.logs / 'blender.stderr.log'
    started = time.monotonic()
    with stdout_path.open('w', encoding='utf-8') as stdout, stderr_path.open('w', encoding='utf-8') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, text=True)
        with _ACTIVE_PROCESSES_LOCK:
            _ACTIVE_PROCESSES[job.root.name] = process
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            _terminate_process(process)
            raise RuntimeError(f'Blender timed out after {timeout_seconds} seconds; partial logs were retained') from exc
        finally:
            with _ACTIVE_PROCESSES_LOCK:
                _ACTIVE_PROCESSES.pop(job.root.name, None)
    if process.returncode != 0:
        raise RuntimeError(f'Blender failed ({process.returncode}). See logs.')
    (job.logs / 'timing.json').write_text(json.dumps({
        'elapsedSeconds': round(time.monotonic() - started, 3),
        'timeoutSeconds': timeout_seconds,
    }, indent=2), encoding='utf-8')


def _alpha_mask(image: Image.Image, threshold: int = OPAQUE_BG_DISTANCE_THRESHOLD) -> Image.Image:
    rgba = image.convert('RGBA')
    alpha = rgba.getchannel('A')
    extrema = alpha.getextrema()
    if extrema and extrema[0] < 250:
        return alpha.point(lambda value: 255 if value >= 24 else 0, mode='1').convert('L')

    rgb = rgba.convert('RGB')
    corners = [
        rgb.getpixel((0, 0)),
        rgb.getpixel((rgb.width - 1, 0)),
        rgb.getpixel((0, rgb.height - 1)),
        rgb.getpixel((rgb.width - 1, rgb.height - 1)),
    ]
    background = tuple(round(sum(pixel[channel] for pixel in corners) / len(corners)) for channel in range(3))
    difference = ImageChops.difference(rgb, Image.new('RGB', rgb.size, background))
    red, green, blue = difference.split()
    maximum_channel_difference = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    return maximum_channel_difference.point(lambda value: 255 if value > threshold else 0, mode='1').convert('L')


def _fit_mask(mask: Image.Image, size: int = FIT_CANVAS_SIZE, margin: int = FIT_CANVAS_MARGIN) -> Image.Image:
    mask = mask.convert('L')
    bbox = mask.getbbox()
    canvas = Image.new('L', (size, size), 0)
    if not bbox:
        return canvas
    crop = mask.crop(bbox)
    target = size - 2 * margin
    scale = min(target / crop.width, target / crop.height)
    resized = crop.resize(
        (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
        Image.Resampling.NEAREST,
    )
    canvas.paste(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    return canvas


def _mask_iou(first: Image.Image, second: Image.Image) -> float:
    intersection = ImageChops.logical_and(first.convert('1'), second.convert('1'))
    union = ImageChops.logical_or(first.convert('1'), second.convert('1'))
    intersection_count = ImageStat.Stat(intersection.convert('L')).sum[0] / 255
    union_count = ImageStat.Stat(union.convert('L')).sum[0] / 255
    return 0.0 if union_count == 0 else intersection_count / union_count


def _silhouette_iou(authority_path: Path, render_path: Path, output_path: Path, authority_mask_path: Path) -> dict[str, Any]:
    with Image.open(authority_path) as authority_image, Image.open(render_path) as render_image:
        raw_authority_mask = _alpha_mask(authority_image)
        raw_render_mask = _alpha_mask(render_image)
        raw_authority_mask.save(authority_mask_path)
        authority = _fit_mask(raw_authority_mask)
        rendered = _fit_mask(raw_render_mask)
        round_trip = _fit_mask(raw_authority_mask.resize(render_image.size, Image.Resampling.NEAREST))

    value = _mask_iou(authority, rendered)
    round_trip_ceiling = _mask_iou(authority, round_trip)

    authority_only = ImageChops.logical_and(authority.convert('1'), ImageChops.invert(rendered.convert('1')))
    render_only = ImageChops.logical_and(rendered.convert('1'), ImageChops.invert(authority.convert('1')))
    intersection = ImageChops.logical_and(authority.convert('1'), rendered.convert('1'))
    overlay = Image.new('RGBA', authority.size, (32, 35, 40, 255))
    overlay.paste((65, 170, 255, 255), mask=authority_only.convert('L'))
    overlay.paste((255, 115, 80, 255), mask=render_only.convert('L'))
    overlay.paste((105, 220, 145, 255), mask=intersection.convert('L'))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, overlay.width, 42), fill=(12, 16, 22, 235))
    draw.text(
        (12, 8),
        f'blue authority-only / orange render-only / green intersection — IoU {value:.4f}',
        fill=(245, 248, 252, 255),
    )
    overlay.save(output_path)

    return {
        'value': round(value, 6),
        'achievableCeilingAtRenderResolution': round(round_trip_ceiling, 6),
        'invariantTo': ['translation', 'uniform_scale'],
        'sensitiveTo': ['aspect_ratio', 'shape', 'rotation'],
        'fitCanvas': FIT_CANVAS_SIZE,
        'fitMargin': FIT_CANVAS_MARGIN,
        'resample': 'NEAREST',
    }


def _background(size: tuple[int, int], terrain_proxy: bool) -> Image.Image:
    if not terrain_proxy:
        return Image.new('RGBA', size, (83, 88, 94, 255))
    image = Image.new('RGBA', size, (91, 63, 43, 255))
    draw = ImageDraw.Draw(image)
    step = max(8, size[1] // 10)
    for y in range(-step, size[1] + step, step):
        draw.line((0, y, size[0], y + step // 2), fill=(118, 82, 54, 255), width=max(2, step // 5))
        draw.line((0, y + step // 2, size[0], y + step), fill=(63, 85, 88, 255), width=max(1, step // 8))
    return image


def _composite_on(image: Image.Image, background: Image.Image) -> Image.Image:
    foreground = image.convert('RGBA')
    canvas = background.copy()
    canvas.alpha_composite(
        foreground,
        ((canvas.width - foreground.width) // 2, (canvas.height - foreground.height) // 2),
    )
    return canvas


def _authority_tile(authority_path: Path, neutral_path: Path, tile: int) -> Image.Image:
    with Image.open(authority_path) as authority_source, Image.open(neutral_path) as neutral_source:
        authority = authority_source.convert('RGBA')
        authority_bbox = _alpha_mask(authority).getbbox()
        neutral_bbox = _alpha_mask(neutral_source).getbbox()
    if not authority_bbox or not neutral_bbox:
        return ImageOps.contain(authority, (tile, tile), Image.Resampling.LANCZOS)

    crop = authority.crop(authority_bbox)
    target_span = max(neutral_bbox[2] - neutral_bbox[0], neutral_bbox[3] - neutral_bbox[1])
    scale = target_span / max(crop.width, crop.height)
    resized = crop.resize(
        (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new('RGBA', (tile, tile), (0, 0, 0, 0))
    canvas.alpha_composite(resized, ((tile - resized.width) // 2, (tile - resized.height) // 2))
    return canvas


def _make_review_sheet(authority_path: Path, output_dir: Path, size: int, terrain_proxy: bool, output_name: str) -> None:
    labels = ['AUTHORITY', 'NEUTRAL', 'BANK LEFT', 'BANK RIGHT']
    source_names = [
        None,
        f'preview_neutral_{size}_lanczos.png',
        f'preview_bank_left_{size}_lanczos.png',
        f'preview_bank_right_{size}_lanczos.png',
    ]
    tile = size
    label_height = 24
    gutter = 8
    sheet = Image.new('RGBA', (gutter + 4 * (tile + gutter), label_height + tile + gutter), (24, 29, 36, 255))
    draw = ImageDraw.Draw(sheet)
    neutral_path = output_dir / f'preview_neutral_{size}_lanczos.png'
    for index, label in enumerate(labels):
        x = gutter + index * (tile + gutter)
        draw.text((x + 4, 6), label, fill=(235, 240, 247, 255))
        if index == 0:
            image = _authority_tile(authority_path, neutral_path, tile)
        else:
            with Image.open(output_dir / source_names[index]) as source:
                image = source.convert('RGBA')
        background = _background((tile, tile), terrain_proxy)
        sheet.alpha_composite(_composite_on(image, background), (x, label_height))
    sheet.save(output_dir / output_name)


def _measure_asset(output_dir: Path, silhouette: dict[str, Any], manifest: dict[str, Any]) -> None:
    asset_path = output_dir / 'asset.json'
    asset = json.loads(asset_path.read_text(encoding='utf-8'))
    with Image.open(output_dir / 'preview_neutral_96_lanczos.png') as image:
        mask = _alpha_mask(image)
    bbox = mask.getbbox()
    if not bbox:
        raise RuntimeError('Neutral render contains no visible craft pixels')
    pixels = mask.load()
    total = sum(pixels[x, y] / 255 for y in range(mask.height) for x in range(mask.width))
    if total <= 0:
        raise RuntimeError('Neutral render alpha mask is empty')
    centroid_x = sum(x * (pixels[x, y] / 255) for y in range(mask.height) for x in range(mask.width)) / total
    centroid_y = sum(y * (pixels[x, y] / 255) for y in range(mask.height) for x in range(mask.width)) / total
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    inset = 0.72
    asset['pivot'] = {
        'source': 'neutral_96_alpha_centroid',
        'units': 'normalized_image_fraction',
        'value': [round(centroid_x / mask.width, 6), round(centroid_y / mask.height, 6)],
    }
    asset['collision'] = {
        'type': 'ellipse',
        'source': 'neutral_96_alpha_bounds',
        'units': 'normalized_image_fraction',
        'insetFactor': inset,
        'rx': round((width / 2 / mask.width) * inset, 6),
        'ry': round((height / 2 / mask.height) * inset, 6),
    }
    asset['anchors'] = asset.get('anchors') or None
    asset['measurements'] = {
        'silhouetteIoU': silhouette,
        'neutralAlphaBounds96': list(bbox),
        'authorityMask': {
            'path': 'authority_mask.png',
            'method': manifest['measurementSettings']['authorityMaskMethod'],
            'threshold': manifest['measurementSettings']['authorityMaskThreshold'],
        },
        'downsample': {
            'primary': 'Pillow LANCZOS',
            'comparison': 'Pillow NEAREST',
            'reviewSizes': list(REVIEW_SIZES),
        },
    }
    asset['distributionGate'] = manifest['distributionGate']
    _write_json(asset_path, asset)


def _write_review_template(job: JobPaths, silhouette: dict[str, Any], experiment: dict[str, str]) -> None:
    review = {
        'schemaVersion': 'skyforge.mesh-review.v1',
        'jobId': job.root.name,
        'experiment': experiment,
        'silhouetteIoU': silhouette,
        'cleanupMinutes': None,
        'gates': {
            'identityRecognizable': None,
            'identityMarkersReadable': None,
            'pivotClippingFragmentsStable': None,
            'bankTextureStable': None,
            'cleanupBelow20Minutes': None,
        },
        'verdict': None,
        'notes': '',
    }
    _write_json(job.output / 'review.json', review)


def postprocess_outputs(job: JobPaths, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    output_dir = job.output
    for stem in ('preview_neutral', 'preview_bank_left', 'preview_bank_right'):
        master_path = output_dir / f'{stem}_master.png'
        with Image.open(master_path) as image:
            rgba = image.convert('RGBA')
            for size in REVIEW_SIZES:
                rgba.resize((size, size), Image.Resampling.LANCZOS).save(output_dir / f'{stem}_{size}_lanczos.png')
                rgba.resize((size, size), Image.Resampling.NEAREST).save(output_dir / f'{stem}_{size}_nearest.png')

    authority_path = job.source / manifest['authority']['path']
    silhouette = _silhouette_iou(
        authority_path,
        output_dir / 'silhouette_top_master.png',
        output_dir / 'silhouette_comparison.png',
        output_dir / 'authority_mask.png',
    )
    for size in REVIEW_SIZES:
        _make_review_sheet(authority_path, output_dir, size, False, f'review_sheet_neutral_{size}.png')
        _make_review_sheet(authority_path, output_dir, size, True, f'review_sheet_terrain_proxy_{size}.png')
    _measure_asset(output_dir, silhouette, manifest)
    _write_review_template(job, silhouette, manifest['experiment'])


def verify_output_group(job: JobPaths, names: list[str], label: str) -> dict[str, Any]:
    missing: list[str] = []
    empty: list[str] = []
    for name in names:
        path = job.output / name
        if not path.exists():
            missing.append(name)
        elif path.stat().st_size == 0:
            empty.append(name)
    if missing or empty:
        details = []
        if missing:
            details.append('missing=' + ','.join(missing))
        if empty:
            details.append('empty=' + ','.join(empty))
        raise RuntimeError(f'{label} output contract failed: ' + '; '.join(details))
    return {'label': label, 'outputCount': len(names), 'verifiedAt': utc_now()}


def verify_required_outputs(job: JobPaths, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    complete = verify_output_group(job, manifest['requiredOutputs'], 'Complete')
    run_report = json.loads((job.output / 'run_report.json').read_text(encoding='utf-8'))
    consumed = set(run_report.get('consumedSettings', []))
    required_consumed = set(manifest.get('requiredConsumedSettings', []))
    unconsumed = sorted(required_consumed - consumed)
    reported_unconsumed = sorted(run_report.get('unconsumedSettings', []))
    if unconsumed or reported_unconsumed:
        names = sorted(set(unconsumed) | set(reported_unconsumed))
        raise RuntimeError('Settings-consumption contract failed: ' + ', '.join(names))
    if not run_report.get('neutralPoseRestoredBeforeExport'):
        raise RuntimeError('Export evidence reports a non-neutral pose')
    if run_report.get('cleanExportContainsReviewRig'):
        raise RuntimeError('Export evidence reports surviving review-rig objects')
    if not run_report.get('meshMatricesIdentityAtExport'):
        raise RuntimeError('Export evidence reports residual mesh transforms')
    if not run_report.get('meshWorldBoundsPreservedDuringBake'):
        raise RuntimeError('Export evidence reports geometry drift during transform baking')
    if not run_report.get('normalizationBakedIntoMeshData'):
        raise RuntimeError('Export evidence reports normalization was not baked')
    if run_report.get('rootTransformMustBeHonoured'):
        raise RuntimeError('Export evidence reports a required root transform')
    if run_report.get('usedFallbackFixture'):
        raise RuntimeError('Production verification rejected a fallback fixture')
    asset = json.loads((job.output / 'asset.json').read_text(encoding='utf-8'))
    silhouette_value = float(asset.get('measurements', {}).get('silhouetteIoU', {}).get('value', 0.0))
    minimum_iou = float(manifest.get('identityAcceptance', {}).get('blenderSilhouetteIoUMin', 0.0))
    if silhouette_value < minimum_iou:
        raise RuntimeError(
            f'Identity gate failed: Blender silhouette IoU {silhouette_value:.4f} is below {minimum_iou:.4f}'
        )
    if manifest.get('identityAcceptance', {}).get('generatedMeshMustUseAuthority'):
        if manifest.get('mesh', {}).get('origin') != 'generated_from_authority':
            raise RuntimeError('Identity gate failed: mesh was not generated from the authority image')
    return {
        'requiredOutputCount': complete['outputCount'],
        'consumedSettings': sorted(consumed),
        'neutralPoseRestoredBeforeExport': bool(run_report['neutralPoseRestoredBeforeExport']),
        'cleanExportContainsReviewRig': bool(run_report['cleanExportContainsReviewRig']),
        'meshMatricesIdentityAtExport': bool(run_report['meshMatricesIdentityAtExport']),
        'meshWorldBoundsPreservedDuringBake': bool(run_report['meshWorldBoundsPreservedDuringBake']),
        'normalizationBakedIntoMeshData': bool(run_report['normalizationBakedIntoMeshData']),
        'rootTransformMustBeHonoured': bool(run_report['rootTransformMustBeHonoured']),
        'silhouetteIoU': silhouette_value,
        'silhouetteIoUMin': minimum_iou,
        'meshOrigin': manifest['mesh']['origin'],
        'verifiedAt': utc_now(),
    }


def verify_generation_contract(job: JobPaths, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    mesh_record = manifest.get('mesh') or {}
    mesh_path = job.source / str(mesh_record.get('path', ''))
    if not mesh_path.is_file() or mesh_path.stat().st_size == 0:
        raise RuntimeError('Mesh-generation contract failed: generated/imported mesh is missing')
    if sha256_file(mesh_path) != mesh_record.get('sha256'):
        raise RuntimeError('Mesh-generation contract failed: mesh checksum mismatch')

    origin = mesh_record.get('origin')
    if origin == 'generated_from_authority':
        if not mesh_record.get('generatedFromAuthority'):
            raise RuntimeError('Mesh-generation contract failed: authority provenance flag is absent')
        report_relative = mesh_record.get('generationReport')
        if not report_relative:
            raise RuntimeError('Mesh-generation contract failed: authority generation report is missing')
        report_path = job.source / report_relative
        if sha256_file(report_path) != mesh_record.get('generationReportSha256'):
            raise RuntimeError('Mesh-generation contract failed: generation report checksum mismatch')
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if mesh_path.suffix.lower() != '.glb':
            raise RuntimeError('Mesh-generation contract failed: authority generation did not produce a GLB')
        if not report.get('source', {}).get('authorityPixelsConsumed'):
            raise RuntimeError('Mesh-generation contract failed: authority pixels were not consumed')
        if report.get('source', {}).get('authoritySha256') != manifest['authority']['sha256']:
            raise RuntimeError('Mesh-generation contract failed: report is bound to a different authority image')
        if report.get('mesh', {}).get('sha256') != mesh_record['sha256']:
            raise RuntimeError('Mesh-generation contract failed: report is bound to a different mesh')
        if not report.get('gateResults', {}).get('passed'):
            raise RuntimeError('Mesh-generation contract failed: strict generator gates did not pass')
        if not report.get('mesh', {}).get('watertightByEdgeIncidence'):
            raise RuntimeError('Mesh-generation contract failed: generated mesh is not watertight')
        if not report.get('mesh', {}).get('glbReloadWatertight'):
            raise RuntimeError('Mesh-generation contract failed: generated GLB did not reload as watertight')
        if not report.get('mesh', {}).get('glbReloadWindingConsistent'):
            raise RuntimeError('Mesh-generation contract failed: generated GLB winding is inconsistent')
        if report.get('identityMetricSource') != 'target_mesh_and_emulated_blender_gltf_import_top_projection':
            raise RuntimeError(
                'Mesh-generation contract failed: identity was not measured in both target and Blender-import coordinates'
            )
        coordinate = report.get('mesh', {}).get('coordinateContract', {})
        if coordinate.get('encoding') != 'target_xyz_to_gltf_x_z_neg_y':
            raise RuntimeError('Mesh-generation contract failed: glTF coordinate encoding is absent or unsupported')
        if float(coordinate.get('blenderImportBoundsDelta', 1.0)) > 1e-5:
            raise RuntimeError('Mesh-generation contract failed: Blender-import coordinate reconstruction changed bounds')
        if float(coordinate.get('blenderImportHeightToPlanformRatio', 1.0)) > 0.45:
            raise RuntimeError('Mesh-generation contract failed: generated mesh would import vertically in Blender')
        blender_metrics = report.get('blenderImportIdentityMetrics', {})
        if float(blender_metrics.get('silhouetteIoU', 0.0)) < 0.94:
            raise RuntimeError('Mesh-generation contract failed: emulated Blender-import silhouette identity is too low')
    elif origin != 'uploaded_provider':
        raise RuntimeError(f'Mesh-generation contract failed: unknown mesh origin {origin!r}')

    output_contract = verify_output_group(job, GENERATION_REQUIRED_OUTPUTS, 'Authority mesh generation')
    return {
        'meshOrigin': origin,
        'meshSha256': mesh_record['sha256'],
        'authorityGenerated': bool(mesh_record.get('generatedFromAuthority')),
        'outputCount': output_contract['outputCount'],
        'verifiedAt': utc_now(),
    }


def package_job(job: JobPaths, archives_dir: Path) -> Path:
    status = read_job_status(job).get('status')
    if status != 'rendered':
        raise RuntimeError('Only a verified rendered job can be packaged')
    archives_dir.mkdir(parents=True, exist_ok=True)
    archive = archives_dir / f'{job.root.name}_review_package.zip'
    source_mtime = max(path.stat().st_mtime for path in job.root.rglob('*') if path.is_file())
    if archive.exists() and archive.stat().st_mtime >= source_mtime:
        return archive
    temporary_base = archives_dir / f'.{job.root.name}_review_package'
    created = Path(shutil.make_archive(str(temporary_base), 'zip', root_dir=job.root))
    created.replace(archive)
    return archive


def run_job(package_root: Path, job: JobPaths, manifest: Path, blender_path: Path) -> None:
    try:
        with _JOB_SEMAPHORE:
            generation_contract = verify_generation_contract(job, manifest)
            write_job_status(job, 'rendering', generationContract=generation_contract)
            run_blender(blender_path, package_root, job, manifest)
            render_contract = verify_output_group(job, RENDER_REQUIRED_OUTPUTS, 'Blender render')
            write_job_status(job, 'postprocessing', renderContract=render_contract)
            postprocess_outputs(job, manifest)
            postprocess_contract = verify_output_group(job, POSTPROCESS_REQUIRED_OUTPUTS, 'Post-processing')
            verification = verify_required_outputs(job, manifest)
            write_job_status(
                job,
                'rendered',
                renderContract=render_contract,
                postprocessContract=postprocess_contract,
                verification=verification,
            )
    except Exception as exc:
        write_job_status(job, 'failed', error=str(exc))


def start_job_thread(package_root: Path, job: JobPaths, manifest: Path, blender_path: Path) -> threading.Thread:
    thread = threading.Thread(
        target=run_job,
        args=(package_root, job, manifest, blender_path),
        name=f'mesh-builder-{job.root.name}',
        daemon=True,
    )
    thread.start()
    return thread


def prune_workspace(workspace: Path, keep_jobs: int = 20) -> None:
    if not workspace.exists():
        return
    jobs = [
        path for path in workspace.iterdir()
        if path.is_dir() and path.name not in {'_archives', '_vmp'} and is_valid_job_id(path.name)
    ]
    jobs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    removable = []
    for candidate in jobs:
        candidate_job = JobPaths(candidate, candidate / 'source', candidate / 'output', candidate / 'logs')
        status = read_job_status(candidate_job).get('status')
        if status not in {'queued', 'rendering', 'postprocessing'}:
            removable.append(candidate)
    for old in removable[keep_jobs:]:
        shutil.rmtree(old, ignore_errors=True)
        archive = workspace / '_archives' / f'{old.name}_review_package.zip'
        archive.unlink(missing_ok=True)
        vmp = workspace / '_vmp' / f'{old.name}.sfmeshpack'
        receipt = workspace / '_vmp' / f'{old.name}.import_receipt.json'
        vmp.unlink(missing_ok=True)
        receipt.unlink(missing_ok=True)
