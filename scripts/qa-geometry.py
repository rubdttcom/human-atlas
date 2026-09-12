"""Measure shipped geometry without turning unperformed anatomy checks into passes.

Specialised results already measured by qa-anatomy.py (self-intersections, connected components)
are carried over only for meshes whose `geometry_sha256` equals the one in the previous report
(scripts/qa_identity.py). Rows without a digest are never carried over: migrate an old report with
scripts/qa-hash-revision.py first. Everything else is `not-assessed` until qa-anatomy.py runs.
`--previous PATH` reads another report as the carry-over source.
"""
import json
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_identity import carry_over, geometry_digest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
previous_path = Path(sys.argv[sys.argv.index('--previous') + 1]) if '--previous' in sys.argv else ROOT / 'generated/qa-report.json'
previous = {(r['atlas'], r['structure']): r for r in json.loads(previous_path.read_text())['structures']} if previous_path.exists() else {}
reports = []
carried = 0
for source in ('hra-female', 'bodyparts3d', 'tcia', 'denver-vhf', 'nlm-vhf-ct', 'ct-consensus', 'composed'):
    atlas = json.loads((ROOT / 'public/atlases' / (source + '.json')).read_text())
    buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in atlas['chunks']]
    for part in atlas['parts']:
        data = buffers[part['chunk']]
        vertices = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3)
        normals = np.frombuffer(data, '<i2', count=part['vertexCount'] * 3, offset=part['normals']).reshape(-1, 3).astype(float) / 32767
        faces = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices']).reshape(-1, 3)
        assert np.isfinite(vertices).all() and faces.max() < len(vertices)
        face_vertices = vertices[faces].astype(float)
        cross = np.cross(face_vertices[:, 1] - face_vertices[:, 0], face_vertices[:, 2] - face_vertices[:, 0])
        areas = np.linalg.norm(cross, axis=1) / 2
        lengths = np.linalg.norm(normals, axis=1)
        bounds = np.array(part['bounds'])
        assert np.all(vertices >= bounds[0] - 1e-6) and np.all(vertices <= bounds[1] + 1e-6), part['id']
        # Edge incidence distinguishes open boundaries from non-manifold junctions.
        edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
        _, counts = np.unique(edges, axis=0, return_counts=True)
        digest = geometry_digest(vertices, faces)
        reports.append({'atlas': source, 'structure': part['id'], 'finite_vertices': True, 'valid_indices': True, 'geometry_sha256': digest,
                        'triangles': len(faces), 'degenerate_faces': int(np.count_nonzero(areas < 1e-14)),
                        'zero_normals': int(np.count_nonzero(lengths < 1e-4)),
                        'nonunit_normals': int(np.count_nonzero(abs(lengths - 1) > .02)),
                        'boundary_edges': int(np.count_nonzero(counts == 1)),
                        'nonmanifold_edges': int(np.count_nonzero(counts > 2)),
                        'signed_volume_m3': float(np.einsum('ij,ij->i', face_vertices[:, 0], cross).sum() / 6),
                        'self_intersections': 'not-assessed', 'anatomical_review': 'pending'})
        carried += carry_over(previous.get((source, part['id'])), reports[-1])
    print(f'{source}: geometry measurements complete', flush=True)
pending = sum(r['self_intersections'] == 'not-assessed' for r in reports)
report = {'structures': reports, 'anatomical_review': 'pending',
          'self_intersections': 'not-assessed' if pending == len(reports) else f'measured for {len(reports) - pending} of {len(reports)} meshes ({carried} carried over from identical geometry); {pending} not-assessed until qa-anatomy.py runs',
          'notes': 'Open or nonmanifold surfaces are reported individually; absence of failures is not anatomical validation.'}
(ROOT / 'generated/qa-report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'mesh_references': len(reports), 'self_intersections_carried_over': carried, 'self_intersections_not_assessed': pending, 'with_boundary_edges': sum(r['boundary_edges'] > 0 for r in reports),
                  'with_nonmanifold_edges': sum(r['nonmanifold_edges'] > 0 for r in reports),
                  'with_degenerate_faces': sum(r['degenerate_faces'] > 0 for r in reports)}))
