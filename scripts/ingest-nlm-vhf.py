"""Convert the TotalSegmentator labels of the NLM VHF fresh CT into traceable viewer geometry in the canonical space.

Input : data/derived/nlm-vhf/totalseg.nii (TotalSegmentator `total` task, Apache-2.0 model; label map on the CT grid)
        transforms/nlm-ct-to-vhf.json (rigid same-donor pelvis registration CT -> VHF-image-2022, scripts/register-nlm-ct.py)
Output: public/models/atlas-nlm-vhf-ct.json + nlm-vhf-ct-source-*.bin, generated/nlm-vhf-ct-qa.json

Every present label becomes one mesh (marching cubes on the label mask, step 1 voxel; 2 voxels for
labels above 400 cm3 so the browser download stays bounded). Vertices go CT RAS mm -> VHF image frame
(nlm-ct-to-vhf) -> Denver viewer stage (denver-image-to-stage), so the source is natively in the
canonical stage. The femora keep the pelvis transform; their own rigid fits are recorded as evidence
only. Nothing is anatomically reviewed: masks are automatic and unedited.

Usage: .venv/bin/python scripts/ingest-nlm-vhf.py [labels.nii]
"""
import hashlib
import json
import re
import sys
from pathlib import Path
import nibabel as nib
import numpy as np
import trimesh
from scipy import ndimage
from skimage.measure import marching_cubes

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'public/models'
LABELS = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'data/derived/nlm-vhf/totalseg.nii')
class_map = {int(k): v for k, v in json.load(open(ROOT / 'data/derived/nlm-vhf/totalseg-classmap.json'))['total'].items()}
ct_meta = json.loads((ROOT / 'data/derived/nlm-vhf/vhf-fresh-ct-metadata.json').read_text())
transform = json.loads((ROOT / 'transforms/nlm-ct-to-vhf.json').read_text())
registration = json.loads((ROOT / 'generated/nlm-ct-registration.json').read_text())
stage = json.loads((ROOT / 'transforms/source-to-stage.json').read_text())
labels_sha = hashlib.sha256(LABELS.read_bytes()).hexdigest()
assert transform['labels_sha256'] == labels_sha, 'nlm-ct-to-vhf.json was fitted on a different label map; re-run scripts/register-nlm-ct.py'
image = nib.load(LABELS)
volume = np.asarray(image.dataobj).astype(np.int16)
ct_to_vhf = np.array(transform['matrix_row_major']).reshape(4, 4)
image_to_stage = np.array(stage['denver-image-to-stage']['matrix_row_major']).reshape(4, 4)
voxel_to_stage = image_to_stage @ ct_to_vhf @ image.affine
voxel_mm3 = float(np.prod(image.header.get_zooms()))
SYSTEM_RULES = [
    (r'vertebrae|sacrum|rib_|sternum|humerus|scapula|clavicula|femur|^hip_|skull', 'skeletal'),
    (r'costal_cartilages', 'connective'), (r'gluteus|autochthon|iliopsoas', 'muscular'),
    (r'heart|atrial_appendage', 'cardiac'), (r'aorta|artery|brachiocephalic_trunk', 'arterial'),
    (r'vein|vena|portal', 'venous'), (r'lung|trachea|esophagus$', 'respiratory'), (r'brain|spinal_cord', 'nervous'),
    (r'kidney|urinary_bladder|prostate', 'urinary'), (r'thyroid|adrenal', 'endocrine'),
    (r'spleen', 'lymphatic'), (r'liver|gallbladder|stomach|pancreas|bowel|duodenum|colon|esophagus', 'digestive'),
]
NAMES = {'clavicula': 'clavicle', 'autochthon': 'erector spinae (autochthonous back muscles)', 'iliac_vena': 'common iliac vein', 'iliac_artery': 'common iliac artery',
         'hip': 'hip bone', 'small_bowel': 'small intestine', 'portal_vein_and_splenic_vein': 'portal vein and splenic vein', 'atrial_appendage': 'atrial appendage'}


def system_of(label):
    for pattern, system in SYSTEM_RULES:
        if re.search(pattern, label):
            return system
    return 'skeletal' if 'bone' in label else 'connective'


