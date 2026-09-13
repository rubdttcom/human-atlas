"""Trunk posture offset: the fresh NLM CT against Denver's aligned CT, per vertebra and rib.

CORRECTION (13 September 2026, after this script ran): Denver's aligned CT is the NLM fresh CT resampled into the
cryosection frame, not a CT of the frozen block (NLM's female index has no frozen CT; the two volumes agree to NCC 0.998
after a local shift). The premise below is therefore wrong: what this script measures is the inconsistency between two
rigid pelvis placements of ONE acquisition (`nlm-ct-to-vhf` and `denver-aligned-ct-voxel-to-vhf`) plus resampling, not
posture. The fresh-versus-frozen difference is measured by scripts/check-photo-ct-alignment.py against the photographs.
The output fields keep their names until the pipeline-wide rename is decided (docs/PROGRESS.md backlog).

Plan B stage 0, first item (moved forward 12 September 2026). Both CTs are of the same donor. The fresh CT was
acquired on a table before freezing; Denver's aligned CT is the frozen block, resampled into the cryosection frame.
Each CT carries the same consensus instances (`scripts/ct-vertebra-instances.py`: 25 vertebrae + sacrum, 12 ribs per
side; ids are geometric, cranial to caudal, names pending). The two CTs are placed in the canonical frame
`VHF-image-2022` by two independent rigid fits of their pelvis onto the Denver pelvis meshes
(`transforms/nlm-ct-to-vhf.json`, `transforms/denver-aligned-ct-voxel-to-vhf.json`). Whatever remains between the
same instance on the two CTs, above the pelvis, is the posture difference plus the two registration errors plus the
two segmentation differences. This script measures that remainder; it does not correct it and it does not attribute
it. Segmenter agreement does not correct registration or posture.

Per instance (matched by geometric id, then verified by nearest transformed centroid):
  centroid_offset_vhf_mm      Denver minus NLM centroid in VHF mm (+x subject right, +y anterior, +z superior)
  surface_distance_placed     NLM surface -> Denver surface (and back) as placed by the two transforms
  own_rigid_fit               rigid ICP (no scale) of the NLM instance surface onto the Denver one: rotation (deg,
                              axis-angle components about x = sagittal flexion/extension, y = frontal tilt,
                              z = axial), translation, and the residual after the fit (segmentation, discretisation, sampling and fit limits)
  model_spread                the centroid offset recomputed with each model's own instance map; the range across
                              models is one observable component of the discrepancy (models may share bias)
Anchors: pelvis (TotalSegmentator hips + consensus sacrum) and skull, same measures. The pelvis is what both
registrations fitted, so its offset is the anchor offset shared by every level. This calculation does not identify its
cause (registration translation, angular registration error, anchor segmentation); subtracting it removes one
translational reference only, never angular registration error (0.5 deg gives about 5 mm at 600 mm from the pelvis).
Chain: one rigid fit (Kabsch) of all vertebra centroids NLM -> Denver, whole spine and per region, with residuals
per level, to separate a global trunk rotation from local intervertebral change.
Controls: each NLM vertebra against the next caudal Denver instance (must show the inter-level spacing).

Output: generated/trunk-posture-offset.json and generated/trunk-posture-offset.png. Nothing here is anatomy: the
figures are distances between two automatic segmentations of two CTs under two automatic registrations.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import nibabel as nib
import numpy as np
import trimesh
from scipy import ndimage
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from skimage.measure import marching_cubes

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'generated/trunk-posture-offset.json'
PNG = ROOT / 'generated/trunk-posture-offset.png'
MODELS = ('totalseg', 'moose', 'skellytour')
TS_CLASS = {v: int(k) for k, v in json.loads((ROOT / 'data/derived/nlm-vhf/totalseg-classmap.json').read_text())['total'].items()}
SAMPLE = 20000
SEED = 1993
REGIONS = {'cervical': range(1, 8), 'thoracic': range(8, 20), 'lumbar_type': (20, 21, 22, 25, 26, 27)}

CT = {
    'nlm': {'consensus': ROOT / 'data/derived/nlm-vhf/consensus', 'totalseg': ROOT / 'data/derived/nlm-vhf/totalseg.nii',
            'instances_json': ROOT / 'generated/ct-vertebra-instances-nlm.json',
            'transform': ROOT / 'transforms/nlm-ct-to-vhf.json', 'transform_applies_to': 'RAS mm (image affine first)'},
    'denver': {'consensus': ROOT / 'data/derived/denver/priors/consensus', 'totalseg': ROOT / 'data/derived/denver/priors/totalseg/total.nii.gz',
               'instances_json': ROOT / 'generated/ct-vertebra-instances-denver.json',
               'transform': ROOT / 'transforms/denver-aligned-ct-voxel-to-vhf.json', 'transform_applies_to': 'voxel index'},
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 24), b''):
            h.update(chunk)
    return h.hexdigest()


class Volume:
    """One CT's label maps and its voxel -> VHF matrix."""

    def __init__(self, name):
        cfg = CT[name]
        self.name = name
        img = nib.load(cfg['consensus'] / 'vertebra-instances.nii.gz')
        self.affine = img.affine
        self.shape = img.shape
        T = np.array(json.loads(cfg['transform'].read_text())['matrix_row_major']).reshape(4, 4)
        self.vox_to_vhf = T @ img.affine if name == 'nlm' else T
        self.spacing = np.array(img.header.get_zooms()[:3], float)
        self.maps = {'vertebra': np.asanyarray(img.dataobj)}
        for side in ('left', 'right'):
            self.maps[f'rib-{side}'] = np.asanyarray(nib.load(cfg['consensus'] / f'rib-{side}-instances.nii.gz').dataobj)
        self.model_maps = {m: np.asanyarray(nib.load(cfg['consensus'] / f'vertebra-model-{m}.nii.gz').dataobj) for m in MODELS}
        self.totalseg = np.asanyarray(nib.load(cfg['totalseg']).dataobj)
        self.inputs = {'vertebra-instances': cfg['consensus'] / 'vertebra-instances.nii.gz',
                       'rib-left-instances': cfg['consensus'] / 'rib-left-instances.nii.gz', 'rib-right-instances': cfg['consensus'] / 'rib-right-instances.nii.gz',
                       **{f'vertebra-model-{m}': cfg['consensus'] / f'vertebra-model-{m}.nii.gz' for m in MODELS}, 'totalseg': cfg['totalseg']}

    def to_vhf(self, ijk):
        p = np.c_[np.asarray(ijk, float), np.ones(len(ijk))]
        return (self.vox_to_vhf @ p.T).T[:, :3]

    def instance(self, mask_source, value):
        """Centroid (VHF mm), surface points (VHF mm) and volume (mL) of one label value; None when absent."""
        mask = mask_source == value
        if not mask.any():
            return None
        # bounding box from per-axis projections (find_objects on the full grid costs seconds per call)
        box = []
        for ax in range(3):
            other = tuple(k for k in range(3) if k != ax)
            hit = np.flatnonzero(mask.any(axis=other))
            box.append(slice(int(hit[0]), int(hit[-1]) + 1))
        pad = tuple(slice(max(0, s.start - 1), min(n, s.stop + 1)) for s, n in zip(box, mask.shape))
        sub = mask[pad]
        off = np.array([s.start for s in pad])
        idx = np.argwhere(sub) + off
        centroid = self.to_vhf(idx).mean(axis=0)
        verts, faces, _, _ = marching_cubes(sub.astype(np.uint8), 0.5)
        surface = self.to_vhf(verts + off)
        return {'centroid': centroid, 'surface': surface, 'volume_ml': float(idx.shape[0] * np.prod(self.spacing) / 1000.0),
                'voxels': int(idx.shape[0])}

    def union(self, pairs):
        """Union of several (array, value) masks as one instance."""
        mask = np.zeros(self.shape, bool)
        for arr, value in pairs:
            mask |= arr == value
        return self.instance(mask, True)


