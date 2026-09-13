"""Denver post-processing floor measured with the pilot's own metric implementation (Codex audit of afec927, P1).

generated/denver-noise-floor.json measures original label versus final mesh with marching-cubes surface points, mesh
samples and the original-to-final direction only. The acceptance protocol scores predictions with scripts/cryo_metrics.py
(voxel surfaces, symmetric, pooled, anisotropic EDT). A threshold taken from one metric and applied to another is not the
same comparison, so this script recomputes the floor per structure with cryo_metrics on the voxelised final meshes: the
final STL is rasterised onto the label grid slice by slice with an even-odd fill of every closed contour (see voxelise: the
noise-floor rasteriser silently dropped every slice with more than one contour because `rtree` is missing), the
original label is the reference, eligibility is the whole crop, one k-run per structure. Output: per structure Dice and
P95_vox, per class medians (P_vox_c), next to the old figures for comparison.

  .venv/bin/python scripts/denver-surface-floor.py     # about the runtime of denver-noise-floor.py; writes generated/denver-surface-floor.json

Training never uses the voxelised meshes (plan B 2.1); this only sets the surface bar. Nothing here is anatomy.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import h5py
import numpy as np
import trimesh
from skimage.draw import polygon as draw_polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cryo_metrics as M  # noqa: E402

MAT = ROOT / 'data/raw/denver/extracted/Original Segmentation Labelmaps-mat_tif/VHF_Full.mat'
OLD = ROOT / 'generated/denver-noise-floor.json'
OUT = ROOT / 'generated/denver-surface-floor.json'


def rd(ds):
    return ''.join(chr(int(c)) for c in np.array(ds[()]).ravel())


def voxelise(mesh_ijk, shape):
    """Rasterise a mesh given in voxel (i, j, k) coordinates onto a boolean grid (crop), slice by slice at integer k.

    Differs from scripts/denver-noise-floor.py on purpose (finding of 13 September 2026): that script fills the section
    with trimesh `polygons_full`, which needs the `rtree` package whenever a slice has more than one closed contour (a hole
    or two components); `rtree` is not installed, the exception was swallowed and every such slice was left EMPTY (27 of
    158 slices of the left calcaneus), which biased its Dice low and would have made a symmetric surface distance
    meaningless. Here every closed contour of the section is rasterised and combined even-odd (a contour inside a contour
    is a hole), which needs no spatial index. Returns the volume and the number of slices where the section failed."""
    out = np.zeros(shape, bool)
    k0, k1 = int(np.floor(mesh_ijk.bounds[0][2])), int(np.ceil(mesh_ijk.bounds[1][2]))
    failed = 0
    for k in range(max(k0, 0), min(k1, shape[2] - 1) + 1):
        path = mesh_ijk.section(plane_origin=[0, 0, float(k)], plane_normal=[0, 0, 1.0])
        if path is None or len(path.entities) == 0:
            continue
        try:
            p2, to_3d = path.to_2D()
            loops = p2.discrete
        except Exception as e:                      # a failed section would leave an empty slice and bias the floor: refuse
            raise RuntimeError(f'section failed at slice k={k}: {e!r}') from e
        if len(p2.dangling) or len(loops) != len(p2.paths) or not all(np.allclose(d[0], d[-1]) for d in loops):
            # trimesh lists only closed paths in `discrete`; an open polyline would silently rasterise to nothing
            raise RuntimeError(f'open contour in the section at slice k={k}: {len(p2.dangling)} dangling entities; the even-odd fill needs closed loops')
        mask = np.zeros((shape[0], shape[1]), bool)
        for d in loops:
            p3 = trimesh.transform_points(np.column_stack([np.asarray(d), np.zeros(len(d))]), to_3d)
            rr, cc = draw_polygon(p3[:, 0], p3[:, 1], shape=(shape[0], shape[1]))
            m = np.zeros((shape[0], shape[1]), bool); m[rr, cc] = True
            mask ^= m
        out[:, :, k] = mask
    return out, failed


def main():
    t0 = time.time()
    with h5py.File(MAT, 'r') as f:
        sd = f['segmentation_data']
        names = [rd(f[r]) for r in sd['geometry_labels']['name'][()].ravel()]
        ijk_to_lps = np.array(sd['ijkToLpsTransform']).T
        labels = np.transpose(np.array(sd['label_data']), (2, 1, 0))     # (i, j, k)
    denver = json.loads((ROOT / 'public/atlases/denver-vhf.json').read_text())
    stage = json.loads((ROOT / 'transforms/source-to-stage.json').read_text())
    stage_to_image = np.linalg.inv(np.array(stage['denver-image-to-stage']['matrix_row_major']).reshape(4, 4))
    buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in denver['chunks']]
    ras_to_ijk = np.linalg.inv(ijk_to_lps)
    old = json.loads(OLD.read_text())
    old_by = {e['structure']: e for e in old['structures']}
    name_index = {n: i for i, n in enumerate(names)}
    rows, unmatched = [], []
    for part in denver['parts']:
        m = part['source_metadata']; key = f"{m['source_folder']}_{m['tissue_class']}_{m['source_label']}"
        if key not in name_index:
            unmatched.append(key); continue
        lab = name_index[key]
        data = buffers[part['chunk']]
        v = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3).astype(float)
        fc = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices']).reshape(-1, 3)
        mesh = trimesh.Trimesh(trimesh.transform_points(v, stage_to_image), fc, process=False)
        mesh_ijk = trimesh.Trimesh(trimesh.transform_points(mesh.vertices, ras_to_ijk), mesh.faces, process=False)
        lo = np.maximum(np.floor(mesh_ijk.bounds[0]).astype(int) - 2, 0); hi = np.minimum(np.ceil(mesh_ijk.bounds[1]).astype(int) + 2, np.array(labels.shape) - 1)
        # the crop must hold every original voxel too, otherwise the surface pool misses them
        idx = np.argwhere(labels == lab)
        if len(idx):
            lo = np.minimum(lo, idx.min(axis=0)); hi = np.maximum(hi, idx.max(axis=0))
        orig = labels[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1, lo[2]:hi[2] + 1] == lab
        vox, failed = voxelise(trimesh.Trimesh(mesh_ijk.vertices - lo, mesh_ijk.faces, process=False), orig.shape)
        E = np.ones(orig.shape, bool)
        k_first = int(lo[2]); runs = [(k_first, int(hi[2]))]
        d = M.dice(vox, orig, E)
        s = M.surface_p95(vox, orig, E, runs, k_first)
        o = old_by.get(key, {})
        rows.append({'structure': key, 'label_value': lab, 'tissue_class': m['tissue_class'], 'mesh_watertight': bool(mesh.is_watertight), 'mesh_bodies': int(mesh.body_count), 'dice_vox': d, 'p95_vox_mm': s['p95_mm'], 'mean_vox_mm': s['mean_mm'],
                     'surface_status': s['status'], 'n_distances': s['n_distances'], 'section_failures': failed, 'support': s['support'], 'original_voxels': int(orig.sum()), 'final_voxels': int(vox.sum()),
                     'old_dice': o.get('dice'), 'old_p95_original_to_final_mm': (o.get('surface') or {}).get('original_to_final', {}).get('p95_mm')})
        print(f"{key:40s} Dice {d if d is not None else float('nan'):.3f}  p95_vox {s['p95_mm'] if s['p95_mm'] is not None else float('nan'):.3f} mm  (old o->f {rows[-1]['old_p95_original_to_final_mm']})", flush=True)
    per_class = {}
    for c in sorted({r['tissue_class'] for r in rows}):
        es = [r for r in rows if r['tissue_class'] == c and r['p95_vox_mm'] is not None]
        p = np.array([r['p95_vox_mm'] for r in es]); dd = np.array([r['dice_vox'] for r in es])
        per_class[c] = {'n': len(es), 'P_vox_p95_mm_median': float(np.median(p)), 'P_vox_p95_mm_p95': float(np.quantile(p, .95)), 'P_vox_p95_mm_max': float(p.max()),
                        'H_dice_vox_median': float(np.median(dd)), 'old_P_p95_mm_median': old['per_class'][c]['P_p95_mm_median'], 'old_H_dice_median': old['per_class'][c]['H_dice_median']}
        print(c, per_class[c], flush=True)
    report = {'method': __doc__.strip(), 'metric_implementation': 'scripts/cryo_metrics.py', 'metric_sha256': hashlib.sha256((ROOT / 'scripts/cryo_metrics.py').read_bytes()).hexdigest(),
              'old_floor': str(OLD.relative_to(ROOT)), 'old_floor_sha256': hashlib.sha256(OLD.read_bytes()).hexdigest(), 'mat_sha256': hashlib.sha256(MAT.read_bytes()).hexdigest(),
              'grid': {'spacing_mm': list(M.SPACING), 'ijk_to_lps': ijk_to_lps.tolist()}, 'structures': rows, 'unmatched': unmatched, 'per_class': per_class,
              'statement': 'effect of Denver post-processing measured with the pilot metric; sets the surface bar of the protocol; not human variability, not anatomy', 'seconds': round(time.time() - t0, 1)}
    OUT.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({'done': True, 'out': str(OUT.relative_to(ROOT)), 'per_class': per_class, 'seconds': report['seconds']}))


if __name__ == '__main__':
    main()
