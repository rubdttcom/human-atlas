"""Photograph-to-CT check of the colour cryosections against Denver's aligned whole-body CT (plan B stage 0, last item).

Runs on rub-pc (photographs and CT there):
  python3 scripts/check-photo-ct-alignment.py --nlm /media/rub/Backups/VHF/Female-Images/fullbody \
      --ct /media/rub/Backups/VHF/denver/aligned-ct-nii/denver_aligned_ct_hu.nii.gz --ct-transform denver-aligned-ct-voxel-to-vhf.json \
      --transform nlm-cryosection-to-vhf.json --inventory fullbody-inventory.json --step 10 --workers 12 --out photo-ct-alignment.json

Why. Denver publishes aligned photographs only from the pelvis down; `transforms/nlm-cryosection-to-vhf.json` is measured
there (residual below 0.1 px) and only *extrapolated* above (the pelvis block's mapping, marked unverified). Denver also
publishes the fresh whole-body CT resampled into the same frame (`denver-aligned-ct-voxel-to-vhf.json`, a rigid pelvis
fit with p95 5.4 mm and 2.25 deg of residual rotation). The CT is therefore the only reference above the pelvis. This
script maps every sampled photograph into the canonical frame with the transform, samples the CT on the photograph's
grid and compares two automatic features: the body outline (photograph tissue against the blue block; CT HU > -400) and
the bone (photograph bright cortical bone; CT HU > 300, weaker in the photograph). It also scans the CT along z around
the predicted position to see where the outline agrees best.

Baseline. The same comparison on the Denver-covered photographs (measured mapping) gives the floor of the method: the
CT placement error (rigid fit, angular error growing with the distance from the pelvis) plus the fresh-CT versus frozen-
block outline difference (soft tissue moves; nothing here separates the two). Above the pelvis the excess over that
floor is the photograph alignment uncertainty; nothing is corrected here. Per photograph:
  mapping            measured (Denver per-slice table) | extrapolated (pelvis block) | denver-blank (nearest block)
  body               Dice, centroid offset (mm, CT minus photograph), rigid shift by phase correlation of the two signed
                     distance maps (mm, CT minus photograph), mean symmetric contour distance before and after removing
                     that shift (mm)
  bone               Dice and centroid offset, informative only (photograph bone detection is a colour threshold)
  z_scan             body Dice at z + dz, dz in [-15, 15] mm; best dz by parabola; a systematic dz above the pelvis is a
                     z offset of the extrapolation (Denver removed 1 mm at the knee gap; the 1492-1497 gap has 16
                     missing photographs whose physical thickness is unknown)
Output: one JSON with rows and per-band statistics (100 mm bands of canonical z, plus the Denver blocks as bands),
copied to generated/photo-ct-alignment-check.json. Nothing here is anatomy: two acquisitions of one body, compared by
their outlines under two automatic transforms.
"""
import argparse
import json
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage
from skimage.registration import phase_cross_correlation

W, H = 2048, 1216
SUB = 4                          # photograph sampling step (px); 4 px = 1.33 mm
ROW_MAX = 1000                   # below this photograph row lie the colour chart and the slice card (never body)
DZ = np.arange(-15.0, 15.01, 1.5)  # z scan (mm)
ARGS = None
CT = None
CT_INV = None                    # mm -> CT voxel


def nlm_name(n):
    return f'avf{1001 + n // 3:04d}{"abc"[n % 3]}.raw.Z'


