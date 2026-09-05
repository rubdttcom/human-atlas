"""Validate composed buffers against the recorded source-to-canonical transforms and landmark evidence (composition 0.4)."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = 'VHF-image-2022'
atlas = json.loads((ROOT / 'public/atlases/composed.json').read_text())
transforms = {name: json.loads((ROOT / 'transforms' / (name + '.json')).read_text())
              for name in ('denver-stage-to-vhf', 'nlm-stage-to-vhf', 'tcia003-stage-to-vhf', 'hra-stage-to-vhf')}
nlm_ct_to_vhf = json.loads((ROOT / 'transforms/nlm-ct-to-vhf.json').read_text())
canonical_space = json.loads((ROOT / 'transforms/canonical-space.json').read_text())
landmarks = {name: json.loads((ROOT / 'transforms/landmarks' / (name + '.json')).read_text())
             for name in ('denver-vhf', 'tcia-003', 'hra-female')}
matrices = {t['id']: np.array(t['matrix_row_major']).reshape(4, 4) for t in transforms.values()}
for regional in transforms['hra-stage-to-vhf']['regional_transforms']:
    matrices[regional['id']] = np.array(regional['matrix_row_major']).reshape(4, 4)
source_atlases = {key: json.loads((ROOT / 'public/atlases' / (key + '.json')).read_text()) for key in ('hra-female', 'tcia', 'denver-vhf', 'nlm-vhf-ct')}
source_parts = {p['provenance']['id']: p for a in source_atlases.values() for p in a['parts']}
cache = {}


def buffer(url):
    if url not in cache:
        cache[url] = (ROOT / 'public' / url.lstrip('/')).read_bytes()
    return cache[url]


def vertices_of(atlas_, part):
    data = buffer(atlas_['chunks'][part['chunk']]['url'])
    return np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3)


# Canonical space definition: identity for Denver and for the NLM CT source (already in the canonical stage), stage matrix recorded.
assert atlas['canonical_space'] == CANONICAL and canonical_space['id'] == CANONICAL
assert np.allclose(matrices['denver-stage-to-vhf'], np.eye(4)) and transforms['denver-stage-to-vhf']['canonical_registration']
assert np.allclose(matrices['nlm-stage-to-vhf'], np.eye(4)) and transforms['nlm-stage-to-vhf']['canonical_registration']
stage = json.loads((ROOT / 'transforms/source-to-stage.json').read_text())
assert canonical_space['image_to_stage']['matrix_row_major'] == stage['denver-image-to-stage']['matrix_row_major']
# The NLM source atlas voxel->stage matrix equals denver-image-to-stage @ nlm-ct-to-vhf @ CT affine, and the label map hashes agree.
nlm_atlas = source_atlases['nlm-vhf-ct']
expected_voxel_to_stage = np.array(stage['denver-image-to-stage']['matrix_row_major']).reshape(4, 4) @ np.array(nlm_ct_to_vhf['matrix_row_major']).reshape(4, 4) @ np.array(nlm_atlas['source_affine'])
assert np.allclose(expected_voxel_to_stage, np.array(nlm_atlas['voxel_to_stage']), atol=1e-9)
assert nlm_atlas['labels_sha256'] == nlm_ct_to_vhf['labels_sha256'] == transforms['nlm-stage-to-vhf']['components'][0]['labels_sha256']
assert nlm_ct_to_vhf['scale'] == 1.0 and nlm_ct_to_vhf['rotation_deg'] < 5, 'same-donor CT registration must be rigid and close to the header frame'
verification = canonical_space['nlm_verification']
assert verification['axes_and_units'] == 'consistent' and abs(verification['free_scale'] - 1) < 0.01

for chunk in atlas['chunks']:
    data = buffer(chunk['url'])
    assert len(data) == chunk['bytes']
    assert hashlib.sha256(data).hexdigest() == chunk['sha256']
ids = set()
expected_ids = {'denver-vhf': {'denver-stage-to-vhf'}, 'nlm-vhf-ct': {'nlm-stage-to-vhf'}, 'tcia': {'tcia003-stage-to-vhf'}, 'hra-female': {'hra-stage-to-vhf', 'hra-head-to-vhf'}}
for part in atlas['parts']:
    record = part['provenance']
    original = source_parts[record['id']]
    assert part['id'] not in ids
    ids.add(part['id'])
    assert record['canonical_space'] == CANONICAL and record['registration']['canonical_registration']
    data = buffer(atlas['chunks'][part['chunk']]['url'])
    source = source_atlases[record['source']]
    raw = buffer(source['chunks'][original['chunk']]['url'])
    vertices = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3)
    indices = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices'])
    original_vertices = np.frombuffer(raw, '<f4', count=original['vertexCount'] * 3, offset=original['positions']).reshape(-1, 3)
    original_indices = np.frombuffer(raw, '<u4', count=original['indexCount'], offset=original['indices'])
    assert np.array_equal(indices, original_indices)
    transform_id = record['registration']['transform_id']
    assert transform_id in expected_ids[record['source']], part['id']
    active_matrix = matrices[transform_id]
    expected = original_vertices @ active_matrix[:3, :3].T + active_matrix[:3, 3]
    if record['source'] in ('denver-vhf', 'nlm-vhf-ct'):
        assert np.array_equal(vertices, original_vertices), part['id']
    assert np.allclose(vertices, expected, rtol=1e-6, atol=1e-7), part['id']
    assert np.isfinite(vertices).all()
    assert indices.max() < len(vertices)
for concept in atlas['concepts']:
    assert concept['elements'] and set(concept['elements']) <= ids

# Landmark and proxy fits: recorded residuals and RMS follow from the recorded points and matrices.
fits = [transforms['tcia003-stage-to-vhf'], transforms['tcia003-stage-to-vhf']['pose_check']['fit'], transforms['hra-stage-to-vhf']] + transforms['hra-stage-to-vhf']['cross_checks']
for fit in fits:
    fit_matrix = np.array(fit['matrix_row_major']).reshape(4, 4)
    errors = np.array([np.linalg.norm(fit_matrix[:3, :3] @ p['source_point_m'] + fit_matrix[:3, 3] - p['target_point_m']) * 1000 for p in fit['landmarks']])
    assert np.allclose(errors, [p['residual_mm'] for p in fit['landmarks']], atol=1e-6), fit['id']
    assert abs(np.sqrt(np.mean(errors ** 2)) - fit['rms_mm']) < 1e-6 and abs(errors.max() - fit['max_residual_mm']) < 1e-6, fit['id']
    assert fit['landmark_count'] == len(fit['landmarks'])
# Organ proxies reference existing HRA and NLM assets and their bounding-box centres.
nlm_parts = {p['id']: p for p in nlm_atlas['parts']}
hra_parts = {p['id']: p for p in source_atlases['hra-female']['parts']}
for pair in transforms['hra-stage-to-vhf']['landmarks']:
    boxes = np.array([nlm_parts[i]['bounds'] for i in pair['target_assets']])
    assert np.allclose((boxes[:, 0].min(axis=0) + boxes[:, 1].max(axis=0)) / 2, pair['target_point_m'])
    boxes = np.array([hra_parts[i]['bounds'] for i in pair['source_assets']])
    assert np.allclose((boxes[:, 0].min(axis=0) + boxes[:, 1].max(axis=0)) / 2, pair['source_point_m'])
# Landmark points come from the recorded meshes: slab centroids lie within 10 mm of a source vertex (recorded), sphere centres inside the bone box.
source_vertices = {}
for key, atlas_ in source_atlases.items():
    if key == 'nlm-vhf-ct':
        continue
    for part in atlas_['parts']:
        source_vertices[part['id']] = (vertices_of(atlas_, part), np.array(part['bounds']))
for name, landmark_set in landmarks.items():
    assert landmark_set['manual_review'] == 'pending'
    for item in landmark_set['landmarks']:
        point = np.array(item['point_stage_m'])
        assert item['marked_by'].startswith('scripts/extract-landmarks.py') and item['manual_review'] == 'pending'
        vertices = np.vstack([source_vertices[a][0] for a in item['source_assets']])
        bounds = np.array([np.min([source_vertices[a][1][0] for a in item['source_assets']], axis=0), np.max([source_vertices[a][1][1] for a in item['source_assets']], axis=0)])
        if item.get('on_surface', True):
            nearest = np.min(np.linalg.norm(vertices - point, axis=1)) * 1000
            assert abs(nearest - item['nearest_source_vertex_mm']) < 1e-6 and nearest < 10, (name, item['landmark'], item['side'], nearest)
        else:
            assert np.all(point >= bounds[0]) and np.all(point <= bounds[1]), (name, item['landmark'], item['side'])
            assert 0.015 < item['sphere_radius_mm'] / 1000 < 0.035, (name, item['landmark'])
tcia_pairs = transforms['tcia003-stage-to-vhf']['landmarks']
assert len(tcia_pairs) == 10 and {p['landmark'] for p in tcia_pairs} == {'anterior_superior_iliac_spine', 'iliac_crest_apex', 'ischial_tuberosity', 'pubic_symphysis_facet', 'femoral_head_centre'}
recorded = {(l['side'], l['landmark']): l['point_stage_m'] for l in landmarks['tcia-003']['landmarks']}
target = {(l['side'], l['landmark']): l['point_stage_m'] for l in landmarks['denver-vhf']['landmarks']}
for pair in tcia_pairs:
    assert pair['source_point_m'] == recorded[(pair['side'], pair['landmark'])] and pair['target_point_m'] == target[(pair['side'], pair['landmark'])]
acceptance = transforms['tcia003-stage-to-vhf']['acceptance']
assert acceptance['tcia_pelvic_landmark_rms_below_15_mm']['met'] == (transforms['tcia003-stage-to-vhf']['rms_mm'] < 15)
assert acceptance['nlm_ct_pelvis_rigid_p95_below_5_mm']['met'] == (nlm_ct_to_vhf['p95_mm'] < 5)
assert acceptance['manual_landmark_review'] == 'pending' and acceptance['anatomical_review'] == 'pending'

sources = {p['provenance']['source'] for p in atlas['parts']}
assert 'tcia' not in sources, 'TCIA 003 (another donor) must not be composed in 0.4'
denver_ids = {p['id'] for p in atlas['parts'] if p['provenance']['source'] == 'denver-vhf'}
assert len(denver_ids) == len(source_atlases['denver-vhf']['parts']), 'Every Denver mesh should be in the composition'
ct_labels = {p['provenance']['label_name'] for p in atlas['parts'] if p['provenance']['source'] == 'nlm-vhf-ct'}
assert not ct_labels & {'hip_left', 'hip_right', 'sacrum', 'femur_left', 'femur_right'}, 'CT pelvis and femora must be replaced by Denver bones'
assert {'skull', 'brain', 'heart', 'liver', 'vertebrae_L1'} <= ct_labels, 'trunk and head CT labels expected in the composite'
ct_terms = {p['provenance']['structure_id'].split('|')[0] for p in atlas['parts'] if p['provenance']['source'] == 'nlm-vhf-ct'}
for part in atlas['parts']:
    if part['provenance']['source'] == 'hra-female':
        assert part['provenance']['structure_id'].split('|')[0] not in ct_terms or part['provenance']['structure_id'].startswith('HRA:'), f"HRA {part['id']} duplicates a same-donor CT term"
brain_parts = [p for p in atlas['parts'] if p['provenance']['source_asset'].startswith('Allen_')]
brain_bounds = np.array([p['bounds'] for p in brain_parts])
box = np.array([brain_bounds[:, 0].min(axis=0), brain_bounds[:, 1].max(axis=0)])
ct_brain = next(p for p in atlas['parts'] if p['provenance']['source'] == 'nlm-vhf-ct' and p['provenance']['label_name'] == 'brain')
target_box = np.array(ct_brain['bounds'])
assert np.all(box[0] >= target_box[0] - 1e-3) and np.all(box[1] <= target_box[1] + 1e-3), 'Brain bounds leave the CT brain envelope'
by_donor = atlas['registration_report']['composition']['meshes_by_donor']
print(f"Verified {len(ids)} composed meshes in {CANONICAL}: unchanged topology, Denver and NLM CT identity (same donor, rigid pelvis fit p95 {nlm_ct_to_vhf['p95_mm']:.2f} mm, "
      f"frame rotation {nlm_ct_to_vhf['rotation_deg']:.2f} deg), HRA organ-proxy fit RMS {transforms['hra-stage-to-vhf']['rms_mm']:.2f} mm; donors {by_donor}. "
      f"Landmarks and anatomy remain unreviewed; acceptance: {', '.join(k + '=' + str(v['met']) for k, v in acceptance.items() if isinstance(v, dict) and 'met' in v)}.")
