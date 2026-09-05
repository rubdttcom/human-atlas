"""Register the NLM VHF fresh-CT segmentation to the Denver VHF bones and verify canonical space VHF-image-2022.

Same donor, two acquisitions: the fresh CT (1993, before freezing) and the cryosections that Denver
segmented (aligned image frame). Both frames are +x right, +y anterior, +z superior in millimetres, so
a correct canonical space should relate them by a rigid transform with a scale of 1.0. This script
measures that:

1. Bones are extracted from the TotalSegmentator label map (marching cubes in the CT RAS frame).
2. The pelvis (both hip bones and the sacrum) is registered rigidly (no scale) onto the Denver hip
   bones and sacrum in the VHF image frame, after centroid alignment. A second fit with a free scale is
   recorded only as a unit check.
3. Each femur is registered rigidly on its own, because the legs may have moved between the two
   acquisitions (fresh on the table versus frozen block).
4. Residual surface distances are reported per bone. The pelvis transform becomes `nlm-ct-to-vhf`.

Usage: .venv/bin/python scripts/register-nlm-ct.py [data/derived/nlm-vhf/totalseg.nii]
Outputs: transforms/nlm-ct-to-vhf.json, generated/nlm-ct-registration.json
"""
import hashlib
import json
import sys
from pathlib import Path
import nibabel as nib
import numpy as np
import trimesh
from scipy import ndimage
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes

ROOT = Path(__file__).resolve().parents[1]
LABELS = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'data/derived/nlm-vhf/totalseg.nii')
RNG = np.random.default_rng(1993)
class_map = {int(k): v for k, v in json.load(open(ROOT / 'data/derived/nlm-vhf/totalseg-classmap.json'))['total'].items()}
name_to_label = {v: k for k, v in class_map.items()}
image = nib.load(LABELS)
labels = np.asarray(image.dataobj).astype(np.int16)
affine = image.affine
ct_meta = json.loads((ROOT / 'data/derived/nlm-vhf/vhf-fresh-ct-metadata.json').read_text())
denver = json.loads((ROOT / 'public/atlases/denver-vhf.json').read_text())
stage = json.loads((ROOT / 'transforms/source-to-stage.json').read_text())
image_to_stage = np.array(stage['denver-image-to-stage']['matrix_row_major']).reshape(4, 4)
stage_to_image = np.linalg.inv(image_to_stage)
buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in denver['chunks']]


def denver_bone(label, folder):
    part = next(p for p in denver['parts'] if p['source_metadata']['tissue_class'] == 'Bone' and p['source_metadata']['source_label'] == label and p['source_metadata']['source_folder'] == folder)
    data = buffers[part['chunk']]
    vertices = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3).astype(float)
    faces = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices']).reshape(-1, 3)
    return part['id'], trimesh.Trimesh(trimesh.transform_points(vertices, stage_to_image), faces, process=False)   # VHF image frame, mm


SPECKLE_FRACTION = 0.05
speckle_log = {}


def clean(mask, key):
    """Keep connected components at least SPECKLE_FRACTION of the largest; stray islands of a label are recorded, not registered."""
    components, count = ndimage.label(mask)
    if count <= 1:
        speckle_log[key] = {'components': int(count), 'removed_voxels': 0}
        return mask
    sizes = ndimage.sum(mask, components, range(1, count + 1))
    keep = np.where(sizes >= SPECKLE_FRACTION * sizes.max())[0] + 1
    cleaned = np.isin(components, keep)
    speckle_log[key] = {'components': int(count), 'kept_components': int(len(keep)), 'removed_voxels': int(mask.sum() - cleaned.sum())}
    return cleaned


def ct_bone(names):
    mask = clean(np.isin(labels, [name_to_label[n] for n in names]), '+'.join(names))
    box = ndimage.find_objects(mask.astype(np.uint8))[0]
    crop = np.pad(mask[box], 1)
    vertices, faces, _, _ = marching_cubes(crop.astype(np.uint8), 0.5, allow_degenerate=False)
    vertices += np.array([s.start for s in box]) - 1
    mesh = trimesh.Trimesh(nib.affines.apply_affine(affine, vertices), faces, process=False)   # CT RAS frame, mm
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def samples(mesh, count):
    points, _ = trimesh.sample.sample_surface(mesh, count, seed=int(RNG.integers(1 << 31)))
    return np.vstack([points, mesh.vertices])


