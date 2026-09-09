"""Baseline for the plan B bone-concordance criterion: Denver bones against the cortical edge of the same-donor CT.

Reference and procedure, identical for Denver bones today and for machine bones later:
  1. The Denver bone (VHF-image-2022 frame) is carried into the CT frame with the inverse of nlm-ct-to-vhf
     (global placement) and the residual to the CT cortical edge is measured: "placement" distances.
  2. The bone is then fitted rigidly on its own (ICP, no scale) to the CT cortical edge within its own
     neighbourhood: "shape" distances. Placement and shape are reported separately.
  The CT cortical edge is the iso-surface HU = 300 of the fresh CT, extracted only inside a 20 mm band
  around the bone so that the fit cannot latch onto other bones. Distances are bone surface -> CT edge
  (one direction), because the band contains edges of neighbouring bones. Points whose nearest CT voxel
  lies outside the acquired field of view (data/derived/nlm-vhf/ct-coverage-mask.nii.gz) are excluded.

Output: generated/denver-ct-baseline.json (per bone: placement p95, shape p95, rotation of the own fit).
"""
import json
from pathlib import Path
import nibabel as nib
import numpy as np
import trimesh
from scipy import ndimage
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes

ROOT = Path(__file__).resolve().parents[1]
RNG = np.random.default_rng(1993)
D = ROOT / 'data/derived/nlm-vhf'
img = nib.load(D / 'vhf-fresh-ct.nii.gz'); ct = np.asanyarray(img.dataobj); aff = img.affine; inv = np.linalg.inv(aff)
cover_path = D / 'ct-coverage-mask.nii.gz'
cover = np.asanyarray(nib.load(cover_path).dataobj) if cover_path.exists() else None
denver = json.loads((ROOT / 'public/atlases/denver-vhf.json').read_text())
stage = json.loads((ROOT / 'transforms/source-to-stage.json').read_text())
stage_to_image = np.linalg.inv(np.array(stage['denver-image-to-stage']['matrix_row_major']).reshape(4, 4))
ct_to_vhf = np.array(json.loads((ROOT / 'transforms/nlm-ct-to-vhf.json').read_text())['matrix_row_major']).reshape(4, 4)
vhf_to_ct = np.linalg.inv(ct_to_vhf)
buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in denver['chunks']]
HU_EDGE, BAND_MM = 300, 20

def denver_bone(part):
    data = buffers[part['chunk']]
    v = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3).astype(float)
    f = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices']).reshape(-1, 3)
    v = trimesh.transform_points(trimesh.transform_points(v, stage_to_image), vhf_to_ct)   # -> CT RAS mm
    return trimesh.Trimesh(v, f, process=False)

def ct_edge_points(mesh):
    lo = nib.affines.apply_affine(inv, mesh.bounds[0] - BAND_MM); hi = nib.affines.apply_affine(inv, mesh.bounds[1] + BAND_MM)
    lo, hi = np.floor(np.minimum(lo, hi)).astype(int), np.ceil(np.maximum(lo, hi)).astype(int)
    lo = np.clip(lo, 0, np.array(ct.shape) - 1); hi = np.clip(hi, 0, np.array(ct.shape) - 1)
    box = tuple(slice(a, b + 1) for a, b in zip(lo, hi))
    crop = ct[box].astype(np.float32)
    if (crop > HU_EDGE).sum() < 50: return None, None
    v, f, _, _ = marching_cubes(crop, HU_EDGE)
    v = nib.affines.apply_affine(aff, v + lo)
    edge = trimesh.Trimesh(v, f, process=False)
    # keep only edge points within BAND_MM of the Denver bone surface
    d = cKDTree(mesh.vertices).query(edge.vertices)[0]
    keep = edge.vertices[d <= BAND_MM]
    if cover is not None and len(keep):
        ijk = np.round(nib.affines.apply_affine(inv, keep)).astype(int)
        ijk = np.clip(ijk, 0, np.array(ct.shape) - 1)
        keep = keep[cover[tuple(ijk.T)] > 0]
    return keep, edge

