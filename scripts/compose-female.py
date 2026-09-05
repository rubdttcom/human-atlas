"""Build an auditable experimental female composition in the canonical VHF space (composition 0.4).

Canonical space `VHF-image-2022` is the aligned Visible Human Female image frame of the Denver 2022
release, shown through the Denver viewer stage (axis permutation and mm -> m only). Sources:

- Denver VHF (manual cryosection segmentation, lower limb): identity transform.
- NLM VHF fresh-CT TotalSegmentator labels (same donor, trunk, upper limb, head): already placed in
  the canonical stage by the rigid same-donor pelvis registration `nlm-ct-to-vhf`; identity here.
  Denver bones replace the CT hip bones, sacrum and femora; Denver muscles replace the CT gluteal and
  iliopsoas compartments.
- HRA female reference (detailed organs, vessels, nerves, reproductive and sensory anatomy, different
  donors): similarity fitted on six organ bounding-box proxies onto the same-donor CT organs, with a
  separate bounding-box fit of the head into the CT brain envelope. HRA parts whose reviewed ontology
  term is already covered by a CT label of the same donor are left out.
- TCIA 003 (another female donor): not composed. Its pelvic-landmark similarity onto Denver is kept
  as evidence and as the registration of the alternative source.

All fits are automatic and unreviewed: landmarks are geometric rules or bounding boxes, not anatomist
picks; CT labels are model output.
"""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'public/models'
CANONICAL = 'VHF-image-2022'
CANONICAL_STAGE = 'VHF-image-2022 canonical stage'
RNG = np.random.default_rng(2022)
hra = json.loads((ROOT / 'public/atlases/hra-female.json').read_text())
tcia = json.loads((ROOT / 'public/atlases/tcia.json').read_text())
denver = json.loads((ROOT / 'public/atlases/denver-vhf.json').read_text())
nlm = json.loads((ROOT / 'public/atlases/nlm-vhf-ct.json').read_text())
stage = json.loads((ROOT / 'transforms/source-to-stage.json').read_text())
nlm_ct_to_vhf = json.loads((ROOT / 'transforms/nlm-ct-to-vhf.json').read_text())
nlm_registration = json.loads((ROOT / 'generated/nlm-ct-registration.json').read_text())
landmark_sets = {name: json.loads((ROOT / 'transforms/landmarks' / (name + '.json')).read_text())
                 for name in ('denver-vhf', 'tcia-003', 'hra-female')}
hra_parts = {p['id']: p for p in hra['parts']}
nlm_by_label = {p['source_metadata']['label_name']: p for p in nlm['parts']}
PELVIC = ('anterior_superior_iliac_spine', 'iliac_crest_apex', 'ischial_tuberosity', 'pubic_symphysis_facet', 'femoral_head_centre')
assert nlm['labels_sha256'] == nlm_ct_to_vhf['labels_sha256'], 'NLM atlas and nlm-ct-to-vhf were built from different label maps'


def load_buffers(atlas):
    return [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in atlas['chunks']]


def geometry(atlas, buffers, part):
    data = buffers[part['chunk']]
    pos = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3)
    normals = np.frombuffer(data, '<i2', count=part['vertexCount'] * 3, offset=part['normals']).reshape(-1, 3)
    indices = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices'])
    return pos, normals, indices


def center(parts):
    boxes = np.array([p['bounds'] for p in parts])
    return (boxes[:, 0].min(axis=0) + boxes[:, 1].max(axis=0)) / 2


def apply(matrix, points):
    return np.asarray(points) @ matrix[:3, :3].T + matrix[:3, 3]


def similarity(pairs, source_key='source_point_m', target_key='target_point_m'):
    """Umeyama closed-form similarity (rotation, isotropic scale, translation); writes residuals into `pairs`."""
    source_points = np.array([p[source_key] for p in pairs])
    target_points = np.array([p[target_key] for p in pairs])
    x, y = source_points - source_points.mean(axis=0), target_points - target_points.mean(axis=0)
    u, singular, vt = np.linalg.svd(x.T @ y)
    correction = np.eye(3)
    correction[-1, -1] = np.linalg.det(vt.T @ u.T)
    rotation = vt.T @ correction @ u.T
    scale = np.sum(singular * correction.diagonal()) / np.sum(x * x)
    translation = target_points.mean(axis=0) - scale * rotation @ source_points.mean(axis=0)
    matrix = np.eye(4)
    matrix[:3, :3] = scale * rotation
    matrix[:3, 3] = translation
    distances = np.linalg.norm(apply(matrix, source_points) - target_points, axis=1)
    for pair, error in zip(pairs, distances):
        pair['residual_mm'] = float(error * 1000)
    return matrix, float(scale), distances


