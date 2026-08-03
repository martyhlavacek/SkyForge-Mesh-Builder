from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import bpy
from mathutils import Matrix, Vector

MIN_BLENDER_VERSION = (4, 2, 0)
AXES = {
    '+X': Vector((1, 0, 0)), '-X': Vector((-1, 0, 0)),
    '+Y': Vector((0, 1, 0)), '-Y': Vector((0, -1, 0)),
    '+Z': Vector((0, 0, 1)), '-Z': Vector((0, 0, -1)),
}


class RecordingSettings(dict[str, Any]):
    """Dictionary that records settings actually read by the running Blender job."""

    def __init__(self, source: dict[str, Any]):
        super().__init__(source)
        self.observed: set[str] = set()

    def __getitem__(self, key: str) -> Any:
        self.observed.add(key)
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self:
            self.observed.add(key)
        return super().get(key, default)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--job-root', required=True)
    if '--' not in sys.argv:
        raise RuntimeError('Missing Blender script argument separator')
    return parser.parse_args(sys.argv[sys.argv.index('--') + 1:])


def require_supported_blender() -> None:
    if bpy.app.version < MIN_BLENDER_VERSION:
        raise RuntimeError(
            f'Blender 4.2 or newer is required; detected {bpy.app.version_string}'
        )


def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_mesh(path: Path) -> None:
    extension = path.suffix.lower()
    if extension in {'.glb', '.gltf'}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif extension == '.obj':
        bpy.ops.wm.obj_import(filepath=str(path))
    elif extension == '.fbx':
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        raise RuntimeError(f'Unsupported mesh extension: {extension}')


def parent_preserve_world(child: bpy.types.Object, parent: bpy.types.Object | None) -> None:
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = world


def remove_object_preserve_descendants(obj: bpy.types.Object) -> None:
    """Remove one unsupported node without changing any descendant world transform."""
    replacement_parent = obj.parent
    for child in list(obj.children):
        parent_preserve_world(child, replacement_parent)
    bpy.data.objects.remove(obj, do_unlink=True)


def sanitize_imported_objects() -> list[bpy.types.Object]:
    supported = {'MESH', 'EMPTY', 'ARMATURE'}
    for obj in list(bpy.context.scene.objects):
        if obj.type not in supported:
            remove_object_preserve_descendants(obj)
    objects = list(bpy.context.scene.objects)
    if not any(obj.type == 'MESH' for obj in objects):
        raise RuntimeError('Imported scene contains no supported mesh objects')
    return objects


def reject_unsupported_armatures(objects: list[bpy.types.Object]) -> None:
    armatures = sorted(obj.name for obj in objects if obj.type == 'ARMATURE')
    if armatures:
        raise RuntimeError(
            'Armature-backed imports are not supported by the v0.3.1 static normalization export: '
            + ', '.join(armatures)
        )


def object_tree_roots(objects: list[bpy.types.Object]) -> list[bpy.types.Object]:
    object_set = set(objects)
    return [obj for obj in objects if obj.parent not in object_set]


def orientation_matrix(forward_axis: str, up_axis: str) -> Matrix:
    forward = AXES[forward_axis]
    up = AXES[up_axis]
    if abs(forward.dot(up)) > 1e-6:
        raise RuntimeError('Forward and up axes are not orthogonal')
    right = forward.cross(up)
    source_basis = Matrix((right, forward, up)).transposed().to_4x4()
    return source_basis.inverted()


def descendants(root: bpy.types.Object) -> list[bpy.types.Object]:
    result: list[bpy.types.Object] = []
    stack = list(root.children)
    while stack:
        item = stack.pop()
        result.append(item)
        stack.extend(item.children)
    return result


def mesh_descendants(root: bpy.types.Object) -> list[bpy.types.Object]:
    return [obj for obj in descendants(root) if obj.type == 'MESH']


def world_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    minimum = Vector((float('inf'), float('inf'), float('inf')))
    maximum = Vector((float('-inf'), float('-inf'), float('-inf')))
    for obj in objects:
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            for axis in range(3):
                minimum[axis] = min(minimum[axis], world[axis])
                maximum[axis] = max(maximum[axis], world[axis])
    if not all(math.isfinite(value) for value in (*minimum, *maximum)):
        raise RuntimeError('Mesh bounds could not be measured')
    return minimum, maximum