def stats(d):
    return {'mean_mm': round(float(d.mean()), 2), 'rms_mm': round(float(np.sqrt(np.mean(d ** 2))), 2), 'p95_mm': round(float(np.quantile(d, .95)), 2),
            'max_mm': round(float(d.max()), 2), 'n': int(len(d))}


def subsample(pts, rng, n=SAMPLE):
    if len(pts) <= n:
        return pts
    return pts[rng.choice(len(pts), n, replace=False)]


def rotation_report(R):
    rv = Rotation.from_matrix(R).as_rotvec(degrees=True)
    return {'angle_deg': round(float(np.linalg.norm(rv)), 3),
            'about_x_right_deg': round(float(rv[0]), 3), 'about_y_anterior_deg': round(float(rv[1]), 3), 'about_z_superior_deg': round(float(rv[2]), 3)}


def compare(a, b, rng):
    """NLM instance `a` against Denver instance `b` (both dicts from Volume.instance)."""
    offset = b['centroid'] - a['centroid']
    sa, sb = subsample(a['surface'], rng), subsample(b['surface'], rng)
    tree_b = cKDTree(sb); tree_a = cKDTree(sa)
    placed = {'nlm_to_denver': stats(tree_b.query(sa)[0]), 'denver_to_nlm': stats(tree_a.query(sb)[0])}
    centre = sa.mean(axis=0)
    m, moved, _ = trimesh.registration.icp(sa - centre, sb - centre, initial=np.eye(4), scale=False, max_iterations=60, threshold=1e-7)
    moved = moved + centre
    after = {'nlm_to_denver': stats(tree_b.query(moved)[0]), 'denver_to_nlm': stats(cKDTree(moved).query(sb)[0])}
    return {'centroid_offset_vhf_mm': {'x_right': round(float(offset[0]), 2), 'y_anterior': round(float(offset[1]), 2), 'z_superior': round(float(offset[2]), 2),
                                       'norm': round(float(np.linalg.norm(offset)), 2)},
            'volume_ml': {'nlm': round(a['volume_ml'], 2), 'denver': round(b['volume_ml'], 2)},
            'surface_distance_placed': placed,
            'own_rigid_fit': {**rotation_report(m[:3, :3]), 'translation_mm': [round(float(v), 2) for v in (moved.mean(axis=0) - centre)],
                              'residual_after_fit': after}}