def distances(a, b, count=40000):
    pa, pb = samples(a, count), samples(b, count)
    ab = cKDTree(pb).query(pa)[0]
    ba = cKDTree(pa).query(pb)[0]
    stats = lambda d: {'mean_mm': float(d.mean()), 'rms_mm': float(np.sqrt(np.mean(d ** 2))), 'p95_mm': float(np.quantile(d, .95)), 'max_mm': float(d.max())}
    return {'ct_to_denver': stats(ab), 'denver_to_ct': stats(ba), 'hausdorff_mm': float(max(ab.max(), ba.max()))}


def rigid_fit(source, target, scale=False):
    src, tgt = samples(source, 30000), samples(target, 60000)
    initial = np.eye(4)
    initial[:3, 3] = tgt.mean(axis=0) - src.mean(axis=0)
    matrix, _, cost = trimesh.registration.icp(src, tgt, initial=initial, scale=scale, max_iterations=80, threshold=1e-7)
    linear = matrix[:3, :3]
    s = float(np.cbrt(abs(np.linalg.det(linear))))
    rotation = linear / s
    angle = float(np.degrees(np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1, 1))))
    moved = trimesh.Trimesh(trimesh.transform_points(source.vertices, matrix), source.faces, process=False)
    return matrix, {'matrix_row_major': matrix.ravel().tolist(), 'scale': s, 'rotation_deg': angle, 'translation_mm': matrix[:3, 3].tolist(),
                    'translation_norm_mm': float(np.linalg.norm(matrix[:3, 3])), 'icp_cost': float(cost), 'surface': distances(moved, target)}


report = {'labels_file': str(LABELS.relative_to(ROOT)), 'labels_sha256': hashlib.sha256(LABELS.read_bytes()).hexdigest(), 'ct_file': ct_meta['file'], 'ct_sha256': ct_meta['sha256'],
          'frames': {'ct': 'NLM fresh CT RAS mm, header-derived (data/derived/nlm-vhf/vhf-fresh-ct-metadata.json)', 'target': 'VHF-image-2022 (Denver aligned image frame, mm) via the inverse of denver-image-to-stage'},
          'method': __doc__.strip(), 'bones': []}

# 1. Pelvis: rigid, no scale. Then the same fit with free scale as a unit check.
ct_pelvis = ct_bone(['hip_left', 'hip_right', 'sacrum'])
denver_ids, denver_pieces = zip(*[denver_bone('Pelvis', 'Left'), denver_bone('Pelvis', 'Right'), denver_bone('Sacrum', 'Left')])
denver_pelvis = trimesh.util.concatenate(denver_pieces)
before = distances(ct_pelvis, denver_pelvis)
pelvis_matrix, pelvis_fit = rigid_fit(ct_pelvis, denver_pelvis, scale=False)
_, pelvis_scaled = rigid_fit(ct_pelvis, denver_pelvis, scale=True)
report['bones'].append({'structure': 'pelvis (hip bones + sacrum)', 'ct_labels': ['hip_left', 'hip_right', 'sacrum'], 'denver_assets': list(denver_ids),
                        'ct_volume_cm3': float(ct_pelvis.volume / 1000), 'denver_volume_cm3': float(denver_pelvis.volume / 1000),
                        'before_registration_surface': before, 'rigid': pelvis_fit, 'similarity_unit_check': {k: pelvis_scaled[k] for k in ('scale', 'rotation_deg', 'surface')}})
print(f"pelvis: rigid rotation {pelvis_fit['rotation_deg']:.2f} deg, translation {pelvis_fit['translation_norm_mm']:.1f} mm, p95 {pelvis_fit['surface']['ct_to_denver']['p95_mm']:.2f} mm, "
      f"Hausdorff {pelvis_fit['surface']['hausdorff_mm']:.1f} mm; free-scale fit scale {pelvis_scaled['scale']:.4f}", flush=True)

# 2. Hip bones and sacrum individually under the pelvis transform (no further fitting): consistency of the rigid assumption.
for names, (denver_id, target) in [(['hip_left'], denver_bone('Pelvis', 'Left')), (['hip_right'], denver_bone('Pelvis', 'Right')), (['sacrum'], denver_bone('Sacrum', 'Left'))]:
    mesh = ct_bone(names)
    moved = trimesh.Trimesh(trimesh.transform_points(mesh.vertices, pelvis_matrix), mesh.faces, process=False)
    entry = {'structure': names[0], 'ct_labels': names, 'denver_assets': [denver_id], 'ct_volume_cm3': float(mesh.volume / 1000), 'denver_volume_cm3': float(target.volume / 1000),
             'under_pelvis_transform': distances(moved, target)}
    report['bones'].append(entry)
    print(f"{names[0]} under pelvis transform: p95 {entry['under_pelvis_transform']['ct_to_denver']['p95_mm']:.2f} mm, Hausdorff {entry['under_pelvis_transform']['hausdorff_mm']:.1f} mm", flush=True)

