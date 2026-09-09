"""Place Denver's aligned whole-body CT (DICOM without position/orientation tags) in the Denver label-map frame.

The aligned CT ships as 1,727 secondary-capture slices (673 x 670 at 0.722656 mm, 1 mm apart) with no
ImagePositionPatient or ImageOrientationPatient, so dcm2niix invents an affine. Denver states the CT is
aligned to the cryosections; this script measures how, by fitting the CT pelvis (MOOSE hip bones and
sacrum) to the Denver final pelvis meshes, which live in the label-map LPS millimetre frame
(scripts/denver-noise-floor.py). Axis flips of the voxel grid are tried; the fit that needs the smallest
rotation with the smallest residual wins. A well-aligned CT should need a rotation near 0 deg.

Output: transforms/denver-aligned-ct-voxel-to-vhf.json (voxel index -> Denver LPS mm), generated/denver-aligned-ct-placement.json
"""
import itertools, json
from pathlib import Path
import nibabel as nib
import numpy as np
import trimesh
from scipy import ndimage
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes

ROOT = Path(__file__).resolve().parents[1]
RNG = np.random.default_rng(1993)
SEG = next((ROOT / 'data/derived/denver/priors/moose').glob('*/segmentations/clin_CT_vertebrae_segmentation_CT_denverct.nii.gz'))
IDX = json.loads(SEG.with_name('clin_CT_vertebrae_organ_indices.json').read_text())['organ_indices']
ids = {v['name']: int(k) for k, v in IDX.items()}
img = nib.load(SEG); seg = np.asanyarray(img.dataobj)
spacing = np.array([0.722656, 0.722656, 1.0])
denver = json.loads((ROOT / 'public/atlases/denver-vhf.json').read_text())
stage = json.loads((ROOT / 'transforms/source-to-stage.json').read_text())
stage_to_image = np.linalg.inv(np.array(stage['denver-image-to-stage']['matrix_row_major']).reshape(4, 4))
buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in denver['chunks']]

def denver_mesh(label, folder):
    p = next(p for p in denver['parts'] if p['source_metadata']['source_label'] == label and p['source_metadata']['source_folder'] == folder)
    v = np.frombuffer(buffers[p['chunk']], '<f4', count=p['vertexCount'] * 3, offset=p['positions']).reshape(-1, 3).astype(float)
    f = np.frombuffer(buffers[p['chunk']], '<u4', count=p['indexCount'], offset=p['indices']).reshape(-1, 3)
    return trimesh.Trimesh(trimesh.transform_points(v, stage_to_image), f, process=False)

def ct_surface(names):
    mask = np.isin(seg, [ids[n] for n in names])
    lab, n = ndimage.label(mask); sizes = np.bincount(lab.ravel())[1:]
    mask = np.isin(lab, np.where(sizes >= 0.05 * sizes.max())[0] + 1)
    box = ndimage.find_objects(mask.astype(np.uint8))[0]
    v, f, _, _ = marching_cubes(np.pad(mask[box], 1).astype(np.uint8), 0.5)
    v = v - 1 + np.array([s.start for s in box])
    return v   # voxel index coordinates (i, j, k)

