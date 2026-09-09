"""H_c and P_c: agreement between Denver's original hand-painted label maps and Denver's final STL meshes.

Plan B section 2.1. This measures the effect of Denver's post-processing (smoothing, overclosure removal),
not human variability. It is the agreement level at which a machine label is indistinguishable from
Denver's own two versions of the same structure.

Input : data/raw/denver/extracted/Original Segmentation Labelmaps-mat_tif/VHF_Full.mat
        (Slicer export: label_data 3533 x 434 x 666 uint8 at 0.666 x 0.666 x 0.333 mm, LPS, 131 labels)
        public/atlases/denver-vhf.json + chunks (final STL meshes, viewer stage frame)
Output: generated/denver-noise-floor.json  per structure: Dice, surface p95 both directions, volumes;
        per class (bone, muscle, cartilage, ligament) medians and 5th percentiles.
Method: each final mesh is carried to the label-map voxel grid and voxelised by slicing it with every
        z plane of its extent (trimesh multiplane) and rasterising the section polygons; Dice against
        the original label of the same name. Surface p95 uses the marching-cubes surface of the label
        and the mesh surface, in millimetres, both directions.
"""
import json
from pathlib import Path
import h5py
import numpy as np
import trimesh
from skimage.draw import polygon as draw_polygon
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes

ROOT = Path(__file__).resolve().parents[1]
MAT = ROOT / 'data/raw/denver/extracted/Original Segmentation Labelmaps-mat_tif/VHF_Full.mat'
RNG = np.random.default_rng(1993)

f = h5py.File(MAT, 'r'); sd = f['segmentation_data']
rd = lambda ds: ''.join(chr(int(c)) for c in np.array(ds[()]).ravel())
names = [rd(f[r]) for r in sd['geometry_labels']['name'][()].ravel()]
ijk_to_lps = np.array(sd['ijkToLpsTransform']).T   # MATLAB stores the 4x4 column-major: translation sits in the last row of the raw array
labels = np.array(sd['label_data'])            # (k, j, i) = (3533, 434, 666)
labels = np.transpose(labels, (2, 1, 0))         # -> (i, j, k) = (666, 434, 3533)
spacing = np.array([0.666, 0.666, 0.333])

denver = json.loads((ROOT / 'public/atlases/denver-vhf.json').read_text())
stage = json.loads((ROOT / 'transforms/source-to-stage.json').read_text())
stage_to_image = np.linalg.inv(np.array(stage['denver-image-to-stage']['matrix_row_major']).reshape(4, 4))
buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in denver['chunks']]

def centroid_ijk(lab):
    idx = np.argwhere(labels == lab)
    return idx.mean(axis=0)

def mesh_of(part):
    data = buffers[part['chunk']]
    v = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3).astype(float)
    fc = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices']).reshape(-1, 3)
    return trimesh.Trimesh(trimesh.transform_points(v, stage_to_image), fc, process=False)   # VHF image frame, mm

def voxelise(mesh_ijk, shape):
    """Rasterise a mesh given in voxel (i, j, k) coordinates onto a boolean grid of `shape` (crop)."""
    out = np.zeros(shape, bool)
    k0, k1 = int(np.floor(mesh_ijk.bounds[0][2])), int(np.ceil(mesh_ijk.bounds[1][2]))
    ks = np.arange(max(k0, 0), min(k1, shape[2] - 1) + 1)
    if not len(ks): return out
    origin = np.array([0, 0, ks[0]], float); normal = np.array([0, 0, 1.0])
    paths = mesh_ijk.section_multiplane(origin, normal, (ks - ks[0]).astype(float))
    for k, path in zip(ks, paths):
        if path is None or len(path.entities) == 0: continue
        to_3d = path.metadata['to_3D']
        try:
            polys = path.polygons_full
        except Exception:
            continue
        mask = np.zeros((shape[0], shape[1]), bool)
        def ij(coords):   # local 2D plane coordinates -> voxel (i, j) of the grid
            p3 = trimesh.transform_points(np.column_stack([np.asarray(coords), np.zeros(len(coords))]), to_3d)
            return p3[:, 0], p3[:, 1]
        for poly in polys:
            i, j = ij(poly.exterior.coords)
            rr, cc = draw_polygon(i, j, shape=(shape[0], shape[1]))
            mask[rr, cc] = True
            for hole in poly.interiors:
                i, j = ij(hole.coords)
                rr, cc = draw_polygon(i, j, shape=(shape[0], shape[1]))
                mask[rr, cc] = False
        out[:, :, k] = mask
    return out

def surface_points(mask, offset_ijk):
    v, fc, _, _ = marching_cubes(np.pad(mask.astype(np.uint8), 1), 0.5)
    v = v - 1 + offset_ijk
    return trimesh.transform_points(v, ijk_to_ras)