def world_vertex_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    minimum = Vector((float('inf'), float('inf'), float('inf')))
    maximum = Vector((float('-inf'), float('-inf'), float('-inf')))
    for obj in objects:
        if obj.type != 'MESH':
            continue
        for vertex in obj.data.vertices:
            world = obj.matrix_world @ vertex.co
            for axis in range(3):
                minimum[axis] = min(minimum[axis], world[axis])
                maximum[axis] = max(maximum[axis], world[axis])
    if not all(math.isfinite(value) for value in (*minimum, *maximum)):
        raise RuntimeError('Mesh vertex bounds could not be measured')
    return minimum, maximum


def matrix_max_identity_delta(matrix: Matrix) -> float:
    identity = Matrix.Identity(4)
    return max(abs(float(matrix[row][column] - identity[row][column])) for row in range(4) for column in range(4))


def bounds_max_delta(
    first: tuple[Vector, Vector],
    second: tuple[Vector, Vector],
) -> float:
    return max(abs(float(first[index][axis] - second[index][axis])) for index in range(2) for axis in range(3))


def build_normalized_hierarchy(
    imported_objects: list[bpy.types.Object],
    forward_axis: str,
    up_axis: str,
    profile_scale: float,
) -> bpy.types.Object:
    craft_root = bpy.data.objects.new('craft_root', None)
    bpy.context.collection.objects.link(craft_root)
    for root_object in object_tree_roots(imported_objects):
        parent_preserve_world(root_object, craft_root)

    orientation = orientation_matrix(forward_axis, up_axis)
    craft_root.matrix_world = orientation
    bpy.context.view_layer.update()
    meshes = mesh_descendants(craft_root)
    if not meshes:
        raise RuntimeError('Imported asset contains no mesh objects')

    minimum, maximum = world_bounds(meshes)
    center = (minimum + maximum) / 2
    span = max(maximum.x - minimum.x, maximum.y - minimum.y, 1e-5)
    target_span = 5.5 * profile_scale
    scale = target_span / span
    craft_root.matrix_world = Matrix.Scale(scale, 4) @ Matrix.Translation(-center) @ orientation
    bpy.context.view_layer.update()
    return craft_root


def principled_node(material: bpy.types.Material) -> bpy.types.Node:
    for node in material.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            return node
    raise RuntimeError(f'Material {material.name} has no Principled BSDF node')


def material(name: str, color: tuple[float, float, float], emission_strength: float = 0) -> bpy.types.Material:
    result = bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1)
    result.use_nodes = True
    bsdf = principled_node(result)
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = 0.35
    bsdf.inputs['Roughness'].default_value = 0.45
    if emission_strength:
        emission_input = bsdf.inputs.get('Emission Color') or bsdf.inputs.get('Emission')
        if emission_input is not None:
            emission_input.default_value = (*color, 1)
        strength_input = bsdf.inputs.get('Emission Strength')
        if strength_input is not None:
            strength_input.default_value = emission_strength
    return result


def ensure_default_materials(craft_root: bpy.types.Object) -> None:
    default = material('MilitaryHull', (0.22, 0.31, 0.39))
    for obj in mesh_descendants(craft_root):
        if not obj.data.materials:
            obj.data.materials.append(default)


def create_bank_root(craft_root: bpy.types.Object) -> bpy.types.Object:
    bank_root = bpy.data.objects.new('review_bank_root', None)
    bpy.context.collection.objects.link(bank_root)
    parent_preserve_world(craft_root, bank_root)
    return bank_root


def select_eevee_engine(scene: bpy.types.Scene) -> str:
    """Select the EEVEE identifier supported by the running Blender version.

    Blender 4.2-4.x uses BLENDER_EEVEE_NEXT. Blender 5.0+ renamed the
    identifier to BLENDER_EEVEE. Probe the live enum instead of assuming that
    every newer Blender release preserves the older identifier.
    """
    failures: list[str] = []
    for engine in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
        try:
            scene.render.engine = engine
        except (TypeError, ValueError) as exc:
            failures.append(f'{engine}: {exc}')
        else:
            return engine
    raise RuntimeError(
        'No supported EEVEE render engine identifier is available. ' + '; '.join(failures)
    )


