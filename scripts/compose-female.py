"""Build an auditable experimental female composition in TCIA 003 display space.

Bounding-box centres are initial registration proxies, not validated anatomical
landmarks. This fit must not be interpreted as a donor-coherent reconstruction.
"""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'public/models'
hra = json.loads((ROOT / 'public/atlases/hra-female.json').read_text())
tcia = json.loads((ROOT / 'public/atlases/tcia.json').read_text())
denver = json.loads((ROOT / 'public/atlases/denver-vhf.json').read_text())
pairs = [('heart', 'Heart'), ('liver', 'Liver'), ('spleen', 'Spleen'),
         ('kidney', 'Kidneys'), ('urinary bladder', 'Bladder'), ('pelvis', 'Pelvis')]
hra_parts = {p['id']: p for p in hra['parts']}


def center(parts):
    boxes = np.array([p['bounds'] for p in parts])
    return (boxes[:, 0].min(axis=0) + boxes[:, 1].max(axis=0)) / 2



def similarity(landmarks):
    # Umeyama closed-form similarity (uniform scale, rotation, translation) on proxy centres.
    source_points = np.array([p['source_center_m'] for p in landmarks])
    target_points = np.array([p['target_center_m'] for p in landmarks])
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
    distances = np.linalg.norm(source_points @ matrix[:3, :3].T + translation - target_points, axis=1)
    for pair, error in zip(landmarks, distances):
        pair['residual_mm'] = float(error * 1000)
    return matrix, float(scale), distances


landmarks = []
for source_name, target_name in pairs:
    concept = next(c for c in hra['concepts'] if c['name'] == source_name)
    source = center([hra_parts[i] for i in concept['elements']])
    target = center([p for p in tcia['parts'] if p['name'] == target_name])
    landmarks.append({'source_concept': concept['id'], 'target_label': target_name,
                      'source_center_m': source.tolist(), 'target_center_m': target.tolist()})
matrix, scale, distances = similarity(landmarks)
transform = {'id': 'hra-stage-to-tcia003-initial', 'type': 'similarity', 'from': 'HRA viewer stage',
             'to': 'TCIA 003 viewer stage', 'matrix_row_major': matrix.ravel().tolist(), 'scale': float(scale),
             'landmarks': landmarks, 'rms_mm': float(np.sqrt(np.mean(distances ** 2)) * 1000),
             'max_residual_mm': float(distances.max() * 1000), 'hausdorff': None,
             'volume_scale': float(scale ** 3), 'surface_area_scale': float(scale ** 2),
             'review_status': 'experimental-unreviewed', 'canonical_registration': False,
             'limitations': ['Bounding-box centres are geometric proxies, not manually marked anatomical landmarks.',
                            'Different donors and poses. Local organ placement and tissue intersections are unreviewed.',
                            'The target is a provisional TCIA display frame, not canonical VHF.']}
brain_parts = [p for p in hra['parts'] if p['id'].startswith('Allen_')]
brain_boxes = np.array([p['bounds'] for p in brain_parts])
source_brain_bounds = np.array([brain_boxes[:, 0].min(axis=0), brain_boxes[:, 1].max(axis=0)])
target_brain_bounds = np.array(next(p for p in tcia['parts'] if p['name'] == 'Brain')['bounds'])
head_scale = np.min((target_brain_bounds[1] - target_brain_bounds[0]) / (source_brain_bounds[1] - source_brain_bounds[0]))
head_matrix = np.eye(4)
head_matrix[:3, :3] *= head_scale
head_matrix[:3, 3] = target_brain_bounds.mean(axis=0) - head_scale * source_brain_bounds.mean(axis=0)
head_transform = {'id': 'hra-head-to-tcia003-initial', 'type': 'similarity-bounding-box-fit',
                  'from': 'HRA viewer stage', 'to': 'TCIA 003 viewer stage',
                  'matrix_row_major': head_matrix.ravel().tolist(), 'scale': float(head_scale),
                  'source_brain_bounds': source_brain_bounds.tolist(), 'target_brain_bounds': target_brain_bounds.tolist(),
                  'volume_scale': float(head_scale ** 3), 'surface_area_scale': float(head_scale ** 2),
                  'rms_mm': None, 'review_status': 'experimental-unreviewed', 'canonical_registration': False,
                  'limitations': ['Brain bounding-box containment is not a surface registration or anatomical validation.',
                                 'The same transform is applied to cranial sensory structures; their placement is unreviewed.']}
