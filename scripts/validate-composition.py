"""Validate composed buffers against the recorded source-to-display transform."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
atlas = json.loads((ROOT / 'public/atlases/composed.json').read_text())
transform = json.loads((ROOT / 'transforms/hra-stage-to-tcia003-initial.json').read_text())
matrix = np.array(transform['matrix_row_major']).reshape(4, 4)
regional = {r['id']: np.array(r['matrix_row_major']).reshape(4, 4)
            for r in transform.get('regional_transforms', []) + transform.get('additional_source_transforms', [])}
source_atlases = {key: json.loads((ROOT / 'public/atlases' / (key + '.json')).read_text()) for key in ('hra-female', 'tcia', 'denver-vhf')}
source_parts = {p['provenance']['id']: p for a in source_atlases.values() for p in a['parts']}
cache = {}


def buffer(url):
    if url not in cache:
        cache[url] = (ROOT / 'public' / url.lstrip('/')).read_bytes()
    return cache[url]


for chunk in atlas['chunks']:
    data = buffer(chunk['url'])
    assert len(data) == chunk['bytes']
    assert hashlib.sha256(data).hexdigest() == chunk['sha256']
ids = set()
for part in atlas['parts']:
    record = part['provenance']
    original = source_parts[record['id']]
    assert part['id'] not in ids
    ids.add(part['id'])
    assert record['canonical_space'] is None
    data = buffer(atlas['chunks'][part['chunk']]['url'])
    source = source_atlases[record['source']]
    raw = buffer(source['chunks'][original['chunk']]['url'])
    vertices = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3)
    indices = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices'])
    original_vertices = np.frombuffer(raw, '<f4', count=original['vertexCount'] * 3, offset=original['positions']).reshape(-1, 3)
    original_indices = np.frombuffer(raw, '<u4', count=original['indexCount'], offset=original['indices'])
    assert np.array_equal(indices, original_indices)
    active_matrix = regional.get(record['registration']['transform_id'], matrix)
    if record['source'] == 'tcia':
        assert record['registration']['transform_id'] is None
        expected = original_vertices
    else:
        assert record['source'] == 'hra-female' or record['registration']['transform_id'] == 'denver-stage-to-tcia003-initial'
        expected = original_vertices @ active_matrix[:3, :3].T + active_matrix[:3, 3]
    assert np.allclose(vertices, expected, rtol=1e-6, atol=1e-7), part['id']
    assert np.isfinite(vertices).all()
    assert indices.max() < len(vertices)
for concept in atlas['concepts']:
    assert concept['elements'] and set(concept['elements']) <= ids
for fit in [transform] + transform.get('additional_source_transforms', []):
    fit_matrix = np.array(fit['matrix_row_major']).reshape(4, 4)
    errors = [np.linalg.norm(fit_matrix[:3, :3] @ p['source_center_m'] + fit_matrix[:3, 3] - p['target_center_m']) * 1000 for p in fit['landmarks']]
    assert abs(np.sqrt(np.mean(np.square(errors))) - fit['rms_mm']) < 1e-6, fit['id']
denver_ids = {p['id'] for p in atlas['parts'] if p['provenance']['source'] == 'denver-vhf'}
assert len(denver_ids) == len(source_atlases['denver-vhf']['parts']), 'Every Denver mesh should be in the composition'
replaced = {p['provenance']['label_name'] for p in atlas['parts'] if p['provenance']['source'] == 'tcia'}
assert not replaced & {'Femur', 'Fibula', 'Metatarsal', 'Patella', 'Pelvis', 'Tarsal', 'Tibia', 'Toes'}, 'TCIA lower-limb labels should be replaced by Denver bones'
brain_parts = [p for p in atlas['parts'] if p['provenance']['source_asset'].startswith('Allen_')]
brain_bounds = np.array([p['bounds'] for p in brain_parts])
box = np.array([brain_bounds[:, 0].min(axis=0), brain_bounds[:, 1].max(axis=0)])
target = np.array(transform['regional_transforms'][0]['target_brain_bounds'])
assert np.all(box[0] >= target[0] - 1e-6) and np.all(box[1] <= target[1] + 1e-6), 'Brain bounds leave CT brain envelope'
denver_fit = transform['additional_source_transforms'][0]
print(f"Verified {len(ids)} composed meshes, unchanged topology, source transforms, torso RMS {transform['rms_mm']:.2f} mm and lower-limb RMS {denver_fit['rms_mm']:.2f} mm. Anatomical registration remains unreviewed.")