def setup_scene(master_resolution: int, render_samples: int) -> tuple[bpy.types.Object, list[bpy.types.Object], dict[str, Any]]:
    scene = bpy.context.scene
    selected_engine = select_eevee_engine(scene)
    scene.render.resolution_x = master_resolution
    scene.render.resolution_y = master_resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'
    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1

    if not hasattr(scene, 'eevee') or not hasattr(scene.eevee, 'taa_render_samples'):
        raise RuntimeError('Blender does not expose the pinned EEVEE render-sample setting')
    scene.eevee.taa_render_samples = render_samples

    bpy.ops.object.camera_add(location=(0, 0, 12))
    camera = bpy.context.object
    camera.name = 'review_camera'
    camera.data.type = 'ORTHO'
    scene.camera = camera

    lights: list[bpy.types.Object] = []
    bpy.ops.object.light_add(type='AREA', location=(-5, -4, 9))
    key = bpy.context.object
    key.name = 'review_key_north_west'
    key.data.energy = 1200
    key.data.shape = 'DISK'
    key.data.size = 5
    lights.append(key)

    bpy.ops.object.light_add(type='AREA', location=(4, 5, 5))
    fill = bpy.context.object
    fill.name = 'review_fill'
    fill.data.energy = 350
    fill.data.size = 4
    lights.append(fill)

    render_state = {
        'engine': selected_engine,
        'resolution': [scene.render.resolution_x, scene.render.resolution_y],
        'renderSamples': int(scene.eevee.taa_render_samples),
        'viewTransform': scene.view_settings.view_transform,
        'look': scene.view_settings.look,
        'exposure': float(scene.view_settings.exposure),
        'gamma': float(scene.view_settings.gamma),
        'transparentFilm': bool(scene.render.film_transparent),
    }
    return camera, lights, render_state


def set_camera_pitch(camera: bpy.types.Object, pitch_degrees: float) -> None:
    pitch = math.radians(pitch_degrees)
    distance = 14.0
    camera.location = (0, -distance * math.sin(pitch), distance * math.cos(pitch))
    direction = Vector((0, 0, 0)) - camera.location
    camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def set_bank(bank_root: bpy.types.Object, bank_degrees: float) -> None:
    bank_root.rotation_mode = 'XYZ'
    bank_root.rotation_euler = (0, math.radians(bank_degrees), 0)
    bpy.context.view_layer.update()


def projected_required_scale(
    bank_root: bpy.types.Object,
    visible_objects: list[bpy.types.Object],
    camera: bpy.types.Object,
    banks: list[float],
    margin: float = 1.14,
) -> float:
    maximum_extent = 0.1
    for bank in banks:
        set_bank(bank_root, bank)
        inverse_camera = camera.matrix_world.inverted()
        for obj in visible_objects:
            if obj.type != 'MESH' or obj.hide_render:
                continue
            for corner in obj.bound_box:
                camera_point = inverse_camera @ (obj.matrix_world @ Vector(corner))
                maximum_extent = max(maximum_extent, abs(camera_point.x), abs(camera_point.y))
    set_bank(bank_root, 0)
    return maximum_extent * 2 * margin


def validate_canonical_frame(
    required_scale: float,
    canonical_scale: float,
    label: str,
    height_to_planform_ratio: float,
) -> None:
    if required_scale > canonical_scale + 1e-6:
        raise RuntimeError(
            f'Canonical orthographic frame would clip {label}: '
            f'required={required_scale:.6f}, canonical={canonical_scale:.6f}, '
            f'heightToPlanformRatio={height_to_planform_ratio:.6f}'
        )


def render(scene: bpy.types.Scene, output_dir: Path, filename: str) -> None:
    scene.render.filepath = str(output_dir / filename)
    bpy.ops.render.render(write_still=True)


