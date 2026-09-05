"""Anatomy-level QA that the geometry pass does not cover: self-intersections, outliers, continuity.

Outputs generated/anatomy-qa.json and fills the `self_intersections` field of generated/qa-report.json
with measured counts (previously "not-assessed"). Nothing here is an anatomical validation: a mesh
without self-intersections or outliers can still be anatomically wrong. Reviewer decisions live in
registry/review-status.json and are never inferred from these measurements.

Checks
1. Self-intersecting triangle pairs per mesh (edge-triangle Moller-Trumbore tests on candidate pairs
   from a k-d tree over triangle centroids; pairs sharing a vertex are skipped; coplanar pairs are
   counted separately as `coplanar_candidates`).
2. Connected-component outliers: components whose centroid lies farther from the largest component
   than `OUTLIER_MM` or above the top of the largest component by more than `OUTLIER_MM`.
3. Composite continuity: vertical gap between the HRA head structures and the CT skull/vertebrae in the
   canonical stage, and between the CT vertebral column and the Denver sacrum.
"""
import json
import sys
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
OUTLIER_MM = 60.0
CONTINUITY_ONLY = '--continuity-only' in sys.argv
atlases = [] if CONTINUITY_ONLY else (sys.argv[1:] or ['denver-vhf', 'tcia', 'nlm-vhf-ct', 'hra-female', 'composed', 'bodyparts3d'])


def load(name):
    atlas = json.loads((ROOT / 'public/atlases' / (name + '.json')).read_text())
    buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in atlas['chunks']]
    for part in atlas['parts']:
        data = buffers[part['chunk']]
        vertices = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3).astype(np.float64)
        faces = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices']).reshape(-1, 3).astype(np.int64)
        yield part, vertices, faces


def segment_hits_triangle(p0, p1, tri, eps=1e-12):
    """Moller-Trumbore segment/triangle test, vectorized over rows."""
    direction = p1 - p0
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    h = np.cross(direction, e2)
    a = np.einsum('ij,ij->i', e1, h)
    ok = np.abs(a) > eps
    f = np.where(ok, 1.0 / np.where(ok, a, 1.0), 0.0)
    s = p0 - tri[:, 0]
    u = f * np.einsum('ij,ij->i', s, h)
    q = np.cross(s, e1)
    v = f * np.einsum('ij,ij->i', direction, q)
    t = f * np.einsum('ij,ij->i', e2, q)
    return ok & (u >= -1e-9) & (u <= 1 + 1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t >= -1e-9) & (t <= 1 + 1e-9)


def tri_tri_intersect(a, b):
    """Non-coplanar triangle pairs intersect iff an edge of one crosses the other. a, b: (n, 3, 3).
    Returns (intersects, coplanar); coplanar pairs are reported separately and not resolved."""
    eps = 1e-12
    n2 = np.cross(b[:, 1] - b[:, 0], b[:, 2] - b[:, 0])
    du = np.einsum('ijk,ik->ij', a - b[:, 0][:, None, :], n2)
    n1 = np.cross(a[:, 1] - a[:, 0], a[:, 2] - a[:, 0])
    dv = np.einsum('ijk,ik->ij', b - a[:, 0][:, None, :], n1)
    scale_u = np.linalg.norm(n2, axis=1)[:, None] + eps
    scale_v = np.linalg.norm(n1, axis=1)[:, None] + eps
    coplanar = np.all(np.abs(du) / scale_u < 1e-9, axis=1) & np.all(np.abs(dv) / scale_v < 1e-9, axis=1)
    hit = np.zeros(len(a), dtype=bool)
    for i in range(3):
        hit |= segment_hits_triangle(a[:, i], a[:, (i + 1) % 3], b)
        hit |= segment_hits_triangle(b[:, i], b[:, (i + 1) % 3], a)
    return hit & ~coplanar, coplanar


def self_intersections(vertices, faces, chunk=400000):
    tri = vertices[faces]
    centroids = tri.mean(axis=1)
    radius = np.linalg.norm(tri - centroids[:, None], axis=2).max(axis=1)
    if len(faces) < 2:
        return 0, 0, 0
    # Candidate pairs: k-d tree over centroids for typical triangles; the few oversized triangles (long
    # slivers) are tested against every triangle by bounding-box overlap so the search radius stays small.
    typical_limit = 3 * np.median(radius)
    large = np.where(radius > typical_limit)[0]
    tree = cKDTree(centroids)
    pairs = tree.query_pairs(r=float(2 * min(radius.max(), typical_limit)), output_type='ndarray')
    if len(large):
        lo, hi = tri.min(axis=1), tri.max(axis=1)
        extra = []
        for index in large:
            overlap = np.all(lo[index] <= hi, axis=1) & np.all(hi[index] >= lo, axis=1)
            others = np.where(overlap)[0]
            others = others[others != index]
            extra.append(np.column_stack([np.full(len(others), index), others]))
        if extra:
            extra = np.vstack(extra)
            extra = np.sort(extra, axis=1)
            pairs = np.unique(np.vstack([pairs, extra]), axis=0) if len(pairs) else np.unique(extra, axis=0)
    if len(pairs) == 0:
        return 0, 0, 0
    close = np.linalg.norm(centroids[pairs[:, 0]] - centroids[pairs[:, 1]], axis=1) <= radius[pairs[:, 0]] + radius[pairs[:, 1]]
    pairs = pairs[close]
    fa, fb = faces[pairs[:, 0]], faces[pairs[:, 1]]
    shared = (fa[:, :, None] == fb[:, None, :]).any(axis=(1, 2))
    pairs = pairs[~shared]
    hits = coplanar = 0
    for start in range(0, len(pairs), chunk):
        block = pairs[start:start + chunk]
        inter, cop = tri_tri_intersect(tri[block[:, 0]], tri[block[:, 1]])
        hits += int(inter.sum())
        coplanar += int(cop.sum())
    return hits, coplanar, int(len(pairs))


