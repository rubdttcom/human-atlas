"""Compare BMFToolkit bones with the Denver VHF bones of the same donor, bone by bone, without shipping them.

BMFToolkit (Sreenivasa & Gonzalez-Alvarado, zlib LICENSE at the repository root) contains lower-body
bone meshes extracted from the Visible Human Female CT: right-side bones segmented, left side mirrored,
sacrum symmetrized, neutral-pose corrected and smoothed. Denver VHF bones come from the cryosections of
the same donor. Because the two sets are in different poses and frames, every bone is aligned by a
rigid ICP (no scale) before measuring surface distances; the recorded transform is a comparison aid,
not a composition transform. Output: generated/bmftoolkit-comparison.json.
"""
import json
from pathlib import Path
import numpy as np
import trimesh
from scipy.io import loadmat
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
RNG = np.random.default_rng(1804)
models = loadmat(ROOT / 'sources/BMFToolkit/data/model_Original.mat', simplify_cells=True)['model_Original']
denver = json.loads((ROOT / 'public/atlases/denver-vhf.json').read_text())
buffers = [(ROOT / 'public' / c['url'].lstrip('/')).read_bytes() for c in denver['chunks']]
denver_meshes = {}
for part in denver['parts']:
    meta = part['source_metadata']
    if meta['tissue_class'] != 'Bone':
        continue
    data = buffers[part['chunk']]
    vertices = np.frombuffer(data, '<f4', count=part['vertexCount'] * 3, offset=part['positions']).reshape(-1, 3).astype(float)
    faces = np.frombuffer(data, '<u4', count=part['indexCount'], offset=part['indices']).reshape(-1, 3)
    denver_meshes[(meta['source_folder'], meta['source_label'])] = (part['id'], trimesh.Trimesh(vertices, faces, process=False))

# BMF name -> Denver (folder, label). Feet phalanges and metatarsals are single Denver meshes per foot; BMF has them per bone.
SIMPLE = {'Sacrum': ('Left', 'Sacrum'), 'Pelvis': 'Pelvis', 'Femur': 'Femur', 'Patella': 'Patella', 'Tibia': 'Tibia', 'Fibula': 'Fibula', 'Talus': 'Talus',
          'Calcaneus': 'Calcaneous', 'Navicular': 'Navicular', 'Cuboid': 'Cuboid', 'MedialCuneiform': 'MedialCuneiform',
          'IntermediateCuneiform': 'IntermediateCuneiform', 'LateralCuneiform': 'LateralCuneiform'}
GROUPS = {'Phalanges': ('FirstProxPhalanx', 'SecondProxPhalanx', 'ThirdProxPhalanx', 'FourthProxPhalanx', 'FifthProxPhalanx', 'SecondMidPhalanx',
                        'ThirdMidPhalanx', 'FourthMidPhalanx', 'FifthMidPhalanx', 'FirstDistPhalanx', 'SecondDistPhalanx', 'ThirdDistPhalanx',
                        'FourthDistPhalanx', 'FifthDistPhalanx')}


def bmf_mesh(model):
    return trimesh.Trimesh(np.asarray(model['vertices_global'], dtype=float), np.asarray(model['faces'], dtype=int) - 1, process=False)


def samples(mesh, count):
    points, _ = trimesh.sample.sample_surface(mesh, count, seed=int(RNG.integers(1 << 31)))
    return np.vstack([points, mesh.vertices])


def compare(source, target):
    """Rigid ICP of `source` onto `target` after centroid alignment and principal-axis pre-alignment; symmetric sampled distances in mm."""
    src = samples(source, 20000)
    tgt = samples(target, 40000)
    best = None
    # Principal axes give four candidate initial orientations (sign ambiguity); keep the ICP with the lowest cost.
    def axes(points):
        centred = points - points.mean(axis=0)
        _, _, vt = np.linalg.svd(centred, full_matrices=False)
        if np.linalg.det(vt) < 0:
            vt[2] *= -1   # right-handed principal frame
        return vt
    a_src, a_tgt = axes(src), axes(tgt)
    for flips in ([1, 1, 1], [-1, -1, 1], [-1, 1, -1], [1, -1, -1]):
        rotation = a_tgt.T @ (np.diag(flips) @ a_src)
        if np.linalg.det(rotation) < 0:
            continue
        initial = np.eye(4)
        initial[:3, :3] = rotation
        initial[:3, 3] = tgt.mean(axis=0) - rotation @ src.mean(axis=0)
        matrix, _, cost = trimesh.registration.icp(src, tgt, initial=initial, scale=False, max_iterations=60)
        if best is None or cost < best[1]:
            best = (matrix, cost)
    matrix = best[0]
    moved = trimesh.Trimesh(trimesh.transform_points(source.vertices, matrix), source.faces, process=False)
    ms, mt = samples(moved, 30000), samples(target, 30000)
    d_st = cKDTree(mt).query(ms)[0] * 1000
    d_ts = cKDTree(ms).query(mt)[0] * 1000
    stats = lambda d: {'mean_mm': float(d.mean()), 'rms_mm': float(np.sqrt(np.mean(d ** 2))), 'p95_mm': float(np.quantile(d, .95)), 'max_mm': float(d.max())}
    return {'rigid_icp_matrix_row_major': matrix.ravel().tolist(), 'bmf_to_denver': stats(d_st), 'denver_to_bmf': stats(d_ts),
            'hausdorff_mm': float(max(d_st.max(), d_ts.max())), 'bmf_volume_cm3': float(abs(source.volume) * 1e6), 'denver_volume_cm3': float(abs(target.volume) * 1e6),
            'bmf_extent_mm': ((source.bounds[1] - source.bounds[0]) * 1000).tolist(), 'denver_extent_mm': ((target.bounds[1] - target.bounds[0]) * 1000).tolist(),
            'volume_ratio_bmf_over_denver': float(abs(source.volume) / abs(target.volume)) if target.volume else None}