def kabsch(P, Q):
    """Rigid R, t with Q ~ R P + t (least squares)."""
    pc, qc = P.mean(axis=0), Q.mean(axis=0)
    H = (P - pc).T @ (Q - qc)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1, 1, d])
    R = Vt.T @ D @ U.T
    t = qc - R @ pc
    return R, t


def chain_fit(levels, ids):
    P = np.array([levels[i]['nlm_centroid'] for i in ids]); Q = np.array([levels[i]['denver_centroid'] for i in ids])
    if len(ids) < 3:
        return None
    R, t = kabsch(P, Q)
    res = np.linalg.norm((P @ R.T + t) - Q, axis=1)
    sv = np.linalg.svd(P - P.mean(axis=0), compute_uv=False)
    ill = bool(sv[1] / sv[0] < 0.15)
    return {'ids': [f'V{i:02d}' for i in ids], **rotation_report(R), 'translation_mm': [round(float(v), 2) for v in t],
            'centroid_spread_singular_values_mm': [round(float(s), 1) for s in sv],
            'rotation_about_spine_axis_ill_determined': ill,
            'note': ('the centroids are nearly collinear (second singular value below 15 % of the first): the rotation about the spine axis and the translation are not physical; read the residuals only'
                     if ill else 'centroids spread enough in two directions for the rigid fit to be determined; the translation is the centroid shift of the region'),
            'residual_after_chain_fit_mm': {f'V{i:02d}': round(float(r), 2) for i, r in zip(ids, res)},
            'residual_rms_mm': round(float(np.sqrt(np.mean(res ** 2))), 2), 'residual_max_mm': round(float(res.max()), 2)}