def landmark_pairs(source_set, target_set, names):
    target = {(l['side'], l['landmark']): l for l in target_set['landmarks']}
    pairs = []
    for item in source_set['landmarks']:
        key = (item['side'], item['landmark'])
        if item['landmark'] in names and key in target:
            pairs.append({'landmark': item['landmark'], 'side': item['side'], 'source_assets': item['source_assets'],
                          'target_assets': target[key]['source_assets'], 'source_point_m': item['point_stage_m'],
                          'target_point_m': target[key]['point_stage_m']})
    return pairs


def fit_record(fit_id, source, target, pairs, extra=None):
    matrix, scale, distances = similarity(pairs)
    record = {'id': fit_id, 'type': 'similarity', 'from': source, 'to': target, 'matrix_row_major': matrix.ravel().tolist(),
              'scale': scale, 'volume_scale': scale ** 3, 'surface_area_scale': scale ** 2, 'landmark_count': len(pairs),
              'landmarks': pairs, 'rms_mm': float(np.sqrt(np.mean(distances ** 2)) * 1000), 'max_residual_mm': float(distances.max() * 1000)}
    record.update(extra or {})
    return matrix, record


ALL_LANDMARKS = tuple(sorted({l['landmark'] for l in landmark_sets['denver-vhf']['landmarks']}))
landmark_provenance = {'method': 'automatic geometric rules on optimized viewer meshes (scripts/extract-landmarks.py)',
                       'marked_by': 'script, not an anatomist', 'manual_review': 'pending',
                       'files': ['transforms/landmarks/denver-vhf.json', 'transforms/landmarks/tcia-003.json', 'transforms/landmarks/hra-female.json']}

# 1. TCIA 003 -> VHF (evidence and alternative-source registration only; TCIA is not composed in 0.4).
tcia_pairs = landmark_pairs(landmark_sets['tcia-003'], landmark_sets['denver-vhf'], PELVIC)
tcia_matrix, tcia_transform = fit_record('tcia003-stage-to-vhf', 'TCIA 003 viewer stage', CANONICAL_STAGE, tcia_pairs)
pose_pairs = landmark_pairs(landmark_sets['tcia-003'], landmark_sets['denver-vhf'], ALL_LANDMARKS)
_, pose_fit = fit_record('tcia003-stage-to-vhf-all-landmarks-pose-check', 'TCIA 003 viewer stage', CANONICAL_STAGE, pose_pairs,
                         {'used_in_composition': False, 'purpose': 'Pose check: one similarity over pelvis, knee and ankle landmarks.'})
tcia_transform.update({
    'used_in_composition': False,
    'landmark_selection': 'pelvic: ' + ', '.join(PELVIC), 'landmark_provenance': landmark_provenance,
    'pose_check': {'all_landmark_rms_mm': pose_fit['rms_mm'], 'all_landmark_max_mm': pose_fit['max_residual_mm'],
                   'landmark_count': pose_fit['landmark_count'], 'fit': pose_fit,
                   'interpretation': 'Knee and ankle residuals of 50-80 mm under one similarity indicate a different lower-limb pose (TCIA 003 knees flexed, shank inclined), not a frame error.'},
    'review_status': 'experimental-unreviewed', 'canonical_registration': True,
    'limitations': ['Landmarks are automatic geometric rules on grouped CT labels split by connected components or midline sign; no anatomist has confirmed them.',
                    'Different donors (VHF, 59 years; TCIA 003, 26 years, 1.70 m) and poses; a similarity cannot remove pose differences.',
                    'Since composition 0.4 the composite uses the same-donor NLM CT instead of TCIA 003; this fit only positions the alternative source.']})

# 2. HRA -> same-donor CT organs (bounding-box proxies), directly in the canonical stage.
organ_pairs = []
for source_name, target_labels in [('heart', ['heart']), ('liver', ['liver']), ('spleen', ['spleen']), ('kidney', ['kidney_left', 'kidney_right']),
                                   ('urinary bladder', ['urinary_bladder']), ('pelvis', ['hip_left', 'hip_right', 'sacrum'])]:
    concept = next(c for c in hra['concepts'] if c['name'] == source_name)
    organ_pairs.append({'landmark': 'bounding-box centre', 'side': 'n/a', 'source_concept': concept['id'], 'target_labels': target_labels,
                        'source_assets': concept['elements'], 'target_assets': [nlm_by_label[l]['id'] for l in target_labels],
                        'source_point_m': center([hra_parts[i] for i in concept['elements']]).tolist(),
                        'target_point_m': center([nlm_by_label[l] for l in target_labels]).tolist()})