transform['regional_transforms'] = [head_transform]
# Denver VHF lower limb -> TCIA 003 display frame. Bilateral bone groups are matched to
# TCIA's grouped bone labels; the tarsal group uses every Denver tarsal bone.
TARSALS = ('Calcaneous', 'Talus', 'Navicular', 'Cuboid', 'MedialCuneiform', 'IntermediateCuneiform', 'LateralCuneiform')
denver_pairs = [('Pelvis, sacrum and coccyx', ('Pelvis', 'Sacrum', 'Coccyx'), 'Pelvis'), ('Femur', ('Femur',), 'Femur'),
                ('Tibia', ('Tibia',), 'Tibia'), ('Fibula', ('Fibula',), 'Fibula'), ('Patella', ('Patella',), 'Patella'),
                ('Tarsal bones', TARSALS, 'Tarsal')]
denver_landmarks = []
for label, source_labels, target_name in denver_pairs:
    parts_used = [p for p in denver['parts'] if p['source_metadata']['tissue_class'] == 'Bone'
                  and p['source_metadata']['source_label'] in source_labels]
    assert parts_used, label
    denver_landmarks.append({'source_concept': label, 'source_assets': [p['id'] for p in parts_used], 'target_label': target_name,
                             'source_center_m': center(parts_used).tolist(),
                             'target_center_m': center([p for p in tcia['parts'] if p['name'] == target_name]).tolist()})
denver_matrix, denver_scale, denver_distances = similarity(denver_landmarks)
denver_transform = {'id': 'denver-stage-to-tcia003-initial', 'type': 'similarity', 'from': 'Denver VHF viewer stage',
                    'to': 'TCIA 003 viewer stage', 'matrix_row_major': denver_matrix.ravel().tolist(), 'scale': denver_scale,
                    'landmarks': denver_landmarks, 'rms_mm': float(np.sqrt(np.mean(denver_distances ** 2)) * 1000),
                    'max_residual_mm': float(denver_distances.max() * 1000), 'hausdorff': None,
                    'volume_scale': float(denver_scale ** 3), 'surface_area_scale': float(denver_scale ** 2),
                    'review_status': 'experimental-unreviewed', 'canonical_registration': False,
                    'limitations': ['Bounding-box centres of grouped bones are geometric proxies, not anatomical landmarks.',
                                    'TCIA grouped labels may include or exclude the sacrum; the pelvis proxy pairing is unreviewed.',
                                    'Different donors (VHF, 59 years; TCIA 003, 26 years) and poses; joint spaces and soft-tissue overlap are unreviewed.',
                                    'Denver "Phalanges" spans about 149 mm antero-posteriorly and probably includes the metatarsals; TCIA metatarsal and toe labels are therefore excluded, unreviewed.']}
transform['additional_source_transforms'] = [denver_transform]
(ROOT / 'transforms/denver-stage-to-tcia003-initial.json').write_text(json.dumps(denver_transform, indent=2) + '\n')
(ROOT / 'transforms/hra-head-to-tcia003-initial.json').write_text(json.dumps(head_transform, indent=2) + '\n')
(ROOT / 'transforms/hra-stage-to-tcia003-initial.json').write_text(json.dumps(transform, indent=2) + '\n')
chunks, parts, concepts, recipe = [], [], [], []
overrides = json.loads((ROOT / 'registry/composition-overrides.json').read_text())
known = {p['provenance']['id'] for a in (hra, tcia, denver) for p in a['parts']}
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