def outliers(vertices, faces):
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    components = mesh.split(only_watertight=False)
    if len(components) <= 1:
        return {'components': len(components), 'outlier_components': []}
    components = sorted(components, key=lambda m: -len(m.faces))
    main = components[0]
    main_box = main.bounds
    flagged = []
    for component in components[1:]:
        centre = component.centroid
        gap = np.linalg.norm(np.maximum(0, np.maximum(main_box[0] - centre, centre - main_box[1]))) * 1000
        above = (component.bounds[0][1] - main_box[1][1]) * 1000
        if gap > OUTLIER_MM or above > OUTLIER_MM:
            flagged.append({'faces': len(component.faces), 'centroid_stage_m': centre.tolist(), 'distance_outside_main_box_mm': float(gap),
                            'above_main_top_mm': float(above), 'volume_mm3': float(abs(component.volume) * 1e9) if component.is_watertight else None})
    return {'components': len(components), 'main_component_faces': len(main.faces), 'outlier_components': flagged}


report = json.loads((ROOT / 'generated/anatomy-qa.json').read_text()) if CONTINUITY_ONLY else {'method': __doc__.strip(), 'outlier_threshold_mm': OUTLIER_MM, 'structures': []}
qa_path = ROOT / 'generated/qa-report.json'
qa = json.loads(qa_path.read_text())
qa_index = {(r['atlas'], r['structure']): r for r in qa['structures']}
for name in atlases:
    count = 0
    for part, vertices, faces in load(name):
        hits, coplanar, candidates = self_intersections(vertices, faces)
        outlier = outliers(vertices, faces)
        entry = {'atlas': name, 'structure': part['id'], 'triangles': len(faces), 'self_intersecting_pairs': hits, 'coplanar_candidates': coplanar,
                 'candidate_pairs_tested': candidates, **outlier}
        report['structures'].append(entry)
        if (name, part['id']) in qa_index:
            qa_index[(name, part['id'])]['self_intersections'] = f'{hits} intersecting triangle pairs (Moller test; {coplanar} coplanar candidates not resolved)'
            qa_index[(name, part['id'])]['connected_components'] = outlier['components']
            qa_index[(name, part['id'])]['outlier_components'] = len(outlier['outlier_components'])
        count += 1
        if count % 100 == 0:
            print(f'{name}: {count} meshes', flush=True)
    rows = [r for r in report['structures'] if r['atlas'] == name]
    print(f"{name}: {len(rows)} meshes, {sum(r['self_intersecting_pairs'] > 0 for r in rows)} with self-intersections, "
          f"{sum(bool(r['outlier_components']) for r in rows)} with outlier components", flush=True)

# Composite continuity in the canonical stage (metres, +y superior).
composed = json.loads((ROOT / 'public/atlases/composed.json').read_text())
parts = composed['parts']
def bounds_of(selector):
    boxes = np.array([p['bounds'] for p in parts if selector(p)])
    return None if len(boxes) == 0 else np.array([boxes[:, 0].min(axis=0), boxes[:, 1].max(axis=0)])
head = bounds_of(lambda p: p['provenance']['source'] == 'hra-female' and p['provenance']['registration']['transform_id'] == 'hra-head-to-vhf')
ct = lambda p: p['provenance']['source'] in ('nlm-vhf-ct', 'tcia')
skull = bounds_of(lambda p: ct(p) and p['provenance'].get('label_name', '').lower() == 'skull')
spine = bounds_of(lambda p: ct(p) and (p['provenance'].get('label_name', '').startswith('vertebrae_') or p['provenance'].get('label_name') == 'Spine'))
sacrum = bounds_of(lambda p: p['provenance']['source'] == 'denver-vhf' and p['provenance'].get('source_label') == 'Sacrum')
brain_like = bounds_of(lambda p: p['provenance']['source'] == 'hra-female' and p['id'].startswith('hra-female:Allen_'))
continuity = {
    'frame': 'VHF-image-2022 canonical stage, metres, +y superior',
    'hra_head_structures_bounds': head.tolist() if head is not None else None,
    'ct_skull_bounds': skull.tolist() if skull is not None else None,
    'ct_spine_bounds': spine.tolist() if spine is not None else None,
    'denver_sacrum_bounds': sacrum.tolist() if sacrum is not None else None,
    'hra_brain_inside_ct_skull_box': bool(np.all(brain_like[0] >= skull[0] - 1e-3) and np.all(brain_like[1] <= skull[1] + 1e-3)) if brain_like is not None and skull is not None else None,
    'hra_head_bottom_minus_spine_top_mm': float((head[0][1] - spine[1][1]) * 1000) if head is not None and spine is not None else None,
    'hra_head_bottom_minus_skull_bottom_mm': float((head[0][1] - skull[0][1]) * 1000) if head is not None and skull is not None else None,
    'ct_spine_bottom_minus_denver_sacrum_top_mm': float((spine[0][1] - sacrum[1][1]) * 1000) if spine is not None and sacrum is not None else None,
    'interpretation': 'Bounding-box gaps only. A negative head-bottom minus spine-top value means the HRA head structures overlap the top of the CT spine vertically; it does not establish cervical continuity, which needs anatomical review.',
}
report['composite_continuity'] = continuity
(ROOT / 'generated/anatomy-qa.json').write_text(json.dumps(report, indent=2) + '\n')
if not CONTINUITY_ONLY:
    qa['self_intersections'] = 'measured per mesh (see structures[].self_intersections and generated/anatomy-qa.json)'
    qa_path.write_text(json.dumps(qa, indent=2) + '\n')
print(json.dumps(continuity, indent=1))