hra_matrix, hra_transform = fit_record('hra-stage-to-vhf', 'HRA viewer stage', CANONICAL_STAGE, organ_pairs,
                                       {'landmark_selection': 'bounding-box centres of six organ/pelvis proxies (targets: NLM VHF CT labels of the Denver donor)',
                                        'review_status': 'experimental-unreviewed', 'canonical_registration': True, 'used_in_composition': True,
                                        'limitations': ['Bounding-box centres are geometric proxies, not anatomical landmarks.',
                                                        'HRA is a multi-donor reference assembly; organ placement inside the VHF trunk is unreviewed.',
                                                        'Targets are automatic CT labels (TotalSegmentator) of the VHF donor, not reviewed organ surfaces.']})
hra_pelvic_pairs = landmark_pairs(landmark_sets['hra-female'], landmark_sets['denver-vhf'], PELVIC)
_, hra_direct_fit = fit_record('hra-stage-to-vhf-pelvic-crosscheck', 'HRA viewer stage', CANONICAL_STAGE, hra_pelvic_pairs,
                               {'used_in_composition': False, 'landmark_selection': 'pelvic: ' + ', '.join(PELVIC), 'landmark_provenance': landmark_provenance})
hra_direct_matrix = np.array(hra_direct_fit['matrix_row_major']).reshape(4, 4)
organ_offsets = []
for pair in organ_pairs:
    proxy = apply(hra_matrix, pair['source_point_m'])
    direct = apply(hra_direct_matrix, pair['source_point_m'])
    target = np.array(pair['target_point_m'])
    organ_offsets.append({'proxy': pair['source_concept'], 'ct_labels': pair['target_labels'],
                          'organ_fit_offset_mm': float(np.linalg.norm(proxy - target) * 1000), 'direct_pelvic_offset_mm': float(np.linalg.norm(direct - target) * 1000)})
hra_direct_fit['organ_offsets_vs_ct_in_vhf'] = organ_offsets
hra_direct_fit['interpretation'] = ('HRA pelvic landmarks fit the Denver pelvis closely (the HRA VH_F skeleton derives from the Visible Human Female), but the direct pelvic fit '
                                    'places HRA trunk organs away from the same-donor CT organs by the offsets listed; the organ-proxy fit is used for the composite.')
hra_transform['cross_checks'] = [hra_direct_fit]

# Head: HRA cranial structures follow a bounding-box fit into the same-donor CT brain envelope.
brain_parts = [p for p in hra['parts'] if p['id'].startswith('Allen_')]
brain_boxes = np.array([p['bounds'] for p in brain_parts])
source_brain_bounds = np.array([brain_boxes[:, 0].min(axis=0), brain_boxes[:, 1].max(axis=0)])
target_brain_bounds = np.array(nlm_by_label['brain']['bounds'])
head_scale = float(np.min((target_brain_bounds[1] - target_brain_bounds[0]) / (source_brain_bounds[1] - source_brain_bounds[0])))
head_matrix = np.eye(4)
head_matrix[:3, :3] *= head_scale
head_matrix[:3, 3] = target_brain_bounds.mean(axis=0) - head_scale * source_brain_bounds.mean(axis=0)
head_transform = {'id': 'hra-head-to-vhf', 'type': 'similarity-bounding-box-fit into the NLM VHF CT brain envelope', 'from': 'HRA viewer stage', 'to': CANONICAL_STAGE,
                  'matrix_row_major': head_matrix.ravel().tolist(), 'scale': head_scale, 'source_brain_bounds': source_brain_bounds.tolist(), 'target_brain_bounds': target_brain_bounds.tolist(),
                  'target_asset': nlm_by_label['brain']['id'], 'rms_mm': None, 'review_status': 'experimental-unreviewed', 'canonical_registration': True, 'used_in_composition': True,
                  'limitations': ['Brain bounding-box containment is not a surface registration or anatomical validation.',
                                  'The same transform is applied to cranial sensory structures; their placement and cervical continuity are unreviewed.']}
hra_transform['regional_transforms'] = [head_transform]
denver_transform = {'id': 'denver-stage-to-vhf', 'type': 'identity', 'from': 'Denver VHF viewer stage', 'to': CANONICAL_STAGE,
                    'matrix_row_major': np.eye(4).ravel().tolist(), 'scale': 1.0, 'rms_mm': 0.0, 'landmarks': [],
                    'review_status': 'canonical-by-definition; anatomy unreviewed', 'canonical_registration': True,
                    'definition': 'The canonical space is the Denver aligned VHF image frame; see transforms/canonical-space.json.'}
