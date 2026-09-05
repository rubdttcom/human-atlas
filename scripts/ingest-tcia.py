"""Convert every present label of TCIA female 003 to traceable viewer geometry."""
import hashlib
import json
from pathlib import Path
import nibabel as nib
import numpy as np
import openpyxl
from scipy import ndimage
from skimage.measure import marching_cubes
import trimesh

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/tcia'
OUT = ROOT / 'public/models'
SCAN = RAW / 'Healthy-Total-Body-CTs-003.nii.gz'
source_hash = hashlib.sha256(SCAN.read_bytes()).hexdigest()
rows = list(openpyxl.load_workbook(RAW / 'demographics.xlsx', data_only=True).active.values)
donor = next(dict(zip(rows[0], row)) for row in rows[1:] if row[0] == 'Healthy-Total-Body-CTs-003')
assert donor['Gender'] == 'F'
label_file = next(RAW.glob('segmentation_organ_values*.xlsx'))
labels = {int(row[0]): row[1] for row in list(openpyxl.load_workbook(label_file, data_only=True).active.values)[1:]
          if isinstance(row[0], (int, float)) and row[1]}
image = nib.load(SCAN)
volume = np.asarray(image.dataobj, dtype=np.uint8)
boxes = ndimage.find_objects(volume)
present = [int(value) for value in np.unique(volume) if value]
assert set(present) <= labels.keys()
# RAS coordinates to viewer left/up/anterior, preserving metric size and pose.
rotation = np.array([[-1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=float)
matrix = rotation @ image.affine
matrix[:3] *= .001
all_bounds = [box for box in boxes if box]
low_z = min(box[2].start for box in all_bounds)
matrix[1, 3] -= (image.affine[2, 3] + (low_z - .5) * image.affine[2, 2]) * .001
systems = {1: 'endocrine', 2: 'arterial', 3: 'urinary', 4: 'nervous', 5: 'cardiac', 6: 'urinary',
           7: 'digestive', 8: 'digestive', 9: 'lymphatic', 10: 'endocrine', 11: 'venous', 12: 'respiratory',
           33: 'muscular', 34: 'integumentary', 35: 'integumentary', 36: 'muscular'}
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
    name = f'tcia-003-{len(chunks)}.bin'
    (OUT / name).write_bytes(blob)
    chunks.append({'url': '/models/' + name, 'bytes': len(blob)})
    blob.clear()


for value in present:
    box = boxes[value - 1]
    # The diffuse tissue depots have a separate, coarser browser LOD; no label is discarded.
    step = 3 if value in (33, 34, 35) else 1
    crop = np.pad((volume[box] == value).astype(np.uint8), step)
    vertices, faces, _, _ = marching_cubes(crop, .5, step_size=step, allow_degenerate=False)
    vertices += np.array([s.start for s in box]) - step
    vertices = nib.affines.apply_affine(matrix, vertices)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    winding_reversed = mesh.volume < 0
    if winding_reversed:
        mesh.invert()
    pos = np.asarray(mesh.vertices, dtype='<f4')
    normal = np.asarray(np.clip(mesh.vertex_normals * 32767, -32767, 32767), dtype='<i2')
    indices = np.asarray(mesh.faces, dtype='<u4').ravel()
    if len(blob) > 6_000_000:
        flush()
    name = labels[value]
    identity = f'TCIA:003:label-{value}'
    part = {'id': identity, 'name': name, 'conceptId': identity, 'system': systems.get(value, 'skeletal'),
            'chunk': len(chunks), 'positions': append(pos), 'normals': append(normal), 'indices': append(indices),
            'vertexCount': len(pos), 'indexCount': len(indices), 'bounds': [pos.min(axis=0).tolist(), pos.max(axis=0).tolist()],
            'source_metadata': {'source_sex': 'female', 'source_donor': 'Healthy-Total-Body-CTs-003',
                                'geometry_type': 'automatic_segmentation', 'input_sha256': source_hash,
                                'label_value': value, 'label_name': name, 'lod_step_voxels': step,
                                'ontology_mapping': 'dataset-local-label; ontology crosswalk pending',
                                'notes': 'Published MOOSE segmentation, not manually reviewed here. Bilateral bones and some organs share a label; labels are not individual structures.'}}
    parts.append(part)
    concepts.append({'id': identity, 'name': name, 'elements': [identity]})
    reports.append({'label': value, 'name': name, 'triangles': len(indices) // 3, 'vertices': len(pos),
                    'watertight': bool(mesh.is_watertight), 'winding_consistent': bool(mesh.is_winding_consistent),
                    'winding_reversed': bool(winding_reversed), 'volume_m3': float(mesh.volume),
                    'degenerate_faces': int(np.sum(mesh.area_faces < 1e-14)), 'lod_step_voxels': step,
                    'self_intersections': 'not-assessed', 'anatomical_review': 'pending'})
    print(f'{value}: {name}: {len(indices)//3} triangles', flush=True)
flush()
atlas = {'version': 'TCIA Healthy Total Body CTs segmentation January 2023; clinical v02 20240927',
         'sex': 'female', 'source': 'TCIA female 003', 'scope': 'Female donor, 26 years; automatic CT segmentation; grouped structures',
         'parts': parts, 'concepts': concepts, 'chunks': chunks, 'triangles': sum(p['indexCount'] // 3 for p in parts),
         'donor_metadata': donor, 'input_sha256': source_hash, 'source_affine': image.affine.tolist(),
         'source_orientation': list(nib.aff2axcodes(image.affine)), 'voxel_to_stage': matrix.tolist(),
         'voxel_spacing_mm': [float(v) for v in image.header.get_zooms()],
         'source_label_count': len(labels), 'absent_labels': [{'value': value, 'name': name} for value, name in labels.items() if value not in present]}
(OUT / 'atlas-tcia-female.json').write_text(json.dumps(atlas, separators=(',', ':')))
(ROOT / 'generated/tcia-qa.json').write_text(json.dumps(reports, indent=2) + '\n')
print(json.dumps({'meshes': len(parts), 'triangles': atlas['triangles'], 'source_orientation': atlas['source_orientation']}))
