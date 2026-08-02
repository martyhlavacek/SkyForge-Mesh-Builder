from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_server_source_uses_contained_job_lookup_and_no_form_blender_path():
    source = (PACKAGE_ROOT / 'app/server.py').read_text(encoding='utf-8')
    assert "request.form.get('blenderPath'" not in source
    assert 'job_paths(workspace_root, job_id)' in source
    assert 'require_csrf()' in source


def test_blender_report_uses_observed_settings_and_measured_export_evidence():
    source = (PACKAGE_ROOT / 'blender/build_asset.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    assert 'consumed_settings = sorted(settings.observed)' in source
    assert "'neutralPoseRestoredBeforeExport': True" not in source
    assert "'cleanExportContainsReviewRig': False" not in source
    assert 'bankRootRotationAtExport' in source
    assert 'sceneObjectTypesAtExport' in source
    assert any(isinstance(node, ast.ClassDef) and node.name == 'RecordingSettings' for node in ast.walk(tree))
    assert 'use_selection=True' in source
    assert 'export_cameras=False' in source
    assert 'export_lights=False' in source


def test_thruster_geometry_is_absent_until_mesh_identity_is_validated():
    blender_source = (PACKAGE_ROOT / 'blender/build_asset.py').read_text(encoding='utf-8')
    html_source = (PACKAGE_ROOT / 'app/templates/index.html').read_text(encoding='utf-8')
    server_source = (PACKAGE_ROOT / 'app/server.py').read_text(encoding='utf-8')
    assert 'primitive_cone_add' not in blender_source
    assert 'def create_thrusters' not in blender_source
    assert 'name="thrusters"' not in html_source
    assert "request.form.get('thrusters')" not in server_source
    assert "'silhouettePassExcludedObjects': []" in blender_source


def test_static_transform_bake_resets_root_before_children_and_measures_result():
    source = (PACKAGE_ROOT / 'blender/build_asset.py').read_text(encoding='utf-8')
    function_start = source.index('def bake_static_mesh_transforms')
    capture = source.index('world_matrices = {obj: obj.matrix_world.copy() for obj in meshes}', function_start)
    root_reset = source.index('craft_root.matrix_world = Matrix.Identity(4)', function_start)
    mutation = source.index('obj.parent = craft_root', function_start)
    assert capture < root_reset < mutation
    assert 'obj.matrix_parent_inverse = Matrix.Identity(4)' in source
    assert 'obj.matrix_basis = Matrix.Identity(4)' in source
    assert "'meshMatricesIdentityAtExport': mesh_matrices_identity" in source
    assert "'normalizationBakedIntoMeshData': normalization_baked" in source
    assert "'rootTransformMustBeHonoured': not normalization_baked" in source


def test_armatures_are_rejected_before_hierarchy_normalization_and_rendering():
    source = (PACKAGE_ROOT / 'blender/build_asset.py').read_text(encoding='utf-8')
    reject_call = source.index('reject_unsupported_armatures(imported_objects)')
    normalize_call = source.index('craft_root = build_normalized_hierarchy')
    render_call = source.index('frame_evidence = render_review_set')
    assert reject_call < normalize_call < render_call


def test_blender_eevee_engine_is_selected_compatibly_for_blender_4_and_5():
    source = (PACKAGE_ROOT / 'blender/build_asset.py').read_text(encoding='utf-8')
    assert "def select_eevee_engine" in source
    assert "('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT')" in source
    assert "scene.render.engine = 'BLENDER_EEVEE_NEXT'" not in source
    assert "'engine': selected_engine" in source


def test_production_blender_path_has_no_fallback_mesh():
    source = (PACKAGE_ROOT / 'blender/build_asset.py').read_text(encoding='utf-8')
    assert 'def fallback_ship' not in source
    assert 'fallback_ship()' not in source
    assert 'fallback fixtures are forbidden' in source
    assert "mesh_record.get('generatedFromAuthority')" in source


def test_server_generates_authority_mesh_before_blender_and_requires_explicit_mode():
    source = (PACKAGE_ROOT / 'app/server.py').read_text(encoding='utf-8')
    assert "request.form.get('experiment', '').strip()" in source
    generation = source.index("provider = resolve_provider('local_deterministic')")
    manifest = source.index('manifest = write_manifest', generation)
    thread = source.index('start_job_thread', manifest)
    assert generation < manifest < thread
    assert "mesh_origin = 'generated_from_authority'" in source
    assert "asset_role='air_moving'" in source


def test_identity_gate_rejects_low_iou_and_fallback_evidence():
    source = (PACKAGE_ROOT / 'app/pipeline.py').read_text(encoding='utf-8')
    assert 'Identity gate failed: Blender silhouette IoU' in source
    assert 'Production verification rejected a fallback fixture' in source
    assert "mesh was not generated from the authority image" in source


def test_transform_bake_crosschecks_bound_box_cache_against_vertices():
    source = (PACKAGE_ROOT / 'blender/build_asset.py').read_text(encoding='utf-8')
    assert 'obj.data.update()' in source
    assert 'vertex_bounds_after = world_vertex_bounds(baked_meshes)' in source
    assert 'meshBoundsCacheCrossCheckDelta' in source
    assert 'heightToPlanformRatio' in source


def test_generated_mesh_orientation_is_fail_closed_before_rendering():
    source = (PACKAGE_ROOT / 'blender/build_asset.py').read_text(encoding='utf-8')
    ratio_gate = source.index("height_to_planform_ratio > 0.45")
    render_call = source.index('frame_evidence = render_review_set')
    assert ratio_gate < render_call
    assert 'glTF Y-up/Z-up coordinate-contract failure' in source


def test_authority_mode_axes_are_fixed_and_not_user_selectable():
    server = (PACKAGE_ROOT / 'app/server.py').read_text(encoding='utf-8')
    html = (PACKAGE_ROOT / 'app/templates/index.html').read_text(encoding='utf-8')
    assert "forward_axis, up_axis = '+Y', '+Z'" in server
    assert 'Authority Mesh uses the fixed verified coordinate contract' in html
    assert 'id="providerAxisFields" hidden' in html


def test_concept_prompts_encode_strict_camera_lighting_and_identity_lessons():
    source = (PACKAGE_ROOT / 'app/server.py').read_text(encoding='utf-8')
    required_beauty_phrases = [
        'strict 3/4 front beauty-shot presentation',
        'slightly elevated fixed camera angle',
        'fully visible inside frame',
        'no extreme wide-angle distortion',
        'controlled studio-style lighting',
        'no heavy rim-light washout',
        'simple dark or neutral background only',
        'no smoke, motion blur, lens flare, explosions, starscape clutter',
        'easy later conversion into a top-down authority view',
    ]
    required_authority_phrases = [
        'This must be the same ship, not a redesign or reinterpretation',
        'true overhead top-down view',
        'orthographic or near-orthographic presentation',
        'zero roll',
        'nose oriented upward in frame',
        'fully visible, and surrounded by a small clean margin',
        'minimal neutral lighting',
        'no dramatic shading',
        'no atmospheric effects, no glow, no cast-shadow clutter, no perspective tricks',
    ]
    for phrase in required_beauty_phrases + required_authority_phrases:
        assert phrase in source


def test_settings_ui_and_routes_keep_api_key_out_of_config_and_manifests():
    server = (PACKAGE_ROOT / 'app/server.py').read_text(encoding='utf-8')
    template = (PACKAGE_ROOT / 'app/templates/index.html').read_text(encoding='utf-8')
    settings_store = (PACKAGE_ROOT / 'app/settings_store.py').read_text(encoding='utf-8')
    assert "@app.post('/api/settings')" in server
    assert "@app.post('/api/settings/test-openai')" in server
    assert "@app.post('/api/settings/test-blender')" in server
    assert 'type="password" id="settingsApiKey"' in template
    assert 'macOS Keychain' in template
    assert "openai_config.pop('apiKey', None)" in settings_store
    assert "config.pop('openaiApiKey', None)" in settings_store
    assert "'legacy config.json'" not in settings_store
    assert 'apiKey' not in (PACKAGE_ROOT / 'config.json.example').read_text(encoding='utf-8')


def test_validation_precedes_job_allocation_and_browser_paths_are_not_returned():
    source = (PACKAGE_ROOT / 'app/server.py').read_text(encoding='utf-8')
    prevalidation = source.index("if experiment_id == 'authority_mesh' and mesh_upload")
    allocation = source.index('job = create_job(workspace_root, profile, asset_id)')
    assert prevalidation < allocation
    assert "'jobPath'" not in source
    assert "'preparationLog'" not in source
    assert 'traceback.format_exc' not in source
    assert 'shutil.rmtree(job.root, ignore_errors=True)' in source


def test_all_browser_error_paths_redact_local_filesystem_paths():
    source = (PACKAGE_ROOT / 'app/server.py').read_text(encoding='utf-8')
    assert 'def _public_error' in source
    assert "return jsonify({'ok': False, 'error': str(exc)})" not in source
    assert "'Verified package is unavailable'" in source
    assert "return jsonify({'ok': False, 'error': _public_error(exc, root, workspace_root)})" in source


def test_browser_dynamic_status_and_filename_values_use_text_nodes():
    source = (PACKAGE_ROOT / 'app/templates/index.html').read_text(encoding='utf-8')
    assert 'node.textContent = String(text' in source
    assert 'node.innerHTML = text' not in source
    assert 'meta.innerHTML' not in source
    assert 'selectedAuthorityNote.innerHTML' not in source
    assert "href.startsWith('/api/jobs/')" in source


def test_vmp_export_is_local_only_probe_gated_and_collision_non_authoritative():
    server = (PACKAGE_ROOT / 'app/server.py').read_text(encoding='utf-8')
    template = (PACKAGE_ROOT / 'app/templates/index.html').read_text(encoding='utf-8')
    exporter = (PACKAGE_ROOT / 'app/vmp_job_export.py').read_text(encoding='utf-8')
    assert "@app.post('/api/jobs/<job_id>/vmp')" in server
    assert "@app.get('/api/jobs/<job_id>/vmp/download')" in server
    assert "body.get('approveCurrentArtifact') is not True" in server
    assert "resolve_import_probe_command(root)" in server
    assert "experiment.get(\"id\") != \"authority_mesh\"" in exporter
    assert "mesh.get(\"origin\") != \"generated_from_authority\"" in exporter
    assert "generator.get(\"generatorId\") != \"skyforge.authority-two-sided-field\"" in exporter
    assert 'Airborne — moving' in template
    assert 'Non-authoritative hint only' in template
    assert 'Meshy' not in template


def test_vmp_preserves_frozen_iou_floor_and_requires_consumer_receipt():
    pipeline = (PACKAGE_ROOT / 'app/pipeline.py').read_text(encoding='utf-8')
    exporter = (PACKAGE_ROOT / 'app/vmp_job_export.py').read_text(encoding='utf-8')
    assert "'blenderSilhouetteIoUMin': 0.94 if mesh_origin == 'generated_from_authority'" in pipeline
    assert 'BLENDER_SILHOUETTE_IOU_MIN = 0.94' in exporter
    assert 'Independent Sprite Foundry Import Probe did not accept the VMP' in exporter
    assert 'sourcePackageContentDigest' in exporter
    assert 'sourceArchiveSha256' in exporter


def test_import_probe_configuration_is_fixed_path_not_shell_execution():
    exporter = (PACKAGE_ROOT / 'app/vmp_job_export.py').read_text(encoding='utf-8')
    tree = ast.parse(exporter)
    assert 'shell=True' not in exporter
    assert 'scripts/run_import_probe.py' in exporter
    assert 'IMPORT_PROBE_SOURCE_BINDING.json' in exporter
    assert any(isinstance(node, ast.FunctionDef) and node.name == 'resolve_import_probe_command' for node in ast.walk(tree))


def test_mbs155_authority_suitability_and_lineage_checks_precede_all_execution_boundaries():
    server = (PACKAGE_ROOT / 'app/server.py').read_text(encoding='utf-8')
    jobs_route = server[server.index("@app.post('/api/jobs')"):]
    manual_gate = jobs_route.index("authority_validation = _validate_uploaded_authority")
    governed_gate = jobs_route.index("authority_validation = require_authority_suitability")
    allocation = jobs_route.index('job = create_job(workspace_root, profile, asset_id)')
    provider = jobs_route.index("provider = resolve_provider('local_deterministic')")
    blender = jobs_route.index('blender = resolve_blender_path(root)')
    thread = jobs_route.index('start_job_thread(root, job, manifest, blender)')
    assert manual_gate < allocation < provider < blender < thread
    assert governed_gate < allocation

    template = (PACKAGE_ROOT / 'app/templates/index.html').read_text(encoding='utf-8')
    assert 'id="manualAuthorityCertified"' in template
    assert "fetch('/api/authority/validate'" in template
    assert 'manualAuthorityValidationPassed' in template
    assert 'Perspective/3/4 uploads' not in template  # messaging remains user-readable rather than jargon-only


def test_mesh_form_and_job_submit_script_have_no_duplicate_controls_or_requests():
    template = (PACKAGE_ROOT / 'app/templates/index.html').read_text(encoding='utf-8')
    assert template.count('name="cameraPitchDegrees"') == 1
    assert template.count("const response = await fetch('/api/jobs'") == 1
    assert template.count('id="manualAuthorityCertified"') == 1