nlm_transform = {'id': 'nlm-stage-to-vhf', 'type': 'identity (the NLM CT source atlas is already expressed in the canonical stage through nlm-ct-to-vhf)',
                 'from': 'NLM VHF CT viewer stage', 'to': CANONICAL_STAGE, 'matrix_row_major': np.eye(4).ravel().tolist(), 'scale': 1.0,
                 'rms_mm': nlm_ct_to_vhf['rms_mm'], 'p95_mm': nlm_ct_to_vhf['p95_mm'], 'hausdorff_mm': nlm_ct_to_vhf['hausdorff_mm'], 'landmarks': [],
                 'components': [nlm_ct_to_vhf], 'same_donor': True, 'review_status': nlm_ct_to_vhf['review_status'], 'canonical_registration': True, 'used_in_composition': True,
                 'evidence': nlm_registration['canonical_space_verification']}

# 3. Bone-to-bone surface distances between Denver and TCIA (alternative source) and per-bone rigid shape comparisons.
denver_buffers, tcia_buffers, hra_buffers, nlm_buffers = load_buffers(denver), load_buffers(tcia), load_buffers(hra), load_buffers(nlm)


def denver_mesh(labels, folders=('Left', 'Right')):
    pieces = []
    for part in denver['parts']:
        meta = part['source_metadata']
        if meta['tissue_class'] == 'Bone' and meta['source_label'] in labels and meta['source_folder'] in folders:
            pos, _, idx = geometry(denver, denver_buffers, part)
            pieces.append(trimesh.Trimesh(pos.astype(float), idx.reshape(-1, 3), process=False))
    assert pieces, labels
    return trimesh.util.concatenate(pieces), [p['id'] for p in denver['parts'] if p['source_metadata']['tissue_class'] == 'Bone'
                                              and p['source_metadata']['source_label'] in labels and p['source_metadata']['source_folder'] in folders]


def tcia_mesh(names, matrix, side=None):
    pieces = []
    for part in tcia['parts']:
        if part['name'] in names:
            pos, _, idx = geometry(tcia, tcia_buffers, part)
            pieces.append(trimesh.Trimesh(apply(matrix, pos.astype(float)), idx.reshape(-1, 3), process=False))
    mesh = trimesh.util.concatenate(pieces)
    if side:
        components = sorted(mesh.split(only_watertight=False), key=lambda m: -len(m.faces))
        sign = 1 if side == 'left' else -1
        kept = [c for c in components if c.centroid[0] * sign > 0 and len(c.faces) >= 0.05 * len(components[0].faces)]
        mesh = trimesh.util.concatenate(kept) if kept else mesh
    return mesh


def samples(mesh, count=60000):
    points, _ = trimesh.sample.sample_surface(mesh, count, seed=int(RNG.integers(1 << 31)))
    return np.vstack([points, mesh.vertices])


def surface_distance(a, b):
    """Symmetric sampled surface distances a -> b and b -> a, in mm; the maximum approximates the Hausdorff distance."""
    pa, pb = samples(a), samples(b)
    ab = cKDTree(pb).query(pa)[0] * 1000
    ba = cKDTree(pa).query(pb)[0] * 1000
    def stats(d):
        return {'mean_mm': float(d.mean()), 'rms_mm': float(np.sqrt(np.mean(d ** 2))), 'p95_mm': float(np.quantile(d, .95)), 'max_mm': float(d.max())}
    return {'a_to_b': stats(ab), 'b_to_a': stats(ba), 'hausdorff_mm': float(max(ab.max(), ba.max())), 'samples_per_surface': int(len(pa)),
            'method': 'nearest neighbour between dense area-weighted surface samples plus vertices; sampled, not exact point-to-triangle'}


def envelope(denver_mesh_, tcia_mesh_, tolerance_mm=5.0):
    box = np.array([tcia_mesh_.vertices.min(axis=0), tcia_mesh_.vertices.max(axis=0)])
    excess = np.maximum(np.maximum(box[0] - denver_mesh_.vertices, denver_mesh_.vertices - box[1]), 0)
    outside = np.linalg.norm(excess, axis=1) * 1000
    return {'tcia_bounds_vhf_m': box.tolist(), 'tolerance_mm': tolerance_mm, 'fraction_inside': float(np.mean(outside <= tolerance_mm)),
            'max_excess_mm': float(outside.max()), 'inside': bool(outside.max() <= tolerance_mm)}


def shape_comparison(source_mesh, target_mesh):
    """Rigid ICP of the TCIA bone onto the Denver bone (no scale) after centroid alignment; measures donor bone shape difference only."""
    source_points = samples(source_mesh, 20000)
    target_points = samples(target_mesh, 60000)
    initial = np.eye(4)
    initial[:3, 3] = target_points.mean(axis=0) - source_points.mean(axis=0)
    matrix, moved, cost = trimesh.registration.icp(source_points, target_points, initial=initial, scale=False, max_iterations=50)
    moved_mesh = trimesh.Trimesh(apply(matrix, source_mesh.vertices), source_mesh.faces, process=False)
    return {'icp_rigid_matrix_row_major': matrix.ravel().tolist(), 'icp_translation_mm': (np.linalg.norm(matrix[:3, 3]) * 1000).item(),
            'icp_rotation_deg': float(np.degrees(np.arccos(np.clip((np.trace(matrix[:3, :3]) - 1) / 2, -1, 1)))),
            'after_rigid_icp': surface_distance(moved_mesh, target_mesh), 'purpose': 'donor bone-shape comparison after per-bone rigid alignment; not the composition transform'}