def draw_panel(levels, order, anchors):
    from PIL import Image, ImageDraw
    W, H = 1400, 900
    img = Image.new('RGB', (W, H), 'white'); d = ImageDraw.Draw(img)
    rows = [('x_right', 'centroid offset x (right) mm'), ('y_anterior', 'centroid offset y (anterior) mm'), ('z_superior', 'centroid offset z (superior) mm'), ('angle', 'own rigid fit rotation deg')]
    left, top, rh, gap = 90, 40, 190, 25
    n = len(order); bw = (W - left - 40) / n
    d.text((left, 8), 'Trunk posture offset: Denver aligned CT minus NLM fresh CT, per consensus instance (VHF frame). Not anatomy: posture + registration + segmentation.', fill='black')
    for r, (key, title) in enumerate(rows):
        y0 = top + r * (rh + gap)
        vals = [(levels[i]['own_rigid_fit']['angle_deg'] if key == 'angle' else levels[i]['centroid_offset_vhf_mm'][key]) for i in order]
        lim = max(1.0, max(abs(v) for v in vals)) * 1.15
        mid = y0 + rh / 2
        d.text((left, y0 - 14), f'{title}   range [{min(vals):.1f}, {max(vals):.1f}]   pelvis anchor {anchors.get(key, 0):.1f}', fill='black')
        d.line([(left, mid), (W - 40, mid)], fill='grey')
        for k, (i, v) in enumerate(zip(order, vals)):
            x0 = left + k * bw + 2; x1 = x0 + bw - 4
            h = v / lim * (rh / 2)
            colour = (200, 60, 60) if abs(v) > abs(anchors.get(key, 0)) + (2 if key != 'angle' else 1) else (60, 110, 200)
            d.rectangle([x0, mid - max(h, 0), x1, mid - min(h, 0)], fill=colour)
            if r == 3:
                d.text((x0, y0 + rh + 4), levels[i]['id'], fill='black')
    img.save(PNG)