target = trimesh.util.concatenate([denver_mesh('Pelvis', 'Left'), denver_mesh('Pelvis', 'Right'), denver_mesh('Sacrum', 'Left')])
tgt_pts = np.vstack([trimesh.sample.sample_surface(target, 60000, seed=1)[0], target.vertices])
tree = cKDTree(tgt_pts)
src_vox = ct_surface(['hip_left', 'hip_right', 'sacrum'])
sub = src_vox[RNG.choice(len(src_vox), min(40000, len(src_vox)), replace=False)]
shape = np.array(seg.shape)
results = []
for flips in itertools.product([1, -1], repeat=3):
    for perm in [(0, 1, 2), (1, 0, 2)]:
        F = np.zeros((4, 4)); F[3, 3] = 1
        for out_axis, in_axis in enumerate(perm):
            F[out_axis, in_axis] = flips[out_axis] * spacing[in_axis]
            if flips[out_axis] < 0: F[out_axis, 3] += (shape[in_axis] - 1) * spacing[in_axis]
        pts = trimesh.transform_points(sub, F)
        init = np.eye(4); init[:3, 3] = tgt_pts.mean(axis=0) - pts.mean(axis=0)
        M, _, cost = trimesh.registration.icp(pts, tgt_pts, initial=init, scale=False, max_iterations=60, threshold=1e-7)
        moved = trimesh.transform_points(pts, M); d = tree.query(moved)[0]
        rot = float(np.degrees(np.arccos(np.clip((np.trace(M[:3, :3]) - 1) / 2, -1, 1))))
        results.append({'flips': flips, 'perm': perm, 'rotation_deg': rot, 'p95_mm': float(np.quantile(d, .95)), 'rms_mm': float(np.sqrt((d ** 2).mean())), 'matrix': (M @ F).tolist()})
        print(f"flips {flips} perm {perm}: rot {rot:6.2f} deg  p95 {results[-1]['p95_mm']:6.2f} mm  rms {results[-1]['rms_mm']:5.2f}", flush=True)
best = min(results, key=lambda r: (r['p95_mm'] + 0.2 * r['rotation_deg']))
M = np.array(best['matrix'])
# residual per bone under the chosen transform
per = {}
for names, (lab, folder) in [(['hip_left'], ('Pelvis', 'Left')), (['hip_right'], ('Pelvis', 'Right')), (['sacrum'], ('Sacrum', 'Left'))]:
    pts = trimesh.transform_points(ct_surface(names), M); mesh = denver_mesh(lab, folder)
    d = cKDTree(np.vstack([trimesh.sample.sample_surface(mesh, 40000, seed=2)[0], mesh.vertices])).query(pts)[0]
    per[names[0]] = {'denver_part': f'{lab}/{folder}', 'p95_mm': float(np.quantile(d, .95)), 'rms_mm': float(np.sqrt((d ** 2).mean())), 'ct_centroid_mm': trimesh.transform_points(ct_surface(names), M).mean(axis=0).tolist(), 'denver_centroid_mm': mesh.vertices.mean(axis=0).tolist()}
out = {'id': 'denver-aligned-ct-voxel-to-vhf', 'type': 'axis flips/permutation + rigid ICP (no scale) of the MOOSE pelvis onto the Denver final pelvis meshes',
       'from': 'voxel index (i, j, k) of data/derived/denver/aligned-ct-nii/denver_aligned_ct*.nii.gz (dcm2niix order, 673 x 670 x 1727, 0.722656 x 0.722656 x 1 mm)',
       'to': 'Denver label-map LPS frame (mm), the frame of the final STL meshes and of VHF_Full.mat', 'matrix_row_major': M.ravel().tolist(),
       'rotation_deg': best['rotation_deg'], 'p95_mm': best['p95_mm'], 'rms_mm': best['rms_mm'], 'axis_choice': {'flips': best['flips'], 'perm': best['perm']},
       'note': 'A rotation near 0 deg confirms Denver aligned the CT to the cryosection frame; the residual mixes MOOSE segmentation error and Denver mesh error.'}
(ROOT / 'transforms/denver-aligned-ct-voxel-to-vhf.json').write_text(json.dumps(out, indent=2) + '\n')
(ROOT / 'generated/denver-aligned-ct-placement.json').write_text(json.dumps({'candidates': results, 'chosen': best, 'per_bone': per, 'segmentation': str(SEG.relative_to(ROOT))}, indent=1) + '\n')
print('chosen', best['flips'], best['perm'], 'rot %.2f deg p95 %.2f mm' % (best['rotation_deg'], best['p95_mm']))
print(json.dumps(per, indent=1))