def render_review_set(
    output_dir: Path,
    bank_root: bpy.types.Object,
    camera: bpy.types.Object,
    bank_degrees: float,
    camera_pitch: float,
    canonical_ortho_scale: float,
    visible_objects: list[bpy.types.Object],
    height_to_planform_ratio: float,
) -> dict[str, Any]:
    scene = bpy.context.scene
    set_camera_pitch(camera, camera_pitch)
    camera.data.ortho_scale = canonical_ortho_scale
    required_review = projected_required_scale(
        bank_root, visible_objects, camera, [-bank_degrees, 0, bank_degrees]
    )
    validate_canonical_frame(
        required_review, canonical_ortho_scale, 'review frames', height_to_planform_ratio
    )

    for filename, angle in (
        ('preview_neutral_master.png', 0),
        ('preview_bank_left_master.png', -bank_degrees),
        ('preview_bank_right_master.png', bank_degrees),
    ):
        set_bank(bank_root, angle)
        render(scene, output_dir, filename)

    set_bank(bank_root, 0)
    set_camera_pitch(camera, 0)
    camera.data.ortho_scale = canonical_ortho_scale
    required_silhouette = projected_required_scale(bank_root, visible_objects, camera, [0])
    validate_canonical_frame(
        required_silhouette, canonical_ortho_scale, 'silhouette frame', height_to_planform_ratio
    )
    render(scene, output_dir, 'silhouette_top_master.png')
    set_camera_pitch(camera, camera_pitch)
    set_bank(bank_root, 0)

    review_headroom = canonical_ortho_scale - required_review
    silhouette_headroom = canonical_ortho_scale - required_silhouette
    return {
        'canonicalOrthoScale': float(camera.data.ortho_scale),
        'requiredReviewOrthoScale': round(required_review, 6),
        'requiredSilhouetteOrthoScale': round(required_silhouette, 6),
        'reviewFrameHeadroomWorldUnits': round(review_headroom, 6),
        'reviewFrameHeadroomFraction': round(review_headroom / canonical_ortho_scale, 6),
        'silhouetteFrameHeadroomWorldUnits': round(silhouette_headroom, 6),
        'silhouettePassExcludedObjects': [],
        'heightToPlanformRatio': round(height_to_planform_ratio, 6),
    }


def clean_scene_for_export(craft_root: bpy.types.Object) -> list[bpy.types.Object]:
    parent_preserve_world(craft_root, None)
    keep = {craft_root, *descendants(craft_root)}
    for obj in list(bpy.context.scene.objects):
        if obj not in keep:
            remove_object_preserve_descendants(obj)
    bpy.context.view_layer.update()
    if any(obj.type in {'CAMERA', 'LIGHT'} for obj in bpy.context.scene.objects):
        raise RuntimeError('Review camera or lights survived clean export preparation')
    return [craft_root, *descendants(craft_root)]


def bake_static_mesh_transforms(craft_root: bpy.types.Object) -> tuple[list[bpy.types.Object], dict[str, Any]]:
    armatures = [obj for obj in descendants(craft_root) if obj.type == 'ARMATURE']
    if armatures:
        raise RuntimeError('Armature-backed import reached the static export stage unexpectedly')

    meshes = mesh_descendants(craft_root)
    if not meshes:
        raise RuntimeError('No mesh objects are available for transform baking')

    # Capture every world transform and the normalized world bounds before any
    # hierarchy mutation. A mesh may parent another mesh.
    world_matrices = {obj: obj.matrix_world.copy() for obj in meshes}
    bounds_before = world_bounds(meshes)

    # The root must be identity before child bases are reset. Resetting it after
    # the loop algebraically cancels the baked normalization (MBS-45).
    craft_root.matrix_world = Matrix.Identity(4)
    bpy.context.view_layer.update()

    for obj in meshes:
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        obj.data.transform(world_matrices[obj])
        obj.data.update()
        obj.parent = craft_root
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_basis = Matrix.Identity(4)

    for obj in list(descendants(craft_root)):
        if obj.type != 'MESH':
            remove_object_preserve_descendants(obj)
    bpy.context.view_layer.update()

    baked_meshes = mesh_descendants(craft_root)
    bounds_after = world_bounds(baked_meshes)
    vertex_bounds_after = world_vertex_bounds(baked_meshes)
    bounds_delta = bounds_max_delta(bounds_before, bounds_after)
    bounds_cache_crosscheck_delta = bounds_max_delta(bounds_after, vertex_bounds_after)
    if bounds_cache_crosscheck_delta > 1e-5:
        raise RuntimeError(
            'Object bound-box cache disagrees with mesh vertex bounds after transform baking: '
            f'{bounds_cache_crosscheck_delta:.9f}'
        )
    residual_mesh_matrices = {
        obj.name: round(matrix_max_identity_delta(obj.matrix_world), 9)
        for obj in baked_meshes
        if matrix_max_identity_delta(obj.matrix_world) > 1e-6
    }
    root_delta = matrix_max_identity_delta(craft_root.matrix_world)
    mesh_matrices_identity = not residual_mesh_matrices
    bounds_preserved = bounds_delta <= 1e-5
    normalization_baked = root_delta <= 1e-6 and mesh_matrices_identity and bounds_preserved

    if residual_mesh_matrices:
        raise RuntimeError(
            'Normalization was not baked; residual mesh transforms: '
            + ', '.join(sorted(residual_mesh_matrices))
        )
    if not bounds_preserved:
        raise RuntimeError(f'Mesh world bounds changed during transform baking: delta={bounds_delta:.9f}')

    evidence = {
        'meshMatricesIdentityAtExport': mesh_matrices_identity,
        'residualMeshMatrixDeltas': residual_mesh_matrices,
        'meshWorldBoundsPreservedDuringBake': bounds_preserved,
        'meshWorldBoundsBakeDelta': round(bounds_delta, 9),
        'meshBoundsCacheCrossCheckDelta': round(bounds_cache_crosscheck_delta, 9),
        'normalizationBakedIntoMeshData': normalization_baked,
        'rootTransformMustBeHonoured': not normalization_baked,
    }
    return [craft_root, *baked_meshes], evidence