comparisons = []
groups = [('Hip bones', ('Pelvis',), ('Pelvis',), None), ('Femur', ('Femur',), ('Femur',), 'both'), ('Tibia', ('Tibia',), ('Tibia',), 'both'),
          ('Fibula', ('Fibula',), ('Fibula',), 'both')]
for label, denver_labels, tcia_names, sides in groups:
    for side in (('left', 'right') if sides else (None,)):
        folders = (side.capitalize(),) if side else ('Left', 'Right')
        d_mesh, d_ids = denver_mesh(denver_labels, folders)
        t_mesh = tcia_mesh(tcia_names, tcia_matrix, side)
        entry = {'structure': label + (f' ({side})' if side else ''), 'denver_assets': d_ids, 'tcia_labels': list(tcia_names),
                 'tcia_side_selection': 'connected components by centroid sign' if side else 'whole label',
                 'in_canonical_frame': surface_distance(d_mesh, t_mesh), 'denver_inside_tcia_envelope': envelope(d_mesh, t_mesh),
                 'shape_after_rigid_icp': shape_comparison(t_mesh, d_mesh)}
        comparisons.append(entry)
        print(f"{entry['structure']}: TCIA in-frame Hausdorff {entry['in_canonical_frame']['hausdorff_mm']:.1f} mm, p95 {entry['in_canonical_frame']['a_to_b']['p95_mm']:.1f} mm, "
              f"inside envelope {entry['denver_inside_tcia_envelope']['fraction_inside']:.3f}; shape p95 after ICP {entry['shape_after_rigid_icp']['after_rigid_icp']['a_to_b']['p95_mm']:.1f} mm", flush=True)
sacrum, sacrum_ids = denver_mesh(('Sacrum', 'Coccyx'), ('Left', 'Right'))
axial = tcia_mesh(('Pelvis', 'Spine'), tcia_matrix)
sacrum_distance = cKDTree(samples(axial)).query(samples(sacrum))[0] * 1000
comparisons.append({'structure': 'Sacrum and coccyx (one-directional)', 'denver_assets': sacrum_ids, 'tcia_labels': ['Pelvis', 'Spine'],
                    'denver_to_tcia': {'mean_mm': float(sacrum_distance.mean()), 'rms_mm': float(np.sqrt(np.mean(sacrum_distance ** 2))),
                                       'p95_mm': float(np.quantile(sacrum_distance, .95)), 'max_mm': float(sacrum_distance.max())},
                    'note': 'Which TCIA label holds the sacrum is unreviewed; distance is to the union of Pelvis and Spine.'})
pelvis_entry = comparisons[0]
tcia_transform['surface_distances'] = comparisons

# 4. Same-donor CT versus Denver in the canonical stage: distances of the CT labels that Denver replaces (no further fitting).
def nlm_mesh(labels):
    pieces = []
    for label in labels:
        pos, _, idx = geometry(nlm, nlm_buffers, nlm_by_label[label])
        pieces.append(trimesh.Trimesh(pos.astype(float), idx.reshape(-1, 3), process=False))
    return trimesh.util.concatenate(pieces)


same_donor = []
for label, denver_labels, folders, ct_labels in [('Hip bones', ('Pelvis',), ('Left', 'Right'), ['hip_left', 'hip_right']), ('Sacrum', ('Sacrum',), ('Left',), ['sacrum']),
                                                  ('Femur (left)', ('Femur',), ('Left',), ['femur_left']), ('Femur (right)', ('Femur',), ('Right',), ['femur_right'])]:
    d_mesh, d_ids = denver_mesh(denver_labels, folders)
    entry = {'structure': label, 'denver_assets': d_ids, 'ct_assets': [nlm_by_label[l]['id'] for l in ct_labels], 'in_canonical_frame': surface_distance(nlm_mesh(ct_labels), d_mesh)}
    same_donor.append(entry)
    print(f"{label}: same-donor CT vs Denver in frame p95 {entry['in_canonical_frame']['a_to_b']['p95_mm']:.1f} mm, Hausdorff {entry['in_canonical_frame']['hausdorff_mm']:.1f} mm", flush=True)