def stats(d):
    return {'mean_mm': float(d.mean()), 'p95_mm': float(np.quantile(d, .95)), 'max_mm': float(d.max())}

# Frame: the final meshes live in the same LPS millimetre frame as the label map (checked 2026-09-09 on 123
# structure pairs: z extents of label and mesh coincide to the voxel, e.g. left femur z 488 to 905 mm in both;
# a vertex-mean centroid is biased by vertex density and must not be used to estimate offsets).
ijk_to_ras = ijk_to_lps.copy()
ras_to_ijk = np.linalg.inv(ijk_to_ras)
frame_note = {'axes': 'LPS as stored in VHF_Full.mat (ijkToLpsTransform, transposed from the MATLAB column-major array)', 'offset_applied_mm': [0.0, 0.0, 0.0]}
print('frame:', frame_note, flush=True)

report = {'method': __doc__.strip(), 'frame': frame_note, 'grid': {'shape_ijk': list(labels.shape), 'spacing_mm': spacing.tolist(), 'ijk_to_ras': ijk_to_ras.tolist()}, 'structures': [], 'unmatched': []}
name_index = {n: i for i, n in enumerate(names)}
for part in denver['parts']:
    m = part['source_metadata']; key = f"{m['source_folder']}_{m['tissue_class']}_{m['source_label']}"
    if key not in name_index:
        report['unmatched'].append({'part': part['id'], 'key': key}); continue
    lab = name_index[key]
    mesh = mesh_of(part)
    mesh_ijk = trimesh.Trimesh(trimesh.transform_points(mesh.vertices, ras_to_ijk), mesh.faces, process=False)
    lo = np.maximum(np.floor(mesh_ijk.bounds[0]).astype(int) - 2, 0); hi = np.minimum(np.ceil(mesh_ijk.bounds[1]).astype(int) + 2, np.array(labels.shape) - 1)
    orig = labels[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1, lo[2]:hi[2] + 1] == lab
    # also count original voxels outside the mesh box (they count against Dice)
    total_orig = int((labels == lab).sum()); outside = total_orig - int(orig.sum())
    crop_mesh = trimesh.Trimesh(mesh_ijk.vertices - lo, mesh_ijk.faces, process=False)
    vox = voxelise(crop_mesh, orig.shape)
    inter = int((vox & orig).sum()); dice = 2 * inter / (int(vox.sum()) + total_orig) if (vox.sum() + total_orig) else float('nan')
    if orig.any() and vox.any():
        so = surface_points(orig, lo); sm = np.vstack([trimesh.sample.sample_surface(mesh, 20000, seed=int(RNG.integers(1 << 31)))[0], mesh.vertices])
        d_orig_to_final = cKDTree(sm).query(so)[0]; d_final_to_orig = cKDTree(so).query(sm)[0]
        surf = {'original_to_final': stats(d_orig_to_final), 'final_to_original': stats(d_final_to_orig)}
    else:
        surf = None
    entry = {'structure': key, 'label_value': lab, 'tissue_class': m['tissue_class'], 'dice': dice, 'original_voxels': total_orig, 'original_voxels_outside_final_box': outside,
             'final_voxels': int(vox.sum()), 'original_volume_cm3': float(total_orig * spacing.prod() / 1000), 'final_volume_cm3': float(abs(mesh.volume) / 1000), 'surface': surf}
    report['structures'].append(entry)
    print(f"{key:36s} Dice {dice:.3f}  orig {entry['original_volume_cm3']:7.1f} cm3  final {entry['final_volume_cm3']:7.1f} cm3  p95 o->f {surf['original_to_final']['p95_mm'] if surf else float('nan'):.2f} f->o {surf['final_to_original']['p95_mm'] if surf else float('nan'):.2f} mm", flush=True)

classes = {}
for e in report['structures']:
    classes.setdefault(e['tissue_class'], []).append(e)
report['per_class'] = {}
for c, es in classes.items():
    d = np.array([e['dice'] for e in es]); p = np.array([e['surface']['original_to_final']['p95_mm'] for e in es if e['surface']])
    report['per_class'][c] = {'n': len(es), 'H_dice_median': float(np.median(d)), 'H_dice_p05': float(np.quantile(d, .05)), 'H_dice_min': float(d.min()),
                              'P_p95_mm_median': float(np.median(p)), 'P_p95_mm_p95': float(np.quantile(p, .95))}
    print(c, report['per_class'][c])
(ROOT / 'generated/denver-noise-floor.json').write_text(json.dumps(report, indent=1) + '\n')
print('unmatched', len(report['unmatched']))