def export_clean_asset(
    output_dir: Path,
    craft_root: bpy.types.Object,
    bank_root: bpy.types.Object,
) -> dict[str, Any]:
    bank_rotation = tuple(round(float(value), 9) for value in bank_root.rotation_euler)
    neutral_pose = not any(abs(value) > 1e-6 for value in bank_rotation)
    if not neutral_pose:
        raise RuntimeError(f'Neutral pose was not restored before export: {bank_rotation}')

    clean_scene_for_export(craft_root)
    craft_objects, bake_evidence = bake_static_mesh_transforms(craft_root)
    scene_objects = list(bpy.context.scene.objects)
    object_names = sorted(obj.name for obj in scene_objects)
    object_types = sorted({obj.type for obj in scene_objects})
    review_rig_names = [
        name for name in object_names
        if name.startswith('review_') or name.startswith('ThrusterPreview_')
    ]
    if review_rig_names:
        raise RuntimeError('Review rig survived clean export preparation: ' + ', '.join(review_rig_names))

    bpy.ops.wm.save_as_mainfile(filepath=str(output_dir / 'normalized.blend'))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in craft_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = craft_root
    bpy.ops.export_scene.gltf(
        filepath=str(output_dir / 'normalized.glb'),
        export_format='GLB',
        use_selection=True,
        export_cameras=False,
        export_lights=False,
    )
    mesh_count = sum(1 for obj in craft_objects if obj.type == 'MESH')
    if mesh_count < 1:
        raise RuntimeError('Clean export contains no mesh objects')

    root_matrix = [[round(float(value), 9) for value in row] for row in craft_root.matrix_world]
    return {
        'exportedObjectCount': len(craft_objects),
        'exportedMeshCount': mesh_count,
        'bankRootRotationAtExport': list(bank_rotation),
        'neutralPoseRestoredBeforeExport': neutral_pose,
        'sceneObjectTypesAtExport': object_types,
        'sceneObjectNamesAtExport': object_names,
        'cleanExportContainsReviewRig': bool(review_rig_names),
        'craftRootMatrixAtExport': root_matrix,
        **bake_evidence,
    }


def write_asset_json(
    output_dir: Path,
    manifest: dict[str, Any],
    settings: RecordingSettings,
    export_evidence: dict[str, Any],
) -> None:
    asset = {
        'schemaVersion': 'skyforge.asset.sidecar.v3.0',
        'integrationStatus': 'pre-schema-sidecar; mapping CR required before SkyForge Studio import',
        'assetId': manifest['assetId'],
        'profileId': manifest['profile']['id'],
        'profileScale': manifest['profile']['scale'],
        'normalization': {
            'targetCoordinates': {'forward': '+Y', 'up': '+Z'},
            'bakedIntoMeshData': bool(export_evidence['normalizationBakedIntoMeshData']),
            'meshMatricesIdentityAtExport': bool(export_evidence['meshMatricesIdentityAtExport']),
            'worldBoundsPreservedDuringBake': bool(export_evidence['meshWorldBoundsPreservedDuringBake']),
            'rootTransformMustBeHonoured': bool(export_evidence['rootTransformMustBeHonoured']),
        },
        'pivot': None,
        'collision': None,
        'animations': {
            'bank': {
                'frames96': [
                    'preview_bank_left_96_lanczos.png',
                    'preview_neutral_96_lanczos.png',
                    'preview_bank_right_96_lanczos.png',
                ],
                'frames64': [
                    'preview_bank_left_64_lanczos.png',
                    'preview_neutral_64_lanczos.png',
                    'preview_bank_right_64_lanczos.png',
                ],
                'fps': 8,
                'bankDegrees': settings['bankDegrees'],
            }
        },
        'anchors': None,
        'features': {
            'thrusters': {
                'requested': False,
                'implemented': False,
                'includedInNormalizedMesh': False,
                'reason': 'Disabled until authority-derived mesh identity and orientation are validated.',
            },
            'destruction': settings['destruction'],
        },
        'sourceManifest': '../manifest.json',
        'generator': manifest['generator'],
    }
    (output_dir / 'asset.json').write_text(json.dumps(asset, indent=2), encoding='utf-8')