DENVER_REPLACES_TCIA = {15: 'Femur', 16: 'Fibula', 19: 'Metatarsal', 20: 'Patella', 21: 'Pelvis', 29: 'Tarsal', 30: 'Tibia', 31: 'Toes'}
for atlas, source_id in [(hra, 'hra-female'), (tcia, 'tcia'), (denver, 'denver-vhf')]:
    buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in atlas['chunks']]
    id_map = {}
    for original in atlas['parts']:
        if source_id == 'hra-female':
            include = original['system'] != 'skeletal' and original['id'] != 'VH_F_skin'
            reason = 'Detailed female reference anatomy; CT skeleton replaces HRA skeleton; mismatched-pose skin excluded.'
            if include and original['system'] == 'muscular' and original['bounds'][1][1] < 1.05:
                include = False
                reason = 'Lower-limb reference muscle replaced by the Denver VHF manual segmentation (priority 1 female donor geometry).'
        elif source_id == 'tcia':
            include = original['system'] in ('skeletal', 'endocrine') or original['source_metadata']['label_value'] in (33, 34, 35, 36)
            reason = 'Female CT skeleton and structures absent from HRA; grouped tissue depots remain optional.'
            if original['source_metadata']['label_value'] in DENVER_REPLACES_TCIA:
                include = False
                reason = 'Grouped CT bone label replaced by individual Denver VHF bones (manual segmentation, female donor).'
        else:
            include = True
            reason = 'Denver VHF lower-limb bones, muscles, cartilage and ligaments: measured female geometry, best available source for the region.'
        if original['provenance']['id'] in overrides:
            include = overrides[original['provenance']['id']]
            reason = 'Explicit per-structure composition override'
        recipe.append({'source': source_id, 'source_asset': original['id'], 'included': include, 'reason': reason})
        if not include:
            continue
        part = copy.deepcopy(original)
        part['id'] = part['provenance']['id']
        id_map[original['id']] = part['id']
        data = buffers[original['chunk']]
        pos = np.frombuffer(data, '<f4', count=original['vertexCount'] * 3, offset=original['positions']).reshape(-1, 3)
        normals = np.frombuffer(data, '<i2', count=original['vertexCount'] * 3, offset=original['normals']).reshape(-1, 3)
        indices = np.frombuffer(data, '<u4', count=original['indexCount'], offset=original['indices'])
        if source_id == 'hra-female':
            regional = (original['id'].startswith('Allen_') or original['system'] == 'sensory'
                        or original['bounds'][0][1] >= source_brain_bounds[0, 1])
            active_matrix = head_matrix if regional else matrix
            active_transform = head_transform if regional else transform
            pos = np.asarray(pos @ active_matrix[:3, :3].T + active_matrix[:3, 3], dtype='<f4')
            normal_vectors = normals @ np.linalg.inv(active_matrix[:3, :3])
            normal_lengths = np.linalg.norm(normal_vectors, axis=1, keepdims=True)
            normal_vectors /= np.maximum(normal_lengths, 1e-12)
            normals = np.asarray(np.clip(normal_vectors * 32767, -32767, 32767), dtype='<i2')
            part['provenance']['registration'] = {'type': 'experimental-similarity', 'transform_id': active_transform['id'],
                'display_transform_id': active_transform['id'], 'rms_mm': active_transform['rms_mm'], 'review_status': 'unreviewed'}
            part['provenance']['display_space'] = transform['to']
            part['provenance']['notes'] += ' Experimental head bounding-box fit; cranial and cervical continuity unreviewed.' if regional else f" Experimental torso registration, RMS {transform['rms_mm']:.1f} mm. Not anatomically reviewed."
        elif source_id == 'denver-vhf':
            pos = np.asarray(pos @ denver_matrix[:3, :3].T + denver_matrix[:3, 3], dtype='<f4')
            normal_vectors = normals @ np.linalg.inv(denver_matrix[:3, :3])
            normal_vectors /= np.maximum(np.linalg.norm(normal_vectors, axis=1, keepdims=True), 1e-12)
            normals = np.asarray(np.clip(normal_vectors * 32767, -32767, 32767), dtype='<i2')
            part['provenance']['registration'] = {'type': 'experimental-similarity', 'transform_id': denver_transform['id'],
                'display_transform_id': denver_transform['id'], 'rms_mm': denver_transform['rms_mm'], 'review_status': 'unreviewed'}
            part['provenance']['display_space'] = transform['to']
            part['provenance']['notes'] += f" Experimental lower-limb registration to TCIA 003, RMS {denver_transform['rms_mm']:.1f} mm on grouped-bone proxies. Not anatomically reviewed."
        elif original['source_metadata']['label_value'] in (33, 34, 35):
            part['system'] = 'tissue'
        if len(blob) > 4_000_000:
            flush()
        part.update({'chunk': len(chunks), 'positions': append(pos), 'normals': append(normals), 'indices': append(indices),
                     'bounds': [pos.min(axis=0).tolist(), pos.max(axis=0).tolist()]})
        parts.append(part)
        concepts.append({'id': part['id'], 'name': part['name'], 'elements': [part['id']]})
    for concept in atlas['concepts']:
        if len(concept['elements']) > 1 and all(i in id_map for i in concept['elements']):
            concepts.append({'id': source_id + ':' + concept['id'], 'name': concept['name'],
                             'elements': [id_map[i] for i in concept['elements']]})
flush()
for part in parts:
    part['provenance']['derived_chunk_sha256'] = chunks[part['chunk']]['sha256']
composed = {'version': 'Female composition 0.2 experimental', 'sex': 'female', 'source': 'HRA + TCIA 003 + Denver VHF',
            'scope': 'Experimental multi-source assembly; spatial registration unreviewed; not a single donor',
            'parts': parts, 'concepts': concepts, 'chunks': chunks, 'triangles': sum(p['indexCount'] // 3 for p in parts),
            'registration_report': transform, 'canonical_space': None}
(ROOT / 'public/atlases/composed.json').write_text(json.dumps(composed, indent=2) + '\n')
(ROOT / 'registry/composition-recipe.json').write_text(json.dumps(recipe, indent=2) + '\n')
(ROOT / 'generated/registration-report.json').write_text(json.dumps(transform, indent=2) + '\n')
print(json.dumps({'meshes': len(parts), 'triangles': composed['triangles'], 'registration_rms_mm': transform['rms_mm'],
                  'registration_max_mm': transform['max_residual_mm'], 'denver_rms_mm': denver_transform['rms_mm'],
                  'denver_max_mm': denver_transform['max_residual_mm'], 'denver_scale': denver_scale,
                  'review': transform['review_status']}, indent=2))