def load_photo(n):
    p = Path(ARGS.nlm) / nlm_name(n)
    if not p.exists():
        return None
    raw = subprocess.run(['gzip', '-dc', str(p)], capture_output=True, check=True, timeout=600).stdout
    if len(raw) != W * H * 3:
        return None
    rgb = np.frombuffer(raw, np.uint8).reshape(3, H, W).transpose(1, 2, 0)
    sub = rgb[SUB // 2::SUB, SUB // 2::SUB].astype(np.float32)      # pixel centres of the SUB x SUB blocks
    if sub.std() < 1.0:
        return None
    return sub


def photo_masks(sub):
    """Body: tissue (reddish/yellow/white) against the blue block; bone: bright, low saturation, inside the body."""
    R, G, B = sub[..., 0], sub[..., 1], sub[..., 2]
    rows = np.arange(sub.shape[0]) * SUB + SUB // 2
    body = (R > B + 25) & (sub.max(axis=2) > 60)
    body[rows >= ROW_MAX] = False
    body = ndimage.binary_closing(body, iterations=2)
    body = ndimage.binary_fill_holes(body)
    lab, n = ndimage.label(body)
    if n:
        sizes = np.bincount(lab.ravel())[1:]
        keep = np.where(sizes >= 200)[0] + 1            # 200 blocks = 3.6 cm2
        body = np.isin(lab, keep)
    bone = body & (R > 165) & (G > 150) & (B > 120) & ((R - B) < 70)
    bone = ndimage.binary_opening(bone, iterations=1)
    return body, bone


def mapping_for(n, transform):
    """Photograph n -> (k, tc, tr, s, theta, kind, region)."""
    per = transform['_per_slice_by_n']
    if n in per:
        p = per[n]
        return p['k'], p['tc'], p['tr'], p['s'], np.radians(p['theta_deg']), 'measured', p['region']
    # choose the region by k = offset - n, using the pelvis block for anything above it
    regions = transform['regions']
    pelvis = max(regions, key=lambda g: g['k_last'])
    for g in regions:
        k = g['offset'] - n
        if g['k_first'] <= k <= g['k_last']:
            m = g['similarity_median']
            return k, m['tc_nlm_px'], m['tr_nlm_px'], m['scale_nlm_px_per_denver_px'], np.radians(m['rotation_deg']), 'denver-blank', g['region']
    k = pelvis['offset'] - n
    m = pelvis['similarity_median']
    kind = 'extrapolated' if k > pelvis['k_last'] else 'denver-blank'
    return k, m['tc_nlm_px'], m['tr_nlm_px'], m['scale_nlm_px_per_denver_px'], np.radians(m['rotation_deg']), kind, pelvis['region']


def photo_grid_mm(k, tc, tr, s, th):
    """Canonical mm (x, y, z) of every sampled photograph pixel."""
    rr, cc = np.mgrid[0:H // SUB, 0:W // SUB]
    c = cc * SUB + SUB // 2 + 0.0; r = rr * SUB + SUB // 2 + 0.0
    dc, dr = c - tc, r - tr
    u = (np.cos(th) * dc + np.sin(th) * dr) / s
    v = (-np.sin(th) * dc + np.cos(th) * dr) / s
    i, j = -u, v
    x = 0.666 * i + 316.35; y = 0.666 * j + 311.022; z = np.full_like(x, 0.333 * (k - 1))
    return x, y, z


def sample_ct(x, y, z):
    pts = np.stack([x.ravel(), y.ravel(), z.ravel(), np.ones(x.size)])
    vox = CT_INV @ pts
    hu = ndimage.map_coordinates(CT, vox[:3], order=1, mode='constant', cval=-1000.0)
    return hu.reshape(x.shape)


def mask_stats(a, b, mm_per_px):
    """a = photograph mask, b = CT mask. Dice, centroid offset, phase-correlation shift, contour distances."""
    out = {'dice': round(float(2 * (a & b).sum() / max(1, a.sum() + b.sum())), 4), 'photo_px': int(a.sum()), 'ct_px': int(b.sum())}
    if a.sum() < 50 or b.sum() < 50:
        out['comparable'] = False; return out
    ca = np.array(ndimage.center_of_mass(a)); cb = np.array(ndimage.center_of_mass(b))
    out['centroid_offset_mm'] = [round(float((cb[1] - ca[1]) * mm_per_px), 2), round(float((cb[0] - ca[0]) * mm_per_px), 2)]   # (x: col, y: row), CT minus photo
    da = ndimage.distance_transform_edt(~a) - ndimage.distance_transform_edt(a)
    db = ndimage.distance_transform_edt(~b) - ndimage.distance_transform_edt(b)
    # skimage returns the shift that registers the moving image (CT) onto the reference (photograph): the CT lies at
    # minus that shift relative to the photograph
    shift, _, _ = phase_cross_correlation(np.clip(da, -20, 20), np.clip(db, -20, 20), upsample_factor=10)
    out['shift_mm'] = [round(float(-shift[1] * mm_per_px), 2), round(float(-shift[0] * mm_per_px), 2)]     # CT minus photograph (x: col, y: row), same convention as centroid_offset_mm
    out['shift_norm_mm'] = round(float(np.hypot(*shift) * mm_per_px), 2)
    # mean symmetric contour distance, as placed and after removing the shift
    def contour(m):
        return m & ~ndimage.binary_erosion(m)
    def msd(m1, m2):
        c1, c2 = contour(m1), contour(m2)
        d12 = ndimage.distance_transform_edt(~c2)[c1]; d21 = ndimage.distance_transform_edt(~c1)[c2]
        return float(np.concatenate([d12, d21]).mean() * mm_per_px)
    out['contour_msd_mm'] = round(msd(a, b), 2)
    b_shift = ndimage.shift(b.astype(np.float32), shift, order=0) > 0.5
    out['contour_msd_after_shift_mm'] = round(msd(a, b_shift), 2)
    out['comparable'] = True
    return out


def one(args):
    n, transform = args
    sub = load_photo(n)
    row = {'n': n, 'nlm': nlm_name(n)}
    if sub is None:
        row['status'] = 'photo-absent-or-placeholder'; return row
    k, tc, tr, s, th, kind, region = mapping_for(n, transform)
    row.update({'k': int(k), 'z_mm': round(0.333 * (k - 1), 3), 'mapping': kind, 'region': region})
    body, bone = photo_masks(sub)
    x, y, z = photo_grid_mm(k, tc, tr, s, th)
    mm_per_px = SUB / s * 0.666           # one sampled photograph pixel in mm (s photo px per Denver px of 0.666 mm)
    hu = sample_ct(x, y, z)
    ct_body = ndimage.binary_fill_holes(hu > -400)
    lab, nn = ndimage.label(ct_body)
    if nn:
        sizes = np.bincount(lab.ravel())[1:]; ct_body = np.isin(lab, np.where(sizes >= 200)[0] + 1)
    ct_bone = hu > 300
    row['body'] = mask_stats(body, ct_body, mm_per_px)
    row['bone'] = mask_stats(bone, ct_bone, mm_per_px)
    # z scan on the body Dice
    dices = []
    for dz in DZ:
        hu_z = sample_ct(x, y, z + dz)
        m = ndimage.binary_fill_holes(hu_z > -400)
        dices.append(float(2 * (body & m).sum() / max(1, body.sum() + m.sum())))
    dices = np.array(dices)
    ib = int(dices.argmax())
    best = float(DZ[ib])
    if 0 < ib < len(DZ) - 1:
        y0, y1, y2 = dices[ib - 1], dices[ib], dices[ib + 1]
        den = y0 - 2 * y1 + y2
        if den < 0:
            best = float(DZ[ib] + 0.5 * (y0 - y2) / den * (DZ[1] - DZ[0]))
    row['z_scan'] = {'dz_mm': [float(d) for d in DZ], 'body_dice': [round(d, 4) for d in dices], 'best_dz_mm': round(best, 2),
                     'at_edge': ib in (0, len(DZ) - 1), 'gain_over_dz0': round(float(dices.max() - dices[len(DZ) // 2]), 4)}
    row['photo_body_bbox_rows'] = [int(v) for v in np.where(body.any(axis=1))[0][[0, -1]] * SUB] if body.any() else None
    row['status'] = 'compared'
    if ARGS.debug_png:
        from PIL import Image
        img = sub.astype(np.uint8).copy()
        def edge(m):
            return m & ~ndimage.binary_erosion(m)
        img[edge(body)] = [0, 255, 0]; img[edge(ct_body)] = [255, 0, 255]; img[edge(ct_bone)] = [0, 255, 255]
        Image.fromarray(img).save(Path(ARGS.debug_png) / f'photo-ct-n{n:04d}-{nlm_name(n).replace(".raw.Z", "")}-{kind}.png')
    return row


def band_stats(rows, key_fn, label):
    bands = {}
    for r in rows:
        if r['status'] != 'compared' or not r['body'].get('comparable'):
            continue
        bands.setdefault(key_fn(r), []).append(r)
    out = []
    for b, rs in sorted(bands.items(), key=lambda kv: str(kv[0])):
        sh = np.array([r['body']['shift_norm_mm'] for r in rs]); dice = np.array([r['body']['dice'] for r in rs])
        msd = np.array([r['body']['contour_msd_mm'] for r in rs]); msd2 = np.array([r['body']['contour_msd_after_shift_mm'] for r in rs])
        dz = np.array([r['z_scan']['best_dz_mm'] for r in rs if not r['z_scan']['at_edge']])
        sx = np.array([r['body']['shift_mm'][0] for r in rs]); sy = np.array([r['body']['shift_mm'][1] for r in rs])
        out.append({'band_kind': label, 'band': b, 'photographs': len(rs), 'mappings': sorted({r['mapping'] for r in rs}),
                    'body_shift_mm': {'median_norm': round(float(np.median(sh)), 2), 'p95_norm': round(float(np.percentile(sh, 95)), 2),
                                      'median_x': round(float(np.median(sx)), 2), 'median_y': round(float(np.median(sy)), 2)},
                    'body_dice': {'median': round(float(np.median(dice)), 4), 'min': round(float(dice.min()), 4)},
                    'contour_msd_mm': {'median_as_placed': round(float(np.median(msd)), 2), 'median_after_shift': round(float(np.median(msd2)), 2), 'p95_as_placed': round(float(np.percentile(msd, 95)), 2)},
                    'z_scan_best_dz_mm': {'median': round(float(np.median(dz)), 2), 'p95_abs': round(float(np.percentile(np.abs(dz), 95)), 2), 'n': int(len(dz)),
                                          'at_edge': int(sum(1 for r in rs if r['z_scan']['at_edge']))} if len(dz) else None,
                    'bone_dice_median': round(float(np.median([r['bone']['dice'] for r in rs])), 4),
                    'bone_centroid_offset_mm_median': [round(float(np.median([r['bone']['centroid_offset_mm'][i] for r in rs if r['bone'].get('comparable')])), 2) for i in (0, 1)]
                    if any(r['bone'].get('comparable') for r in rs) else None})
    return out


def main():
    global ARGS, CT, CT_INV
    ap = argparse.ArgumentParser()
    ap.add_argument('--nlm', required=True); ap.add_argument('--ct', required=True); ap.add_argument('--ct-transform', required=True)
    ap.add_argument('--transform', required=True); ap.add_argument('--inventory', required=True)
    ap.add_argument('--step', type=int, default=10); ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--ns', default=None); ap.add_argument('--rows-from', default=None, help='re-summarise the rows of a previous report without recomputing'); ap.add_argument('--out', default='photo-ct-alignment.json'); ap.add_argument('--debug-png', default=None)
    ARGS = ap.parse_args()
    t0 = time.time()
    if ARGS.debug_png:
        Path(ARGS.debug_png).mkdir(parents=True, exist_ok=True)
    img = nib.load(ARGS.ct)
    CT = np.asanyarray(img.dataobj).astype(np.float32)
    M = np.array(json.loads(Path(ARGS.ct_transform).read_text())['matrix_row_major']).reshape(4, 4)
    CT_INV = np.linalg.inv(M)
    transform = json.loads(Path(ARGS.transform).read_text())
    transform['_per_slice_by_n'] = {p['n']: p for p in transform['per_slice']}
    inventory = json.loads(Path(ARGS.inventory).read_text())
    present = {r['file'] for r in inventory['files']} - set(inventory['summary']['constant_or_blank'])
    if ARGS.ns:
        ns = sorted({int(x) for x in ARGS.ns.split(',')})
    else:
        ns = [n for n in range(0, 5190, ARGS.step) if nlm_name(n) in present]
    if ARGS.rows_from:
        rows = json.loads(Path(ARGS.rows_from).read_text())['rows']; ns = [r['n'] for r in rows]
    else:
        with ProcessPoolExecutor(ARGS.workers) as ex:
            rows = list(ex.map(one, [(n, transform) for n in ns], chunksize=4))
    compared = [r for r in rows if r['status'] == 'compared']
    by_z = band_stats(rows, lambda r: int(r['z_mm'] // 100) * 100, 'z_band_mm_from')
    by_map = band_stats(rows, lambda r: r['mapping'], 'mapping')
    by_region = band_stats(rows, lambda r: r['region'] if r['mapping'] == 'measured' else 'above-denver' if r['mapping'] == 'extrapolated' else 'denver-blank', 'block')
    baseline = [b for b in by_map if b['band'] == 'measured']
    extrap = [b for b in by_map if b['band'] == 'extrapolated']
    # linear trend of the body shift with canonical z (a rotation between the two frames appears as a slope: shift = z * angle)
    trend = {}
    for kind in ('measured', 'extrapolated', 'all'):
        rs = [r for r in compared if r['body'].get('comparable') and (kind == 'all' or r['mapping'] == kind)]
        if len(rs) >= 10:
            zz = np.array([r['z_mm'] for r in rs]); sy = np.array([r['body']['shift_mm'][1] for r in rs]); sx = np.array([r['body']['shift_mm'][0] for r in rs])
            by, ay = np.polyfit(zz, sy, 1); bx, ax = np.polyfit(zz, sx, 1)
            trend[kind] = {'photographs': len(rs), 'y_shift_mm_per_mm_z': round(float(by), 5), 'y_equivalent_rotation_about_x_deg': round(float(np.degrees(np.arctan(by))), 3),
                           'y_intercept_mm': round(float(ay), 2), 'y_zero_crossing_z_mm': round(float(-ay / by), 1) if by else None,
                           'x_shift_mm_per_mm_z': round(float(bx), 5), 'x_equivalent_rotation_about_y_deg': round(float(np.degrees(np.arctan(bx))), 3),
                           'y_residual_rms_mm': round(float(np.sqrt(np.mean((sy - (ay + by * zz)) ** 2))), 2),
                           'note': 'a linear trend of the in-plane shift with z is what a rigid rotation between the two frames looks like; it does not say which frame (CT placement, photograph frame, or the body between acquisitions) carries it'}
    summary = {
        'shift_trend_with_z': trend,
        'photographs_sampled': len(ns), 'compared': len(compared), 'step': ARGS.step,
        'statuses': {s: sum(1 for r in rows if r['status'] == s) for s in sorted({r['status'] for r in rows})},
        'baseline_measured_mapping': baseline[0] if baseline else None,
        'extrapolated_mapping': extrap[0] if extrap else None,
        'by_block': by_region, 'by_z_band_100mm': by_z,
        'method': {'photo_body': 'R > B + 25 and max(R,G,B) > 60, rows below %d, closing, fill holes, components >= 200 blocks of %d x %d px' % (ROW_MAX, SUB, SUB),
                   'ct_body': 'HU > -400 sampled on the photograph grid through the transform and the CT placement, fill holes, components >= 200',
                   'photo_bone': 'inside body, R > 165, G > 150, B > 120, R - B < 70 (a colour threshold; informative only)', 'ct_bone': 'HU > 300',
                   'shift': 'phase correlation of the signed distance transforms (clipped at 20 blocks), 10 x upsampled', 'z_scan': 'body Dice at z + dz, dz -15..15 mm step 1.5, parabolic peak; at_edge counts scans whose best lies on the scan limit (inconclusive)'},
        'limits': ['the floor of this comparison is the CT placement (rigid pelvis fit, p95 5.4 mm, angular error grows with distance from the pelvis) plus the fresh-CT versus frozen-block outline difference; nothing here separates them',
                   'above the pelvis the mapping is the pelvis block extrapolated; the excess over the measured-mapping baseline is the alignment uncertainty of the photographs there, not a correction',
                   'photograph bone is a colour threshold; the CT arms lie partly outside the CT field of view (423 slices on the edge)',
                   'nothing here is anatomy'],
        'seconds': round(time.time() - t0, 1),
    }
    Path(ARGS.out).write_text(json.dumps({'summary': summary, 'rows': rows}, indent=1))
    print(json.dumps({'done': True, 'out': ARGS.out, 'compared': len(compared), 'seconds': summary['seconds'],
                      'baseline': summary['baseline_measured_mapping'], 'extrapolated': summary['extrapolated_mapping']}))


if __name__ == '__main__':
    main()