def main():
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    vols = {n: Volume(n) for n in ('nlm', 'denver')}
    print('loaded', {n: v.shape for n, v in vols.items()}, f'{time.time() - t0:.0f} s', flush=True)
    tables = {n: json.loads(CT[n]['instances_json'].read_text()) for n in vols}
    roster = {n: {i['index']: i for i in tables[n]['instances']} for n in vols}
    full_ids = sorted(set(i for i, r in roster['nlm'].items() if r['size_class'] == 'full' and r['consensus_ml'] > 0)
                      & set(i for i, r in roster['denver'].items() if r['size_class'] == 'full' and r['consensus_ml'] > 0))
    nlm, den = vols['nlm'], vols['denver']

    # vertebrae and sacrum -------------------------------------------------------------------------------
    inst = {n: {} for n in vols}
    for i in full_ids:
        for n, v in vols.items():
            inst[n][i] = v.instance(v.maps['vertebra'], i)
    levels = {}
    den_centroids = {i: inst['denver'][i]['centroid'] for i in full_ids}
    for i in full_ids:
        a, b = inst['nlm'][i], inst['denver'][i]
        nearest = min(full_ids, key=lambda j: np.linalg.norm(den_centroids[j] - a['centroid']))
        rec = {'id': f"{'S' if roster['nlm'][i]['role'] == 'sacrum' else 'V'}{i:02d}", 'index': i, 'role': roster['nlm'][i]['role'],
               'hra_name_by_order': roster['nlm'][i].get('hra_name_by_order'), 'name_status': 'pending',
               'match': 'same geometric id' + ('' if nearest == i else f'; WARNING nearest Denver instance is {nearest}'),
               'nlm_centroid': inst['nlm'][i]['centroid'].round(2).tolist(), 'denver_centroid': inst['denver'][i]['centroid'].round(2).tolist(),
               **compare(a, b, rng)}
        spread = {}
        for m in MODELS:
            am, bm = nlm.instance(nlm.model_maps[m], i), den.instance(den.model_maps[m], i)
            if am is None or bm is None:
                spread[m] = None
                continue
            o = bm['centroid'] - am['centroid']
            spread[m] = {'x_right': round(float(o[0]), 2), 'y_anterior': round(float(o[1]), 2), 'z_superior': round(float(o[2]), 2), 'norm': round(float(np.linalg.norm(o)), 2)}
        present = [s for s in spread.values() if s]
        rec['model_spread'] = {'per_model': spread,
                               'range_of_norm_mm': round(max(s['norm'] for s in present) - min(s['norm'] for s in present), 2) if len(present) > 1 else None,
                               'max_component_range_mm': round(max(max(s[k] for s in present) - min(s[k] for s in present) for k in ('x_right', 'y_anterior', 'z_superior')), 2) if len(present) > 1 else None,
                               'models_present_on_both': len(present)}
        levels[i] = rec
        print(rec['id'], rec['centroid_offset_vhf_mm'], 'rot', rec['own_rigid_fit']['angle_deg'], f'{time.time() - t0:.0f} s', flush=True)

    # neighbour control ------------------------------------------------------------------------------------
    vert_ids = [i for i in full_ids if roster['nlm'][i]['role'] == 'vertebra']
    controls = []
    for i, j in zip(vert_ids[:-1], vert_ids[1:]):
        o = inst['denver'][j]['centroid'] - inst['nlm'][i]['centroid']
        controls.append({'nlm': f'V{i:02d}', 'denver': f'V{j:02d}', 'centroid_offset_norm_mm': round(float(np.linalg.norm(o)), 2)})

    # ribs -----------------------------------------------------------------------------------------------
    ribs = {}
    for side in ('left', 'right'):
        for k in range(1, 13):
            a, b = nlm.instance(nlm.maps[f'rib-{side}'], k), den.instance(den.maps[f'rib-{side}'], k)
            if a is None or b is None:
                ribs[f'R{side[0].upper()}{k:02d}'] = {'status': 'absent on one CT'}
                continue
            ribs[f'R{side[0].upper()}{k:02d}'] = {'side': side, 'order': k, 'name_status': 'pending', **compare(a, b, rng)}
            print(f'R{side[0].upper()}{k:02d}', ribs[f'R{side[0].upper()}{k:02d}']['centroid_offset_vhf_mm'], f'{time.time() - t0:.0f} s', flush=True)

    # anchors --------------------------------------------------------------------------------------------
    sac = next((i for i in full_ids if roster['nlm'][i]['role'] == 'sacrum'), None)
    anchors = {}
    pel = {n: v.union([(v.totalseg, TS_CLASS['hip_left']), (v.totalseg, TS_CLASS['hip_right'])] + ([(v.maps['vertebra'], sac)] if sac else [])) for n, v in vols.items()}
    anchors['pelvis'] = {'definition': 'TotalSegmentator hip_left + hip_right of each CT' + (' + consensus sacrum' if sac else ''),
                         'meaning': 'what both registrations fitted onto the Denver pelvis meshes: its offset is shared by every level; this calculation does not identify its cause (registration, angular error, anchor segmentation)', **compare(pel['nlm'], pel['denver'], rng)}
    sk = {n: v.instance(v.totalseg, TS_CLASS['skull']) for n, v in vols.items()}
    if all(sk.values()):
        anchors['skull'] = {'definition': 'TotalSegmentator skull of each CT', **compare(sk['nlm'], sk['denver'], rng)}
    for side in ('left', 'right'):
        h = {n: v.instance(v.totalseg, TS_CLASS[f'hip_{side}']) for n, v in vols.items()}
        if all(h.values()):
            anchors[f'hip_{side}'] = {'definition': f'TotalSegmentator hip_{side}', **compare(h['nlm'], h['denver'], rng)}
    print('anchors', {k: v['centroid_offset_vhf_mm']['norm'] for k, v in anchors.items()}, flush=True)

    # chain fits -----------------------------------------------------------------------------------------
    chain = {'whole_spine': chain_fit(levels, vert_ids)}
    for region, ids in REGIONS.items():
        ids = [i for i in ids if i in levels]
        chain[region] = chain_fit(levels, ids)

    # uncertainty per level ------------------------------------------------------------------------------
    floor = anchors['pelvis']['centroid_offset_vhf_mm']['norm']
    floor_surface = anchors['pelvis']['surface_distance_placed']['nlm_to_denver']['p95_mm']
    common = np.array([anchors['pelvis']['centroid_offset_vhf_mm'][k] for k in ('x_right', 'y_anterior', 'z_superior')])
    pelvis_parts = [a for k, a in anchors.items() if k in ('pelvis', 'hip_left', 'hip_right')]
    floor_relative = round(max(float(np.linalg.norm(np.array([a['centroid_offset_vhf_mm'][k] for k in ('x_right', 'y_anterior', 'z_superior')]) - common)) for a in pelvis_parts), 2)
    for rec in list(levels.values()) + [r for r in ribs.values() if 'centroid_offset_vhf_mm' in r]:
        o = np.array([rec['centroid_offset_vhf_mm'][k] for k in ('x_right', 'y_anterior', 'z_superior')]) - common
        rec['relative_to_pelvis'] = {'x_right': round(float(o[0]), 2), 'y_anterior': round(float(o[1]), 2), 'z_superior': round(float(o[2]), 2), 'norm': round(float(np.linalg.norm(o)), 2),
                                     'meaning': 'centroid offset minus the pelvis-anchor offset: one translational reference removed; still a mixture of posture, angular registration error and segmentation, not separated'}
    for rec in levels.values():
        spread = rec['model_spread']['max_component_range_mm'] or 0.0
        rec['discrepancy_threshold'] = {'pelvis_anchor_offset_mm': floor, 'model_range_mm': spread,
                                        'heuristic_threshold_mm': round(floor + spread, 2),
                                        'beyond_threshold': bool(rec['centroid_offset_vhf_mm']['norm'] > floor + spread),
                                        'relative_anchor_disagreement_mm': floor_relative,
                                        'relative_heuristic_threshold_mm': round(floor_relative + spread, 2),
                                        'relative_beyond_threshold': bool(rec['relative_to_pelvis']['norm'] > floor_relative + spread),
                                        'rule': 'heuristic threshold = pelvis-anchor offset norm + largest per-component range of the offset across the three models; relative = largest disagreement of the three pelvis anchors about the anchor offset + the same model range. '
                                                'A descriptive threshold for discrepancy, not an error bound, not a confidence level: it propagates no angular uncertainty, the models may share bias, and a per-axis range is not a Euclidean range. '
                                                'beyond_threshold marks a discrepancy to inspect; it does not attribute the excess to posture and it decides nothing.'}

    order = [i for i in full_ids]
    summary = {
        'vertebrae_measured': len(vert_ids), 'sacrum_measured': sac is not None, 'ribs_measured': sum(1 for r in ribs.values() if 'centroid_offset_vhf_mm' in r),
        'registration_floor_pelvis_mm': floor, 'registration_floor_pelvis_surface_p95_mm': floor_surface,
        'centroid_offset_norm_mm': {'min': min(l['centroid_offset_vhf_mm']['norm'] for l in levels.values()), 'median': round(float(np.median([l['centroid_offset_vhf_mm']['norm'] for l in levels.values()])), 2),
                                    'max': max(l['centroid_offset_vhf_mm']['norm'] for l in levels.values())},
        'levels_beyond_heuristic_threshold': [l['id'] for l in levels.values() if l['discrepancy_threshold']['beyond_threshold']],
        'common_shift_vhf_mm': {'x_right': round(float(common[0]), 2), 'y_anterior': round(float(common[1]), 2), 'z_superior': round(float(common[2]), 2), 'norm': floor,
                                'meaning': 'pelvis-anchor offset shared by every level; its cause (registration translation, angular registration error, anchor segmentation) is not identified by this calculation'},
        'relative_to_pelvis_norm_mm': {'min': min(l['relative_to_pelvis']['norm'] for l in levels.values()), 'median': round(float(np.median([l['relative_to_pelvis']['norm'] for l in levels.values()])), 2),
                                       'max': max(l['relative_to_pelvis']['norm'] for l in levels.values())},
        'relative_anchor_disagreement_mm': floor_relative,
        'levels_beyond_relative_heuristic_threshold': [l['id'] for l in levels.values() if l['discrepancy_threshold']['relative_beyond_threshold']],
        'own_rigid_fit_rotation_deg': {'median': round(float(np.median([l['own_rigid_fit']['angle_deg'] for l in levels.values()])), 2), 'max': max(l['own_rigid_fit']['angle_deg'] for l in levels.values())},
        'whole_spine_chain_rotation_deg': chain['whole_spine']['angle_deg'] if chain['whole_spine'] else None,
        'seconds': round(time.time() - t0, 1),
    }
    anchors_panel = {'x_right': anchors['pelvis']['centroid_offset_vhf_mm']['x_right'], 'y_anterior': anchors['pelvis']['centroid_offset_vhf_mm']['y_anterior'],
                     'z_superior': anchors['pelvis']['centroid_offset_vhf_mm']['z_superior'], 'angle': anchors['pelvis']['own_rigid_fit']['angle_deg']}
    draw_panel(levels, order, anchors_panel)

    out = {
        'id': 'trunk-posture-offset', 'date': time.strftime('%Y-%m-%d'), 'script': 'scripts/trunk-posture-offset.py', 'seed': SEED,
        'frame': 'VHF-image-2022 (+x subject right, +y anterior, +z superior, mm); offsets are Denver aligned CT minus NLM fresh CT',
        'what_it_measures': 'the remainder between the same consensus instance on the two same-donor CTs after each CT was placed by its own rigid pelvis fit: posture difference (fresh CT on the table versus frozen block) plus two registration errors plus two segmentation differences; not separated here and not anatomy',
        'what_it_does_not_do': 'it corrects nothing, attributes nothing to anatomy and does not name the levels; segmenter agreement does not correct registration or posture',
        'inputs': {n: {k: {'path': str(p.relative_to(ROOT)), 'sha256': sha256(p)} for k, p in v.inputs.items()} for n, v in vols.items()},
        'instance_tables': {n: {'path': str(CT[n]['instances_json'].relative_to(ROOT)), 'sha256': sha256(CT[n]['instances_json']), 'instance_count': tables[n]['instance_count']} for n in vols},
        'transforms': {n: {'path': str(CT[n]['transform'].relative_to(ROOT)), 'id': json.loads(CT[n]['transform'].read_text())['id'], 'applies_to': CT[n]['transform_applies_to'],
                           'sha256': sha256(CT[n]['transform'])} for n in vols},
        'method': {'instance_matching': 'same geometric id on both CTs (cranial to caudal order), checked against the nearest transformed Denver centroid',
                   'surface': 'marching cubes at 0.5 on each instance mask, vertices carried to VHF mm; up to 20,000 points per surface, seeded',
                   'rigid_fit': 'trimesh ICP without scale, anchored at the NLM instance centroid, 60 iterations; the residual after the fit mixes segmentation differences between the two CTs with voxel discretisation, surface sampling and the limits of the fit',
                   'chain_fit': 'Kabsch rigid fit of vertebra centroids NLM -> Denver, whole spine and per region', 'model_spread': 'centroid offset recomputed with each model\'s own instance map (vertebra-model-*.nii.gz)'},
        'summary': summary,
        'anchors': anchors,
        'chain_fit': chain,
        'levels': [levels[i] for i in order],
        'ribs': ribs,
        'neighbour_control': {'meaning': 'each NLM vertebra against the next caudal Denver instance; the method must show the inter-level spacing here', 'pairs': controls},
        'panel': str(PNG.relative_to(ROOT)),
    }
    OUT.write_text(json.dumps(out, indent=1, default=float) + '\n')
    print(json.dumps({'done': True, 'out': str(OUT.relative_to(ROOT)), **summary}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] not in ('--run',):
        sys.exit('usage: trunk-posture-offset.py [--run]')
    main()
