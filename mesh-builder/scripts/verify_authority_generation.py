from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from app.authority_mesh import ACCEPTANCE_GATES, generate_authority_mesh

ROOT = Path(__file__).resolve().parents[1]
AUTHORITIES = [
    ROOT / 'samples' / 'approved_gunship_authority.png',
    ROOT / 'samples' / 'user_test_gunship_authority.png',
]


def independent_obj_audit(path: Path) -> dict[str, int | bool]:
    vertex_count = 0
    faces: list[tuple[int, int, int]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('v '):
            vertex_count += 1
        elif line.startswith('f '):
            face = tuple(int(part.split('/')[0]) for part in line.split()[1:])
            if len(face) != 3:
                raise RuntimeError('Generated OBJ contains a non-triangle face')
            faces.append(face)
    edges: Counter[tuple[int, int]] = Counter()
    for a, b, c in faces:
        for first, second in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted((first, second)))] += 1
    boundary = sum(value == 1 for value in edges.values())
    non_manifold = sum(value > 2 for value in edges.values())
    return {
        'vertexCount': vertex_count,
        'triangleCount': len(faces),
        'boundaryEdgeCount': boundary,
        'nonManifoldEdgeCount': non_manifold,
        'watertightByIndependentAudit': boundary == 0 and non_manifold == 0,
    }


def main() -> None:
    results = []
    for authority in AUTHORITIES:
        temporary = Path(tempfile.mkdtemp(prefix='skyforge-authority-mesh-'))
        try:
            generated = generate_authority_mesh(authority, temporary)
            report = generated.report
            audit = independent_obj_audit(generated.obj_path)
            coordinate = report['mesh']['coordinateContract']
            failures: list[str] = []
            if not report['gateResults']['passed']:
                failures.append('generator gates')
            if report['identityMetrics']['silhouetteIoU'] < ACCEPTANCE_GATES['silhouetteIoUMin']:
                failures.append('target silhouette IoU')
            if report['blenderImportIdentityMetrics']['silhouetteIoU'] < ACCEPTANCE_GATES['blenderImportSilhouetteIoUMin']:
                failures.append('emulated Blender-import silhouette IoU')
            if coordinate['blenderImportBoundsDelta'] > ACCEPTANCE_GATES['blenderImportBoundsDeltaMax']:
                failures.append('Blender-import bounds reconciliation')
            if coordinate['blenderImportHeightToPlanformRatio'] > ACCEPTANCE_GATES['heightToPlanformRatioMax']:
                failures.append('Blender-import orientation')
            if not audit['watertightByIndependentAudit']:
                failures.append('independent topology audit')
            if audit['vertexCount'] != report['mesh']['vertexCount']:
                failures.append('vertex-count reconciliation')
            if audit['triangleCount'] != report['mesh']['triangleCount']:
                failures.append('triangle-count reconciliation')
            if failures:
                raise RuntimeError(f'Authority mesh self-test failed for {authority.name}: ' + ', '.join(failures))
            results.append({
                'authority': authority.name,
                'authoritySha256': report['source']['authoritySha256'],
                'targetSilhouetteIoU': report['identityMetrics']['silhouetteIoU'],
                'blenderImportSilhouetteIoU': report['blenderImportIdentityMetrics']['silhouetteIoU'],
                'blenderImportBoundsDelta': coordinate['blenderImportBoundsDelta'],
                'heightToPlanformRatio': coordinate['blenderImportHeightToPlanformRatio'],
                'independentAudit': audit,
            })
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps({'result': 'PASS', 'authorities': results}, indent=2))


if __name__ == '__main__':
    main()