def main() -> None:
    require_supported_blender()
    arguments = parse_args()
    job_root = Path(arguments.job_root).resolve()
    manifest_path = Path(arguments.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    output_dir = job_root / 'output'
    output_dir.mkdir(exist_ok=True)

    clear_scene()
    mesh_record = manifest.get('mesh') or {}
    mesh_path_value = mesh_record.get('path')
    if not mesh_path_value:
        raise RuntimeError('Production mesh build requires a generated or provider mesh; fallback fixtures are forbidden')
    mesh_path = job_root / 'source' / mesh_path_value
    if not mesh_path.is_file():
        raise RuntimeError(f'Manifest mesh does not exist: {mesh_path}')
    import_mesh(mesh_path)

    imported_objects = sanitize_imported_objects()
    reject_unsupported_armatures(imported_objects)
    settings = RecordingSettings(manifest['settings'])
    craft_root = build_normalized_hierarchy(
        imported_objects,
        settings['forwardAxis'],
        settings['upAxis'],
        float(settings['profileScale']),
    )
    ensure_default_materials(craft_root)
    craft_minimum, craft_maximum = world_bounds(mesh_descendants(craft_root))
    planform_span = max(craft_maximum.x - craft_minimum.x, craft_maximum.y - craft_minimum.y, 1e-6)
    height_to_planform_ratio = float((craft_maximum.z - craft_minimum.z) / planform_span)
    if mesh_record.get('generatedFromAuthority') and height_to_planform_ratio > 0.45:
        raise RuntimeError(
            'Authority-generated mesh imported with an invalid vertical orientation: '
            f'heightToPlanformRatio={height_to_planform_ratio:.6f}, expected <= 0.450000. '
            'This normally indicates a glTF Y-up/Z-up coordinate-contract failure.'
        )
    bank_root = create_bank_root(craft_root)

    camera, _lights, render_state = setup_scene(
        int(settings['masterResolution']),
        int(settings['renderSamples']),
    )
    visible_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    frame_evidence = render_review_set(
        output_dir,
        bank_root,
        camera,
        float(settings['bankDegrees']),
        float(settings['cameraPitchDegrees']),
        float(settings['canonicalOrthoScale']),
        visible_objects,
        height_to_planform_ratio,
    )

    set_bank(bank_root, 0)
    frame_calibration = settings['canonicalFrameCalibration']
    export_evidence = export_clean_asset(output_dir, craft_root, bank_root)
    write_asset_json(output_dir, manifest, settings, export_evidence)
    consumed_settings = sorted(settings.observed)
    required_settings = sorted(manifest.get('requiredConsumedSettings', []))
    run_report = {
        'schemaVersion': 'skyforge.mesh-build-run.v3.0',
        'blenderVersion': bpy.app.version_string,
        'meshOrigin': mesh_record.get('origin'),
        'authorityGeneratedMesh': bool(mesh_record.get('generatedFromAuthority')),
        'consumedSettings': consumed_settings,
        'requiredConsumedSettings': required_settings,
        'unconsumedSettings': sorted(set(required_settings) - set(consumed_settings)),
        'renderState': render_state,
        'frameEvidence': frame_evidence,
        'canonicalFrameCalibration': frame_calibration,
        **export_evidence,
    }
    if run_report['unconsumedSettings']:
        raise RuntimeError('Blender settings were declared but not observed: ' + ', '.join(run_report['unconsumedSettings']))
    (output_dir / 'run_report.json').write_text(json.dumps(run_report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