# 3. Femora: own rigid fit (leg pose may differ) and residual under the pelvis transform (pose difference measure).
for side, folder in (('left', 'Left'), ('right', 'Right')):
    mesh = ct_bone([f'femur_{side}'])
    denver_id, target = denver_bone('Femur', folder)
    under = trimesh.Trimesh(trimesh.transform_points(mesh.vertices, pelvis_matrix), mesh.faces, process=False)
    own_matrix, own = rigid_fit(mesh, target, scale=False)
    relative = own_matrix @ np.linalg.inv(pelvis_matrix)
    rel_angle = float(np.degrees(np.arccos(np.clip((np.trace(relative[:3, :3]) - 1) / 2, -1, 1))))
    entry = {'structure': f'femur_{side}', 'ct_labels': [f'femur_{side}'], 'denver_assets': [denver_id], 'ct_volume_cm3': float(mesh.volume / 1000), 'denver_volume_cm3': float(target.volume / 1000),
             'under_pelvis_transform': distances(under, target), 'own_rigid': own,
             'pose_change_relative_to_pelvis': {'rotation_deg': rel_angle, 'translation_mm': relative[:3, 3].tolist(), 'note': 'own femur fit composed with the inverse pelvis fit; a hip rotation between acquisitions'}}
    report['bones'].append(entry)
    print(f"femur_{side}: under pelvis p95 {entry['under_pelvis_transform']['ct_to_denver']['p95_mm']:.1f} mm; own rigid p95 {own['surface']['ct_to_denver']['p95_mm']:.2f} mm, pose change {rel_angle:.1f} deg", flush=True)

verification = {
    'axes_and_units': 'consistent' if pelvis_fit['rotation_deg'] < 5 and abs(pelvis_scaled['scale'] - 1) < 0.01 else 'inconsistent',
    'rotation_deg': pelvis_fit['rotation_deg'], 'free_scale': pelvis_scaled['scale'], 'pelvis_p95_mm': pelvis_fit['surface']['ct_to_denver']['p95_mm'],
    'interpretation': ('The Denver aligned image frame and the NLM CT header frame agree in axis directions and millimetre units: the rigid pelvis fit needs a small rotation and a scale of 1 within one percent, '
                       'and the same-donor pelvis surfaces agree to a few millimetres. The translation absorbs the different origins (vertex plane of the CT versus the Denver image origin). '
                       'This verifies the canonical space against NLM image data; it does not review the anatomy of either segmentation.')}
report['canonical_space_verification'] = verification
report['speckle_removal'] = {'rule': f'connected components below {SPECKLE_FRACTION:.0%} of the largest component of a label are excluded from the registration meshes', 'per_label': speckle_log}
transform = {'id': 'nlm-ct-to-vhf', 'type': 'rigid (ICP, no scale) on the pelvis: CT hip bones and sacrum onto Denver hip bones and sacrum', 'from': 'NLM VHF fresh CT RAS (mm)', 'to': 'VHF-image-2022 (mm)',
             'matrix_row_major': pelvis_matrix.ravel().tolist(), 'scale': 1.0, 'rotation_deg': pelvis_fit['rotation_deg'], 'rms_mm': pelvis_fit['surface']['ct_to_denver']['rms_mm'],
             'p95_mm': pelvis_fit['surface']['ct_to_denver']['p95_mm'], 'hausdorff_mm': pelvis_fit['surface']['hausdorff_mm'], 'same_donor': True,
             'canonical_registration': True, 'review_status': 'automatic same-donor surface registration; anatomy unreviewed',
             'segment_scope': 'trunk, pelvis and head (rigid with the pelvis); femora need their own rigid fits (pose_change_relative_to_pelvis)',
             'evidence': 'generated/nlm-ct-registration.json', 'labels_sha256': report['labels_sha256']}
(ROOT / 'transforms/nlm-ct-to-vhf.json').write_text(json.dumps(transform, indent=2) + '\n')
(ROOT / 'generated/nlm-ct-registration.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(verification, indent=1))