nlm_transform['surface_distances'] = same_donor
acceptance = {'criteria_source': 'docs/plans/female-open-human-atlas-plan.md section 29.2 and 29.3 item 3',
              'nlm_ct_pelvis_rigid_p95_below_5_mm': {'value_mm': nlm_ct_to_vhf['p95_mm'], 'met': nlm_ct_to_vhf['p95_mm'] < 5},
              'nlm_ct_frame_scale_within_1_percent': {'value': nlm_registration['canonical_space_verification']['free_scale'], 'met': abs(nlm_registration['canonical_space_verification']['free_scale'] - 1) < 0.01},
              'nlm_ct_frame_rotation_below_5_deg': {'value_deg': nlm_registration['canonical_space_verification']['rotation_deg'], 'met': nlm_registration['canonical_space_verification']['rotation_deg'] < 5},
              'tcia_pelvic_landmark_rms_below_15_mm': {'value_mm': tcia_transform['rms_mm'], 'met': tcia_transform['rms_mm'] < 15, 'note': 'Alternative source (TCIA 003), not composed.'},
              'tcia_all_lower_limb_landmark_rms_below_15_mm': {'value_mm': pose_fit['rms_mm'], 'met': pose_fit['rms_mm'] < 15,
                                                               'note': 'Not achievable with one similarity because of the TCIA 003 knee flexion; lower-limb bones come from Denver only.'},
              'denver_hip_bones_inside_tcia_pelvis_envelope': {'fraction_inside': pelvis_entry['denver_inside_tcia_envelope']['fraction_inside'],
                                                               'max_excess_mm': pelvis_entry['denver_inside_tcia_envelope']['max_excess_mm'],
                                                               'met': pelvis_entry['denver_inside_tcia_envelope']['inside']},
              'hra_organ_proxy_rms_below_30_mm': {'value_mm': hra_transform['rms_mm'], 'met': hra_transform['rms_mm'] < 30},
              'manual_landmark_review': 'pending', 'anatomical_review': 'pending'}
tcia_transform['acceptance'] = acceptance

# 5. Compose.
canonical_space = {'id': CANONICAL, 'definition': 'Aligned Visible Human Female image frame of the Denver 2022 release (Andreassen et al. 2022): +x subject right, +y anterior, +z superior, millimetres.',
                   'canonical_stage': CANONICAL_STAGE, 'image_to_stage': stage['denver-image-to-stage'],
                   'stage_axes': '+x subject left, +y superior, +z anterior, metres', 'reference_source': 'denver-vhf', 'reference_donor': 'VHF',
                   'evidence': ['transforms/source-to-stage.json#denver-image-to-stage', denver['frame_evidence'], 'generated/nlm-ct-registration.json#canonical_space_verification'],
                   'status': ('defined from the Denver aligned image frame; verified against the NLM VHF CT header frame by a rigid same-donor pelvis fit '
                              f"(rotation {nlm_registration['canonical_space_verification']['rotation_deg']:.2f} deg, free scale {nlm_registration['canonical_space_verification']['free_scale']:.4f}, pelvis p95 {nlm_ct_to_vhf['p95_mm']:.1f} mm)"),
                   'nlm_verification': nlm_registration['canonical_space_verification'],
                   'registered_sources': {'denver-vhf': 'denver-stage-to-vhf (identity)', 'nlm-vhf-ct': 'nlm-ct-to-vhf (rigid same-donor pelvis registration)',
                                          'hra-female': 'hra-stage-to-vhf (organ proxies onto same-donor CT organs, experimental)', 'tcia': 'tcia003-stage-to-vhf (pelvic landmark similarity, experimental; alternative source, not composed)'}}
(ROOT / 'transforms/canonical-space.json').write_text(json.dumps(canonical_space, indent=2) + '\n')
(ROOT / 'transforms/denver-stage-to-vhf.json').write_text(json.dumps(denver_transform, indent=2) + '\n')
(ROOT / 'transforms/nlm-stage-to-vhf.json').write_text(json.dumps(nlm_transform, indent=2) + '\n')
(ROOT / 'transforms/tcia003-stage-to-vhf.json').write_text(json.dumps(tcia_transform, indent=2) + '\n')
(ROOT / 'transforms/hra-stage-to-vhf.json').write_text(json.dumps(hra_transform, indent=2) + '\n')
chunks, parts, concepts, recipe = [], [], [], []
overrides = json.loads((ROOT / 'registry/composition-overrides.json').read_text())
known = {p['provenance']['id'] for a in (hra, tcia, denver, nlm) for p in a['parts']}
assert set(overrides) <= known, 'Unknown structure in composition overrides'
assert all(isinstance(value, bool) for value in overrides.values()), 'Overrides must be true or false'
blob = bytearray()