by_name = {m['BoneName']: m for m in models}
results = []
for model in models:
    name = model['BoneName']
    side = 'R' if name.endswith('R') else 'L' if name.endswith('L') else ''
    stem = name[:-1] if side else name
    folder = {'R': 'Right', 'L': 'Left', '': 'Left'}[side]
    if stem in SIMPLE:
        key = SIMPLE[stem] if isinstance(SIMPLE[stem], tuple) else (folder, SIMPLE[stem])
        if key not in denver_meshes:
            continue
        denver_id, target = denver_meshes[key]
        entry = {'bmf_asset': name, 'bmf_geometry': 'segmented_right' if side == 'R' else 'mirrored_from_right' if side == 'L' else 'symmetrized',
                 'denver_asset': denver_id, **compare(bmf_mesh(model), target)}
        results.append(entry)
        print(f"{name} vs {denver_id}: p95 {entry['bmf_to_denver']['p95_mm']:.1f} mm, Hausdorff {entry['hausdorff_mm']:.1f} mm, volume ratio {entry['volume_ratio_bmf_over_denver']:.3f}", flush=True)
for side, folder in (('R', 'Right'), ('L', 'Left')):
    for denver_label, stems in GROUPS.items():
        pieces = [bmf_mesh(by_name[s + side]) for s in stems if (s + side) in by_name]
        if not pieces or (folder, denver_label) not in denver_meshes:
            continue
        denver_id, target = denver_meshes[(folder, denver_label)]
        # Phalanges are compared as one set: individual toe pose differs, so only the set-level distance is meaningful.
        entry = {'bmf_asset': f'{denver_label}{side} (set of {len(pieces)} BMF meshes)', 'bmf_geometry': 'segmented_right' if side == 'R' else 'mirrored_from_right',
                 'denver_asset': denver_id, 'note': 'set-level rigid alignment; individual toe poses differ between the CT and cryosection sets', **compare(trimesh.util.concatenate(pieces), target)}
        results.append(entry)
        print(f"{entry['bmf_asset']} vs {denver_id}: p95 {entry['bmf_to_denver']['p95_mm']:.1f} mm, Hausdorff {entry['hausdorff_mm']:.1f} mm", flush=True)
metatarsals = {}
for side, folder in (('R', 'Right'), ('L', 'Left')):
    pieces = [bmf_mesh(by_name[s + 'Metatarsal' + side]) for s in ('First', 'Second', 'Third', 'Fourth', 'Fifth') if (s + 'Metatarsal' + side) in by_name]
    metatarsals[side] = pieces
report = {'method': __doc__.strip(), 'not_shipped': True, 'licence_evidence': {
    'repository_license_file': 'sources/BMFToolkit/LICENSE (zlib licence text; "this software"; no separate data terms; the data folder is part of the same distribution)',
    'zenodo_record': 'https://doi.org/10.5281/zenodo.889060 (license id other-open, access open)',
    'github_api_license': 'NOASSERTION (non-standard licence header)',
    'position': 'zlib is permissive and OSI-approved, but its text addresses software; whether the authors intend it to cover the mesh data is not stated. Meshes stay out of the shipped atlases until the authors confirm; see docs/LICENSING.md for the prepared request.'},
    'comparisons': results,
    'summary': {'bones_compared': len(results),
                'median_p95_mm_segmented_right': float(np.median([r['bmf_to_denver']['p95_mm'] for r in results if r['bmf_geometry'] == 'segmented_right'])) if results else None,
                'median_p95_mm_mirrored_left': float(np.median([r['bmf_to_denver']['p95_mm'] for r in results if r['bmf_geometry'] == 'mirrored_from_right'])) if results else None,
                'interpretation': 'Same donor, different modality (CT versus cryosection) and processing (BMF neutral-pose correction, smoothing, mirroring). Small residuals after rigid ICP support that both sets describe the same bones; the mirrored left side should show larger residuals than the segmented right side where the donor is asymmetric.'}}
(ROOT / 'generated/bmftoolkit-comparison.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report['summary'], indent=1))