def sample(mesh, n=30000):
    pts, _ = trimesh.sample.sample_surface(mesh, n, seed=int(RNG.integers(1 << 31)))
    return np.vstack([pts, mesh.vertices])

def stats(d):
    return {'mean_mm': float(d.mean()), 'rms_mm': float(np.sqrt(np.mean(d ** 2))), 'p95_mm': float(np.quantile(d, .95)), 'max_mm': float(d.max()), 'n': int(len(d))}

report = {'method': __doc__.strip(), 'hu_edge': HU_EDGE, 'band_mm': BAND_MM, 'coverage_mask_used': cover is not None, 'bones': []}
bones = [p for p in denver['parts'] if p['source_metadata']['tissue_class'] == 'Bone']
for part in sorted(bones, key=lambda p: (p['source_metadata']['source_label'], p['source_metadata']['source_folder'])):
    name = f"{part['source_metadata']['source_label']}_{part['source_metadata']['source_folder']}"
    mesh = denver_bone(part)
    edge_pts, _ = ct_edge_points(mesh)
    if edge_pts is None or len(edge_pts) < 200:
        report['bones'].append({'bone': name, 'status': 'no CT cortical edge in band (outside field of view or below HU threshold)'}); print(name, 'no edge'); continue
    tree = cKDTree(edge_pts)
    src = sample(mesh)
    placement = stats(tree.query(src)[0])
    # own rigid fit in two stages, both anchored at the bone centroid so that ICP cannot drift to neighbouring bones:
    # stage A uses edge points within 8 mm of the placed bone, stage B within 4 mm of the stage-A result
    centre = src.mean(axis=0)
    matrix = np.eye(4); moved = src
    for band in (8.0, 4.0):
        near = edge_pts[cKDTree(moved).query(edge_pts)[0] <= band]
        if len(near) < 200: break
        m, _, _ = trimesh.registration.icp(moved - centre, near - centre, initial=np.eye(4), scale=False, max_iterations=40, threshold=1e-7)
        step = np.eye(4); step[:3, :3] = m[:3, :3]; step[:3, 3] = m[:3, 3] + centre - m[:3, :3] @ centre
        matrix = step @ matrix; moved = trimesh.transform_points(src, matrix)
    shape = stats(tree.query(moved)[0])
    rot = float(np.degrees(np.arccos(np.clip((np.trace(matrix[:3, :3]) - 1) / 2, -1, 1))))
    disp = float(np.linalg.norm(moved.mean(axis=0) - centre))
    diverged = rot > 15 or disp > 15
    entry = {'bone': name, 'denver_id': part['id'], 'denver_volume_cm3': float(abs(mesh.volume) / 1000), 'ct_edge_points': int(len(edge_pts)),
             'placement_under_nlm_ct_to_vhf': placement,
             'own_rigid_fit': {'rotation_deg': rot, 'centroid_displacement_mm': disp, 'shape_residual': shape, 'diverged': diverged}}
    report['bones'].append(entry)
    print(f"{name:26s} placement p95 {placement['p95_mm']:5.2f} mm | own rigid: rot {rot:4.1f} deg, centroid shift {disp:5.1f} mm, shape p95 {shape['p95_mm']:5.2f} mm{'  DIVERGED' if diverged else ''}", flush=True)
ok = [b for b in report['bones'] if 'own_rigid_fit' in b and not b['own_rigid_fit']['diverged']]
report['summary'] = {'bones_measured': len(ok), 'bones_diverged': [b['bone'] for b in report['bones'] if b.get('own_rigid_fit', {}).get('diverged')], 'shape_p95_mm_median': float(np.median([b['own_rigid_fit']['shape_residual']['p95_mm'] for b in ok])),
                     'shape_p95_mm_max': float(max(b['own_rigid_fit']['shape_residual']['p95_mm'] for b in ok)),
                     'placement_p95_mm_median': float(np.median([b['placement_under_nlm_ct_to_vhf']['p95_mm'] for b in ok]))}
(ROOT / 'generated/denver-ct-baseline.json').write_text(json.dumps(report, indent=1) + '\n')
print(json.dumps(report['summary'], indent=1))