def append(array):
    while len(blob) % 4:
        blob.append(0)
    offset = len(blob)
    blob.extend(array.tobytes())
    return offset


def flush():
    if not blob:
        return
    name = f'composed-female-{len(chunks)}.bin'
    data = bytes(blob)
    compressed = gzip.compress(data, mtime=0)
    (OUT / name).write_bytes(data)
    (OUT / (name + '.gz')).write_bytes(compressed)
    chunks.append({'url': '/models/' + name, 'bytes': len(data), 'gzip': '/models/' + name + '.gz',
                   'gzipBytes': len(compressed), 'sha256': hashlib.sha256(data).hexdigest()})
    blob.clear()


def transform_geometry(matrix, pos, normals):
    pos = np.asarray(apply(matrix, pos), dtype='<f4')
    normal_vectors = normals @ np.linalg.inv(matrix[:3, :3])
    normal_vectors /= np.maximum(np.linalg.norm(normal_vectors, axis=1, keepdims=True), 1e-12)
    return pos, np.asarray(np.clip(normal_vectors * 32767, -32767, 32767), dtype='<i2')


def term_of(part):
    return part['provenance']['structure_id'].split('|')[0]


DENVER_REPLACES_CT = {'hip_left', 'hip_right', 'sacrum', 'femur_left', 'femur_right', 'gluteus_maximus_left', 'gluteus_maximus_right', 'gluteus_medius_left', 'gluteus_medius_right',
                      'gluteus_minimus_left', 'gluteus_minimus_right', 'iliopsoas_left', 'iliopsoas_right'}
ct_included_terms = {term_of(p) for p in nlm['parts'] if p['source_metadata']['label_name'] not in DENVER_REPLACES_CT and not term_of(p).startswith('NLMCT:')}
for atlas, buffers, source_id in [(hra, hra_buffers, 'hra-female'), (nlm, nlm_buffers, 'nlm-vhf-ct'), (denver, denver_buffers, 'denver-vhf'), (tcia, tcia_buffers, 'tcia')]:
    id_map = {}
    for original in atlas['parts']:
        if source_id == 'hra-female':
            include = original['system'] != 'skeletal' and original['id'] != 'VH_F_skin'
            reason = 'Detailed female reference anatomy absent from the same-donor CT labels; CT skeleton replaces the HRA skeleton; mismatched-pose skin excluded.'
            if include and original['system'] == 'muscular' and original['bounds'][1][1] < 1.05:
                include = False
                reason = 'Lower-limb reference muscle replaced by the Denver VHF manual segmentation (priority 1 female donor geometry).'
            if include and term_of(original) in ct_included_terms:
                include = False
                reason = 'Reference organ replaced by the same-donor NLM VHF CT label with the same reviewed ontology term.'
        elif source_id == 'nlm-vhf-ct':
            include = original['source_metadata']['label_name'] not in DENVER_REPLACES_CT
            reason = 'Same-donor automatic CT label (trunk, upper limb, head); rigid pelvis registration to the Denver frame.'
            if not include:
                reason = 'CT label replaced by the Denver VHF manual segmentation of the same donor (bones and gluteal/iliopsoas muscles).'
        elif source_id == 'denver-vhf':
            include = True
            reason = 'Denver VHF lower-limb bones, muscles, cartilage and ligaments: measured female geometry in the canonical frame, best available source for the region.'
        else:
            include = False
            reason = 'TCIA 003 is another donor; since composition 0.4 the same-donor NLM CT labels provide the trunk. Kept as an alternative source with its own experimental registration.'
        if original['provenance']['id'] in overrides:
            include = overrides[original['provenance']['id']]
            reason = 'Explicit per-structure composition override'
        recipe.append({'source': source_id, 'source_asset': original['id'], 'included': include, 'reason': reason})
        if not include:
            continue
        part = copy.deepcopy(original)
        part['id'] = part['provenance']['id']
        id_map[original['id']] = part['id']
        pos, normals, indices = geometry(atlas, buffers, original)
        record = part['provenance']
        record['canonical_space'] = CANONICAL
        record['display_space'] = CANONICAL_STAGE
        if source_id == 'hra-female':
            regional = (original['id'].startswith('Allen_') or original['system'] == 'sensory' or original['bounds'][0][1] >= source_brain_bounds[0, 1])
            active_matrix = head_matrix if regional else hra_matrix
            active = head_transform if regional else hra_transform
            pos, normals = transform_geometry(active_matrix, pos, normals)
            record['registration'] = {'type': 'experimental similarity on organ bounding-box proxies onto same-donor CT labels' if not regional else 'experimental head bounding-box fit into the same-donor CT brain envelope',
                                      'transform_id': active['id'], 'display_transform_id': active['id'], 'rms_mm': active['rms_mm'],
                                      'canonical_registration': True, 'review_status': 'unreviewed'}
            record['notes'] += (' Experimental head bounding-box fit into the VHF CT brain envelope; cranial and cervical continuity unreviewed.' if regional
                                else f" Experimental registration into the VHF canonical space on organ proxies (RMS {hra_transform['rms_mm']:.1f} mm). Not anatomically reviewed.")
        elif source_id == 'nlm-vhf-ct':
            record['registration'] = {'type': 'rigid same-donor pelvis registration (nlm-ct-to-vhf); identity in the canonical stage', 'transform_id': nlm_transform['id'],
                                      'display_transform_id': nlm_transform['id'], 'rms_mm': nlm_transform['rms_mm'], 'canonical_registration': True,
                                      'review_status': 'automatic same-donor registration; anatomy unreviewed'}
            record['notes'] += f" Composite placement by the rigid pelvis fit of the same donor (p95 {nlm_ct_to_vhf['p95_mm']:.1f} mm). Automatic label, not anatomically reviewed."
        elif source_id == 'tcia':
            pos, normals = transform_geometry(tcia_matrix, pos, normals)
            record['registration'] = {'type': 'experimental similarity on automatic pelvic bone landmarks', 'transform_id': tcia_transform['id'],
                                      'display_transform_id': tcia_transform['id'], 'rms_mm': tcia_transform['rms_mm'], 'canonical_registration': True, 'review_status': 'unreviewed'}
        else:
            record['registration'] = {'type': 'identity; source frame defines the canonical space', 'transform_id': denver_transform['id'],
                                      'display_transform_id': denver_transform['id'], 'rms_mm': 0.0, 'canonical_registration': True,
                                      'review_status': 'canonical-by-definition; anatomy unreviewed'}
            record['notes'] += ' Shown in its native aligned VHF image frame, which defines canonical space VHF-image-2022.'
        if len(blob) > 4_000_000:
            flush()
        part.update({'chunk': len(chunks), 'positions': append(pos), 'normals': append(normals), 'indices': append(indices),
                     'bounds': [pos.min(axis=0).tolist(), pos.max(axis=0).tolist()]})
        parts.append(part)
        concepts.append({'id': part['id'], 'name': part['name'], 'elements': [part['id']]})
    for concept in atlas['concepts']:
        if len(concept['elements']) > 1 and all(i in id_map for i in concept['elements']):
            concepts.append({'id': source_id + ':' + concept['id'], 'name': concept['name'], 'elements': [id_map[i] for i in concept['elements']]})