def display_name(label):
    side = 'left' if label.endswith('_left') or '_left_' in label else 'right' if label.endswith('_right') or '_right_' in label else None
    base = re.sub(r'_(left|right)(_|$)', r'\2', label).strip('_')
    match = re.match(r'^vertebrae_([CTLS])(\d+)$', base)
    if match:
        return f'Vertebra {match.group(1)}{match.group(2)}', 'midline'
    match = re.match(r'^rib_(\d+)$', base)
    if match:
        return f'{side.capitalize()} rib {match.group(1)}', side
    if base.startswith('lung_'):
        lobe = base.replace('lung_', '').replace('_lobe', '').replace('_', ' ')
        return f'{lobe.capitalize()} lobe of {side} lung', side
    text = NAMES.get(base, base.replace('_', ' '))
    return (f'{side.capitalize()} {text}', side) if side else (text[0].upper() + text[1:], 'midline')


parts, concepts, chunks, reports = [], [], [], []
blob = bytearray()


def append(values):
    while len(blob) % 4:
        blob.append(0)
    offset = len(blob)
    blob.extend(values.tobytes())
    return offset


def flush():
    if not blob:
        return
    name = f'nlm-vhf-ct-source-{len(chunks)}.bin'
    (OUT / name).write_bytes(blob)
    chunks.append({'url': '/models/' + name, 'bytes': len(blob)})
    blob.clear()


boxes = ndimage.find_objects(volume)
present = [int(v) for v in np.unique(volume) if v]
femur_evidence = {b['structure']: b for b in registration['bones'] if b['structure'].startswith('femur_')}
groups = {}
for value in present:
    label = class_map[value]
    box = boxes[value - 1]
    mask = volume[box] == value
    raw_voxels = int(mask.sum())
    # Stray islands of a label (below 5 % of its largest connected component) are removed and counted; the rest is unedited model output.
    components, count = ndimage.label(mask)
    removed = 0
    if count > 1:
        sizes = ndimage.sum(mask, components, range(1, count + 1))
        mask = np.isin(components, np.where(sizes >= 0.05 * sizes.max())[0] + 1)
        removed = raw_voxels - int(mask.sum())
    voxels = int(mask.sum())
    step = 2 if voxels * voxel_mm3 > 400_000 else 1
    crop = np.pad(mask.astype(np.uint8), step)
    vertices, faces, _, _ = marching_cubes(crop, .5, step_size=step, allow_degenerate=False)
    vertices += np.array([s.start for s in box]) - step
    vertices = nib.affines.apply_affine(voxel_to_stage, vertices)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    winding_reversed = bool(mesh.volume < 0)
    if winding_reversed:
        mesh.invert()
    components = mesh.split(only_watertight=False)
    pos = np.asarray(mesh.vertices, dtype='<f4')
    normal = np.asarray(np.clip(mesh.vertex_normals * 32767, -32767, 32767), dtype='<i2')
    indices = np.asarray(mesh.faces, dtype='<u4').ravel()
    if len(blob) > 6_000_000:
        flush()
    name, laterality = display_name(label)
    identity = f'NLMCT:VHF:{label}'
    metadata = {'source_sex': 'female', 'source_donor': 'VHF', 'geometry_type': 'automatic_segmentation', 'input_sha256': ct_meta['sha256'], 'labels_sha256': labels_sha,
                'label_value': value, 'label_name': label, 'laterality': laterality, 'lod_step_voxels': step, 'voxel_count': voxels, 'volume_cm3': voxels * voxel_mm3 / 1000,
                'speckle_voxels_removed': removed, 'speckle_rule': 'connected components below 5 % of the largest component removed',
                'segmentation_model': 'TotalSegmentator 2.18.0, task total (Apache-2.0), CPU, 1.5 mm' if 'fast' not in LABELS.name else 'TotalSegmentator 2.18.0, task total (Apache-2.0), CPU, --fast 3 mm',
                'registration_transform': transform['id'], 'registration_p95_mm': transform['p95_mm'],
                'ontology_mapping': 'dataset-local-label; ontology crosswalk pending',
                'notes': ('Automatic TotalSegmentator label on the NLM Visible Human Female fresh CT (1993, before freezing); same donor as the Denver cryosection meshes. '
                          'Placed in the canonical space by one rigid same-donor pelvis registration (no scale). Not manually reviewed; label boundaries are model output.')}
    if label in femur_evidence:
        pose = femur_evidence[label]['pose_change_relative_to_pelvis']
        metadata['pose_note'] = f"Own rigid fit differs from the pelvis transform by {pose['rotation_deg']:.1f} deg: the hip joint moved between the CT and the cryosections. The pelvis transform is used here; Denver femur is the canonical bone."
    part = {'id': identity, 'name': name, 'conceptId': identity, 'system': system_of(label), 'chunk': len(chunks), 'positions': append(pos), 'normals': append(normal),
            'indices': append(indices), 'vertexCount': len(pos), 'indexCount': len(indices), 'bounds': [pos.min(axis=0).tolist(), pos.max(axis=0).tolist()], 'source_metadata': metadata}
    parts.append(part)
    concepts.append({'id': identity, 'name': name, 'elements': [identity]})
    base = re.sub(r'_(left|right)(_|$)', r'\2', label).strip('_')
    if laterality != 'midline':
        groups.setdefault(base, []).append(identity)
    for prefix, group_name in (('vertebrae_', 'Vertebral column (CT labels)'), ('rib_', 'Ribs (CT labels)'), ('lung_', 'Lungs (CT labels)')):
        if label.startswith(prefix):
            groups.setdefault(group_name, []).append(identity)
    reports.append({'label': value, 'name': label, 'triangles': len(indices) // 3, 'vertices': len(pos), 'watertight': bool(mesh.is_watertight), 'components': len(components),
                    'winding_reversed': winding_reversed, 'volume_m3': float(mesh.volume), 'speckle_voxels_removed': removed, 'degenerate_faces': int(np.sum(mesh.area_faces < 1e-14)), 'lod_step_voxels': step,
                    'self_intersections': 'not-assessed', 'anatomical_review': 'pending'})
    print(f'{value}: {label}: {len(indices)//3} triangles, {len(components)} components', flush=True)