flush()
for part in parts:
    part['provenance']['derived_chunk_sha256'] = chunks[part['chunk']]['sha256']
by_source = {}
for part in parts:
    by_source[part['provenance']['source']] = by_source.get(part['provenance']['source'], 0) + 1
by_donor = {}
for part in parts:
    by_donor[part['provenance']['source_donor']] = by_donor.get(part['provenance']['source_donor'], 0) + 1
report = {'canonical_space': canonical_space, 'transforms': [hra_transform, nlm_transform, denver_transform, tcia_transform], 'acceptance': acceptance,
          'composition': {'meshes_by_source': by_source, 'meshes_by_donor': by_donor}}
composed = {'version': 'Female composition 0.4 experimental', 'sex': 'female', 'source': 'Denver VHF + NLM VHF CT + HRA',
            'scope': 'Experimental multi-source assembly in canonical space VHF-image-2022: one donor (VHF) for the skeleton, lower limb and trunk organs, HRA reference detail registered experimentally; automatic labels and fits, unreviewed',
            'parts': parts, 'concepts': concepts, 'chunks': chunks, 'triangles': sum(p['indexCount'] // 3 for p in parts),
            'canonical_space': CANONICAL, 'registration_report': report}
(ROOT / 'public/atlases/composed.json').write_text(json.dumps(composed, indent=2) + '\n')
(ROOT / 'registry/composition-recipe.json').write_text(json.dumps(recipe, indent=2) + '\n')
(ROOT / 'generated/registration-report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'meshes': len(parts), 'triangles': composed['triangles'], 'canonical_space': CANONICAL, 'meshes_by_source': by_source, 'meshes_by_donor': by_donor,
                  'nlm_pelvis_p95_mm': nlm_ct_to_vhf['p95_mm'], 'hra_organ_proxy_rms_mm': hra_transform['rms_mm'], 'hra_direct_pelvic_rms_mm': hra_direct_fit['rms_mm'],
                  'tcia_pelvic_rms_mm': tcia_transform['rms_mm'], 'acceptance': {k: v['met'] for k, v in acceptance.items() if isinstance(v, dict) and 'met' in v}}, indent=2))