flush()
for key, elements in groups.items():
    if len(elements) > 1:
        name = key if key.endswith('(CT labels)') else f"{NAMES.get(key, key.replace('_', ' '))} (both sides)"
        concepts.append({'id': f'NLMCT:VHF:group:{key}', 'name': name[0].upper() + name[1:], 'elements': elements})
atlas = {'version': 'NLM Visible Human Female fresh CT, TotalSegmentator total task', 'sex': 'female', 'source': 'NLM VHF CT segmentation',
         'scope': 'Female donor VHF (NLM Visible Human Female), fresh CT before freezing; automatic TotalSegmentator labels for trunk, upper limb and head; rigid same-donor registration to the Denver frame; unreviewed',
         'parts': parts, 'concepts': concepts, 'chunks': chunks, 'triangles': sum(p['indexCount'] // 3 for p in parts),
         'input_sha256': ct_meta['sha256'], 'labels_sha256': labels_sha, 'labels_file': str(LABELS.relative_to(ROOT)), 'ct_metadata': 'data/derived/nlm-vhf/vhf-fresh-ct-metadata.json',
         'source_affine': image.affine.tolist(), 'voxel_to_stage': voxel_to_stage.tolist(), 'ct_to_vhf': transform, 'voxel_spacing_mm': [float(v) for v in image.header.get_zooms()],
         'source_label_count': len(class_map), 'absent_labels': [{'value': v, 'name': n} for v, n in class_map.items() if v not in present],
         'licence_evidence': {'input': 'NLM Terms and Conditions (no licence since July 2019; attribution "Courtesy of the U.S. National Library of Medicine")',
                              'model': 'TotalSegmentator task total: "Openly available for any usage (Apache-2.0 license)" per project README; licensed subtasks (appendicular_bones, etc.) were not used'},
         'citation': ['Wasserthal et al. 2023, Radiology: Artificial Intelligence, https://doi.org/10.1148/ryai.230024', 'NLM Visible Human Project, https://www.nlm.nih.gov/research/visible/visible_human.html']}
(OUT / 'atlas-nlm-vhf-ct.json').write_text(json.dumps(atlas, separators=(',', ':')))
(ROOT / 'generated/nlm-vhf-ct-qa.json').write_text(json.dumps(reports, indent=2) + '\n')
print(json.dumps({'meshes': len(parts), 'triangles': atlas['triangles'], 'absent': len(atlas['absent_labels']), 'chunks': len(chunks)}))
