"""Alignment check of the NLM colour cryosections against Denver's aligned grayscale slices (plan B stage 0).

Runs on the box that holds both data sets (rub-pc):
  python3 scripts/check-cryosection-alignment.py --nlm /media/rub/Backups/VHF/Female-Images/fullbody \
      --denver "/media/rub/Backups/VHF/denver/aligned-cryo/Aligned Cryosection-DICOM" \
      --inventory fullbody-inventory.json --step 1 --workers 12 --out cryosection-alignment.json [--debug-png DIR]

What is compared. Denver (Andreassen et al. 2022) publishes 3,533 aligned 8-bit grayscale slices, 666 x 434 pixels at
0.666 mm, 0.333 mm apart, pelvis to feet, in the frame of `VHF_Full.mat` (ijkToLps: x = 0.666 i + 316.35,
y = 0.666 j + 311.022, z = 0.333 (k - 1); slice k of the DICOM is byte-identical to `scan_data[k]`, checked on
13 September 2026). NLM publishes the 5,186 colour photographs, 2,048 x 1,216 at a declared 0.33 mm, three per
millimetre (`avfNNNN{a,b,c}`, index n = 3 (NNNN - 1001) + {a: 0, b: 1, c: 2}). Denver derived its grayscale slices
from these photographs and registered them (manual and automatic, no accuracy reported). This script measures that
relation slice by slice; it decides nothing anatomical.

Per Denver slice k (every --step, plus both ends):
  1. in-plane initialisation on the predicted NLM slice n = offset - k: the Denver slice, mirrored left-right (the only
     orientation that matches; the eight orientations are probed on four slices and recorded), is rotated over a
     coarse grid and located in the 2 x 2-averaged NLM luminance by normalised cross-correlation (NCC); then a
     similarity Denver (i, j) -> NLM full-resolution (c, r) = s R(theta) (-i, j) + (tc, tr) is refined by Powell.
  2. slice identity: every NLM sub-slice in a window of +-W around the predicted index is resampled on the Denver grid
     with that similarity and compared with the Denver slice by NCC over the whole frame and, when the handwritten
     slice label (a bright card with dark digits in the lower part of the frame) is found in the Denver slice, over
     the label region. Neighbouring photographs 1/3 mm apart differ little in tissue but the label digits change on
     every photograph, so the label NCC identifies the photograph; the whole-frame NCC is kept as the fallback and the
     two are compared. The chosen n per k is fitted by a line over all slices; a slope of -1 means three Denver slices
     per NLM millimetre; steps in the intercept are regions Denver shifted in z.
  3. in-plane similarity re-refined on the chosen photograph; local residual after the fit in a 3 x 3 grid of blocks by
     phase correlation (upsampled 20 x), in NLM pixels: a block shift above zero means the similarity does not explain
     the whole slice.
  4. grayscale weights: least-squares Denver gray = w . (R, G, B) + b on the matched pixels, for information.
  5. gaps: Denver slices around each absent or black NLM slice, with blank and identical-to-neighbour flags, and (dense
     run) NLM photographs inside Denver's range that no Denver slice chose, and Denver slices that share one photograph.

Criterion (plan B stage 0): mean in-plane residual below one NLM pixel (1/3 mm) per slice, pelvis to feet, image to
image. Above the pelvis (NLM 1001 to about 1552) Denver has no aligned photographs: nothing here applies there.

Output: one JSON (per-slice rows, identity fit, similarity statistics per region, gaps, grayscale weights, criterion),
copied to generated/cryosection-alignment-check.json; scripts/build-cryosection-transform.py turns it into
transforms/nlm-cryosection-to-vhf.json. Nothing here is anatomy: it relates two publications of the same block.
"""
import argparse
import hashlib
import json
import re
import subprocess
import time
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pydicom
from scipy import ndimage, optimize
from skimage.feature import match_template
from skimage.registration import phase_cross_correlation

W, H = 2048, 1216
DEN_W, DEN_H, DEN_N = 666, 434, 3533
NLM_N = 5190
DEFAULT_OFFSET = 5192        # Denver k = 0 <-> NLM index 5192 (beyond avf2730c): measured on 13 September 2026 (step-25 pass)
LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)
ORIENTS = {
    'identity': lambda a: a, 'rot90': lambda a: np.rot90(a, 1), 'rot180': lambda a: np.rot90(a, 2),
    'rot270': lambda a: np.rot90(a, 3), 'flip_x': lambda a: a[:, ::-1], 'flip_y': lambda a: a[::-1],
    'flip_x_rot90': lambda a: np.rot90(a[:, ::-1], 1), 'flip_y_rot90': lambda a: np.rot90(a[::-1], 1),
}
ROTATION_GRID_DEG = np.arange(-3.0, 3.01, 0.5)
NAME = re.compile(r'^avf(\d{4})([abc])\.raw\.Z$')
ARGS = None
_CACHE = OrderedDict()       # per worker process: n -> (rgb, luma)
_CACHE_MAX = 40


def nlm_name(n):
    return f'avf{1001 + n // 3:04d}{"abc"[n % 3]}.raw.Z'


def nlm_index(name):
    m = NAME.match(name)
    return 3 * (int(m.group(1)) - 1001) + 'abc'.index(m.group(2))


def load_nlm(n):
    """Full-resolution RGB (H, W, 3) float32 and luminance, or (None, None) when absent, truncated or black."""
    if n in _CACHE:
        _CACHE.move_to_end(n); return _CACHE[n]
    p = Path(ARGS.nlm) / nlm_name(n)
    out = (None, None)
    if p.exists():
        raw = subprocess.run(['gzip', '-dc', str(p)], capture_output=True, check=True, timeout=600).stdout
        if len(raw) == W * H * 3:
            rgb = np.frombuffer(raw, np.uint8).reshape(3, H, W).transpose(1, 2, 0).astype(np.float32)
            luma = rgb @ LUMA
            out = (rgb, luma) if luma.std() >= 1.0 else ('placeholder', None)
    _CACHE[n] = out
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return out


def half(img):
    return img.reshape(H // 2, 2, W // 2, 2).mean(axis=(1, 3))


def load_denver(k):
    return pydicom.dcmread(Path(ARGS.denver) / f'VHF_Full_VHF_Scan{k:04d}.dcm').pixel_array


def ncc(a, b):
    a = a - a.mean(); b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def integer_match(img_half, template):
    pad = (max(0, template.shape[0] - img_half.shape[0] + 1), max(0, template.shape[1] - img_half.shape[1] + 1))
    im = np.pad(img_half, ((0, pad[0]), (0, pad[1]))) if any(pad) else img_half
    r = match_template(im, template)
    ij = np.unravel_index(np.argmax(r), r.shape)
    return float(r[ij]), int(ij[0]), int(ij[1])


def similarity_coords(params, i, j):
    """Denver pixel (i col, j row) -> NLM full-res (c col, r row); the mirror is the -i."""
    tc, tr, s, th = params
    u, v = -i, j
    c = s * (np.cos(th) * u - np.sin(th) * v) + tc
    r = s * (np.sin(th) * u + np.cos(th) * v) + tr
    return c, r


_JJ, _II = np.mgrid[0:DEN_H, 0:DEN_W]
_II_F = _II.astype(np.float32); _JJ_F = _JJ.astype(np.float32)


def resample_full(luma_full, params, step=1):
    c, r = similarity_coords(params, _II_F[::step, ::step], _JJ_F[::step, ::step])
    return ndimage.map_coordinates(luma_full, [r, c], order=1, mode='nearest')


def refine(luma_full, den, init):
    d = den[::2, ::2].astype(np.float32)

    def cost(p):
        return -ncc(resample_full(luma_full, p, step=2), d)
    res = optimize.minimize(cost, np.array(init, float), method='Powell',
                            options={'xtol': 1e-3, 'ftol': 1e-6, 'maxfev': 4000})
    return res.x, -float(res.fun)


def initial_similarity(luma_full, den):
    """Coarse rotation grid + integer match at half resolution -> (init params, table)."""
    hl = half(luma_full)
    t0 = den[:, ::-1].astype(np.float32)
    table = []
    for deg in ROTATION_GRID_DEG:
        t = ndimage.rotate(t0, deg, reshape=False, order=1, mode='nearest') if abs(deg) > 1e-9 else t0
        v, r0, c0 = integer_match(hl, t)
        table.append((v, float(deg), r0, c0))
    v, deg, r0, c0 = max(table)
    # the rotated template keeps its centre: place the centre, then express the corner (i = 0, j = 0); the sign of the
    # angle in the similarity is fixed by evaluating both candidates (no dependence on the rotate() convention)
    cen_c, cen_r = 2 * (c0 + (DEN_W - 1) / 2) + 0.5, 2 * (r0 + (DEN_H - 1) / 2) + 0.5
    ui, vj = (DEN_W - 1) / 2, (DEN_H - 1) / 2          # centre in (u, v) = (-i, j) coordinates is (-ui, vj)
    d2 = den[::2, ::2].astype(np.float32)
    best = None
    for th in (np.radians(deg), -np.radians(deg)):
        tc = cen_c - 2 * (np.cos(th) * (-ui) - np.sin(th) * vj)
        tr = cen_r - 2 * (np.sin(th) * (-ui) + np.cos(th) * vj)
        p = [float(tc), float(tr), 2.0, float(th)]
        q = ncc(resample_full(luma_full, p, step=2), d2)
        if best is None or q > best[0]:
            best = (q, p)
    return best[1], {'ncc_half': round(v, 4), 'rotation_deg_grid': deg, 'rotation_deg_init': round(float(np.degrees(best[1][3])), 3),
                     'ncc_init': round(best[0], 4), 'row0_half': r0, 'col0_half': c0, 'grid': [[round(a, 4), b] for a, b, _, _ in table]}


def find_label(den):
    """Bright card with dark digits in the lower part of the Denver frame -> (r0, r1, c0, c1) or None."""
    low = den[DEN_H // 2:]
    mask = low > 170
    lab, n = ndimage.label(mask)
    best = None
    for idx, sl in enumerate(ndimage.find_objects(lab), start=1):
        if sl is None:
            continue
        h_, w_ = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if not (14 <= h_ <= 70 and 35 <= w_ <= 180):
            continue
        comp = lab[sl] == idx
        fill = comp.mean()
        if fill < 0.45:
            continue
        inner = low[sl]
        dark = float((inner < 110).mean())          # digits inside the card
        if dark < 0.02:
            continue
        area = int(comp.sum())
        if best is None or area > best[0]:
            best = (area, sl, fill, dark)
    if best is None:
        return None
    _, sl, fill, dark = best
    r0 = sl[0].start + DEN_H // 2 - 4; r1 = sl[0].stop + DEN_H // 2 + 4
    c0 = sl[1].start - 6; c1 = sl[1].stop + 6
    return {'rows': [max(0, r0), min(DEN_H, r1)], 'cols': [max(0, c0), min(DEN_W, c1)], 'fill': round(float(fill), 3), 'dark_fraction': round(dark, 3)}


def local_residual(den, res_img, s):
    rows = np.linspace(0, DEN_H, 4).astype(int); cols = np.linspace(0, DEN_W, 4).astype(int)
    out = []
    for a in range(3):
        for b in range(3):
            d = den[rows[a]:rows[a + 1], cols[b]:cols[b + 1]].astype(np.float32)
            m = res_img[rows[a]:rows[a + 1], cols[b]:cols[b + 1]]
            if not (float(d.std()) > 8.0 and float(m.std()) > 8.0):
                out.append({'block': [a, b], 'textured': False}); continue
            shift, _, _ = phase_cross_correlation(d, m, upsample_factor=20, normalization='phase')
            out.append({'block': [a, b], 'textured': True, 'shift_denver_px': [round(float(x), 3) for x in shift],
                        'shift_nlm_px': round(float(np.hypot(*shift) * s), 3), 'ncc': round(ncc(d, m), 4)})
    return out


def one(args):
    k, seed = args if isinstance(args, tuple) else (args, None)
    den = load_denver(k)
    row = {'k': k, 'z_denver_mm': round(0.333 * (k - 1), 3), 'denver_sha256': hashlib.sha256(den.tobytes()).hexdigest(),
           'denver_mean': round(float(den.mean()), 3)}
    if den.max() == 0:
        row['status'] = 'denver-blank'; return row
    n_pred = (seed['offset'] if seed else ARGS.offset) - k
    row['pass'] = 2 if seed else 1
    if seed:
        row['seed_from_k'] = seed['from_k']
    row['n_predicted'] = n_pred; row['nlm_predicted'] = nlm_name(n_pred) if 0 <= n_pred < NLM_N else None
    window = list(range(n_pred - ARGS.window, n_pred + ARGS.window + 1))
    loaded = {n: load_nlm(n) for n in window if 0 <= n < NLM_N}
    present = [n for n, (rgb, luma) in loaded.items() if luma is not None]
    if not present:
        row['status'] = 'no-nlm-slice'; return row
    # 1. in-plane initialisation on the predicted slice (nearest present)
    n_init = min(present, key=lambda n: abs(n - n_pred))
    if seed:
        init, init_table = list(seed['params']), {'seeded': True}
    else:
        init, init_table = initial_similarity(loaded[n_init][1], den)
    params0, ncc0 = refine(loaded[n_init][1], den, init)
    row['initialisation'] = {'n': n_init, **init_table, 'ncc_after_refine': round(ncc0, 4)}
    # 2. slice identity: resample every candidate with params0
    label = find_label(den)
    row['label_region'] = label
    dfull = den.astype(np.float32)
    cands = []
    for n in window:
        if n < 0 or n >= NLM_N:
            continue
        rgb, luma = loaded[n]
        if luma is None:
            cands.append({'n': n, 'file': nlm_name(n), 'status': 'placeholder' if rgb == 'placeholder' else 'absent'}); continue
        img = resample_full(luma, params0)
        c = {'n': n, 'file': nlm_name(n), 'status': 'present', 'ncc_frame': round(ncc(img, dfull), 4)}
        if label:
            r0, r1 = label['rows']; c0, c1 = label['cols']
            c['ncc_label'] = round(ncc(img[r0:r1, c0:c1], dfull[r0:r1, c0:c1]), 4)
        cands.append(c)
    row['candidates'] = cands
    present_c = [c for c in cands if c['status'] == 'present']
    best_frame = max(present_c, key=lambda c: c['ncc_frame'])
    frame_others = sorted([c['ncc_frame'] for c in present_c if c['n'] != best_frame['n']], reverse=True)
    row['frame_choice'] = {'n': best_frame['n'], 'ncc': best_frame['ncc_frame'], 'margin': round(best_frame['ncc_frame'] - frame_others[0], 4) if frame_others else None}
    if label:
        best_label = max(present_c, key=lambda c: c['ncc_label'])
        label_others = sorted([c['ncc_label'] for c in present_c if c['n'] != best_label['n']], reverse=True)
        row['label_choice'] = {'n': best_label['n'], 'ncc': best_label['ncc_label'], 'margin': round(best_label['ncc_label'] - label_others[0], 4) if label_others else None}
        chosen, row['identity_by'] = best_label, 'label'
        row['label_and_frame_agree'] = best_label['n'] == best_frame['n']
    else:
        chosen, row['identity_by'] = best_frame, 'frame'
        row['label_choice'] = None; row['label_and_frame_agree'] = None
    row['n_best'] = chosen['n']; row['nlm_best'] = chosen['file']
    row['offset_best'] = chosen['n'] + k
    row['best_at_window_edge'] = chosen['n'] in (window[0], window[-1])
    by_n = {c['n']: c['ncc_frame'] for c in present_c}
    nb = row['frame_choice']['n']
    if nb - 1 in by_n and nb + 1 in by_n:
        y0, y1, y2 = by_n[nb - 1], by_n[nb], by_n[nb + 1]
        den_ = y0 - 2 * y1 + y2
        row['n_peak_parabolic_frame'] = round(nb + (0.5 * (y0 - y2) / den_ if den_ < 0 else 0.0), 3)
    else:
        row['n_peak_parabolic_frame'] = None
    # 3. final similarity on the chosen photograph
    rgb, luma = loaded[chosen['n']]
    params, ncc_full = refine(luma, den, params0)
    tc, tr, s, th = [float(x) for x in params]
    row['similarity'] = {'tc_nlm_px': round(tc, 3), 'tr_nlm_px': round(tr, 3), 'scale_nlm_px_per_denver_px': round(s, 5),
                         'rotation_deg': round(np.degrees(th), 4), 'ncc_full': round(ncc_full, 4)}
    res_img = resample_full(luma, params)
    blocks = local_residual(den, res_img, s)
    shifts = [b['shift_nlm_px'] for b in blocks if b.get('textured')]
    row['local_residual'] = {'blocks': blocks, 'mean_nlm_px': round(float(np.mean(shifts)), 3) if shifts else None,
                             'max_nlm_px': round(float(np.max(shifts)), 3) if shifts else None, 'textured_blocks': len(shifts)}
    # 4. grayscale weights
    c, r = similarity_coords(params, _II_F[::4, ::4].ravel(), _JJ_F[::4, ::4].ravel())
    X = np.stack([ndimage.map_coordinates(rgb[..., ch], [r, c], order=1, mode='nearest') for ch in range(3)], axis=1)
    y = den[::4, ::4].ravel().astype(np.float32)
    keep = y > 0
    A = np.column_stack([X[keep], np.ones(int(keep.sum()), np.float32)])
    w, *_ = np.linalg.lstsq(A, y[keep], rcond=None)
    row['gray_fit'] = {'weights_rgb': [round(float(x), 4) for x in w[:3]], 'bias': round(float(w[3]), 3),
                       'rms': round(float(np.sqrt(np.mean((A @ w - y[keep]) ** 2))), 3), 'pixels': int(keep.sum())}
    row['status'] = 'matched'
    if ARGS.debug_png:
        from PIL import Image
        diff = np.abs(res_img - dfull)
        panel = np.concatenate([dfull, res_img, diff * 2], axis=1)
        Image.fromarray(np.clip(panel, 0, 255).astype(np.uint8)).save(Path(ARGS.debug_png) / f'align-k{k:04d}-{chosen["file"].replace(".raw.Z", "")}.png')
    return row


def orient_probe(ks):
    table = {}
    for k in ks:
        den = load_denver(k)
        _, luma = load_nlm(ARGS.offset - k)
        if luma is None or den.max() == 0:
            continue
        hl = half(luma)
        table[k] = {o: round(integer_match(hl, ORIENTS[o](den.astype(np.float32)))[0], 4) for o in ORIENTS}
    votes = {}
    for t in table.values():
        w = max(t, key=t.get); votes[w] = votes.get(w, 0) + 1
    return max(votes, key=votes.get), table


def gap_report(inventory, rows):
    files = {r['file'] for r in inventory['files']}
    absent = {n for n in range(NLM_N) if nlm_name(n) not in files}
    placeholder = {nlm_index(name) for name in inventory['summary']['constant_or_blank']}
    chosen = {r['k']: r['n_best'] for r in rows if r['status'] == 'matched'}
    out = []
    for n in sorted(absent | placeholder):
        entry = {'n': n, 'nlm': nlm_name(n), 'nlm_status': 'absent' if n in absent else 'placeholder', 'k_predicted': ARGS.offset - n}
        k0 = ARGS.offset - n
        if not 0 <= k0 < DEN_N:
            entry['denver'] = 'outside Denver range'; out.append(entry); continue
        near = []
        for k in range(max(0, k0 - 6), min(DEN_N, k0 + 7)):
            d = load_denver(k)
            e = {'k': k, 'blank': bool(d.max() == 0), 'chosen_n': chosen.get(k), 'chosen_nlm': nlm_name(chosen[k]) if k in chosen else None}
            if k + 1 < DEN_N:
                nb = load_denver(k + 1)
                e['identical_to_next'] = bool(np.array_equal(d, nb))
                e['ncc_to_next'] = round(ncc(d.astype(np.float32), nb.astype(np.float32)), 4) if d.max() > 0 and nb.max() > 0 else None
            near.append(e)
        entry['denver_slices_near'] = near
        out.append(entry)
    return out


def _res(r):
    v = (r.get('local_residual') or {}).get('mean_nlm_px')
    return 99.0 if v is None else v


def is_clean(r):
    lr = r['local_residual']['mean_nlm_px']
    lab = r['label_choice']
    # identity is taken as settled when the label and the whole frame choose the same photograph (two different
    # criteria), or, without a label, when the frame choice has a margin over its neighbours
    ident_ok = (lab is not None and r['label_and_frame_agree'] is True) \
        or (lab is None and r['frame_choice']['margin'] is not None and r['frame_choice']['margin'] >= 0.005)
    return lr is not None and lr <= 0.5 and r['similarity']['ncc_full'] >= 0.97 and ident_ok


def region_stats(matched):
    """Group contiguous slices by identical (offset_best, rounded rotation, rounded translation) into runs."""
    runs = []
    for r in sorted(matched, key=lambda r: r['k']):
        s = r['similarity']
        key = (r['offset_best'], round(s['rotation_deg'], 1), round(s['tc_nlm_px']), round(s['tr_nlm_px']))
        if runs and runs[-1]['key'] == key and r['k'] - runs[-1]['k_last'] <= ARGS.step:
            runs[-1]['k_last'] = r['k']; runs[-1]['rows'].append(r)
        else:
            runs.append({'key': key, 'k_first': r['k'], 'k_last': r['k'], 'rows': [r]})
    out = []
    for run in runs:
        rs = run['rows']
        sims = np.array([[x['similarity']['tc_nlm_px'], x['similarity']['tr_nlm_px'], x['similarity']['scale_nlm_px_per_denver_px'], x['similarity']['rotation_deg']] for x in rs])
        loc = np.array([x['local_residual']['mean_nlm_px'] for x in rs if x['local_residual']['mean_nlm_px'] is not None])
        out.append({'k_first': run['k_first'], 'k_last': run['k_last'], 'slices': len(rs), 'offset': run['key'][0],
                    'nlm_first': rs[0]['nlm_best'], 'nlm_last': rs[-1]['nlm_best'],
                    'z_denver_mm': [rs[0]['z_denver_mm'], rs[-1]['z_denver_mm']],
                    'tc_nlm_px_median': round(float(np.median(sims[:, 0])), 3), 'tr_nlm_px_median': round(float(np.median(sims[:, 1])), 3),
                    'scale_median': round(float(np.median(sims[:, 2])), 5), 'rotation_deg_median': round(float(np.median(sims[:, 3])), 4),
                    'ncc_full_median': round(float(np.median([x['similarity']['ncc_full'] for x in rs])), 4),
                    'local_residual_mean_nlm_px_median': round(float(np.median(loc)), 3) if len(loc) else None,
                    'local_residual_mean_nlm_px_max': round(float(loc.max()), 3) if len(loc) else None})
    return out


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument('--nlm', required=True); ap.add_argument('--denver', required=True); ap.add_argument('--inventory', required=True)
    ap.add_argument('--step', type=int, default=1); ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--out', default='cryosection-alignment.json')
    ap.add_argument('--ks', default=None, help='comma-separated explicit Denver slice indices (overrides --step)')
    ap.add_argument('--window', type=int, default=8, help='NLM sub-slices searched on each side of the predicted index')
    ap.add_argument('--offset', type=int, default=DEFAULT_OFFSET, help='predicted NLM index for Denver k = 0 (n = offset - k)')
    ap.add_argument('--debug-png', default=None, help='write Denver | resampled NLM | difference panels here')
    ap.add_argument('--no-probe', action='store_true')
    ap.add_argument('--compact', action='store_true', help='drop the rotation-grid tables and the per-block residual rows from the written report (summary figures kept)')
    ap.add_argument('--refine-from', default=None, help='previous dense report: re-run only the slices inconsistent with their neighbours, seeded from them')
    ARGS = ap.parse_args()
    t0 = time.time()
    if ARGS.debug_png:
        Path(ARGS.debug_png).mkdir(parents=True, exist_ok=True)
    inventory = json.loads(Path(ARGS.inventory).read_text())
    probe = None if ARGS.no_probe else orient_probe([500, 1500, 2500, 3400])
    if ARGS.ks:
        ks = sorted({int(x) for x in ARGS.ks.split(',')})
    else:
        ks = sorted(set(range(0, DEN_N, ARGS.step)) | {1, 2, DEN_N - 2, DEN_N - 1})
    if ARGS.refine_from:
        rows = refine_pass(json.loads(Path(ARGS.refine_from).read_text())['slices'], inventory)
        ks = [r['k'] for r in rows]
        summarise(rows, ks, inventory, probe, t0); return
    with ProcessPoolExecutor(ARGS.workers) as ex:
        rows = list(ex.map(one, ks, chunksize=8))
        # second pass: slices whose fit or identity is weak are re-run seeded from the nearest clean neighbour
        good = [r for r in rows if r['status'] == 'matched' and is_clean(r)]
        bad = [r for r in rows if r['status'] == 'matched' and not is_clean(r)]
        if good and bad:
            jobs = []
            for r in bad:
                nb = min(good, key=lambda g: abs(g['k'] - r['k']))
                s_ = nb['similarity']
                jobs.append((r['k'], {'params': [s_['tc_nlm_px'], s_['tr_nlm_px'], s_['scale_nlm_px_per_denver_px'], np.radians(s_['rotation_deg'])],
                                      'offset': nb['offset_best'], 'from_k': nb['k']}))
            redo = list(ex.map(one, jobs, chunksize=1))
            by_k = {r['k']: i for i, r in enumerate(rows)}
            for r2 in redo:
                r1 = rows[by_k[r2['k']]]
                if r2['status'] == 'matched' and _res(r2) <= _res(r1) \
                        and r2['similarity']['ncc_full'] >= r1['similarity']['ncc_full'] - 1e-4:
                    r2['pass1'] = {'n_best': r1['n_best'], 'similarity': r1['similarity'], 'local_residual_mean_nlm_px': r1['local_residual']['mean_nlm_px']}
                    rows[by_k[r2['k']]] = r2
                else:
                    r1['pass2_rejected'] = {'n_best': r2.get('n_best'), 'similarity': r2.get('similarity'), 'local_residual_mean_nlm_px': (r2.get('local_residual') or {}).get('mean_nlm_px')}
    summarise(rows, ks, inventory, probe, t0)


def refine_pass(rows, inventory):
    """Third pass: slices whose photograph offset, residual, NCC or identity disagree with their neighbours are re-run
    with a seed taken from the consistent neighbours (median similarity within +-10 slices, their offset) and a +-3 window."""
    matched = sorted([r for r in rows if r['status'] == 'matched'], key=lambda r: r['k'])
    ks = np.array([r['k'] for r in matched]); offs = np.array([r['offset_best'] for r in matched])
    mode = np.array([np.median(offs[max(0, i - 15):i + 16]) for i in range(len(matched))])
    shared = {}
    for r in matched:
        shared.setdefault(r['n_best'], []).append(r['k'])
    def suspect(i, r):
        return (offs[i] != mode[i] or _res(r) > 0.5 or r['similarity']['ncc_full'] < 0.97 or len(shared[r['n_best']]) > 1
                or r['label_and_frame_agree'] is False)
    targets = [(i, r) for i, r in enumerate(matched) if suspect(i, r)]
    consistent = [(i, r) for i, r in enumerate(matched) if not suspect(i, r)]
    jobs = []
    for i, r in targets:
        nb = [q for j, q in consistent if abs(q['k'] - r['k']) <= 10] or [min(consistent, key=lambda t: abs(t[1]['k'] - r['k']))[1]]
        sims = np.array([[q['similarity']['tc_nlm_px'], q['similarity']['tr_nlm_px'], q['similarity']['scale_nlm_px_per_denver_px'], np.radians(q['similarity']['rotation_deg'])] for q in nb])
        med = np.median(sims, axis=0)
        jobs.append((r['k'], {'params': [float(x) for x in med], 'offset': int(round(float(np.median([q['offset_best'] for q in nb])))), 'from_k': [q['k'] for q in nb][:3]}))
    print(json.dumps({'refine_targets': len(jobs), 'ks': [j[0] for j in jobs]}), flush=True)
    old_window = ARGS.window; ARGS.window = 3
    with ProcessPoolExecutor(ARGS.workers) as ex:
        redo = list(ex.map(one, jobs, chunksize=1))
    ARGS.window = old_window
    by_k = {r['k']: i for i, r in enumerate(rows)}
    kept = 0
    for r2 in redo:
        r1 = rows[by_k[r2['k']]]
        ok = r2['status'] == 'matched' and r2['similarity']['ncc_full'] >= r1['similarity']['ncc_full'] - 0.005 and _res(r2) <= max(_res(r1), 0.5)
        if ok:
            r2['pass'] = 3; r2['previous'] = {'n_best': r1['n_best'], 'offset_best': r1['offset_best'], 'similarity': r1['similarity'], 'local_residual_mean_nlm_px': r1['local_residual']['mean_nlm_px']}
            rows[by_k[r2['k']]] = r2; kept += 1
        else:
            r1['pass3_rejected'] = {'n_best': r2.get('n_best'), 'offset_best': r2.get('offset_best'), 'similarity': r2.get('similarity'), 'local_residual_mean_nlm_px': (r2.get('local_residual') or {}).get('mean_nlm_px')}
    print(json.dumps({'refine_kept': kept, 'refine_rejected': len(redo) - kept}), flush=True)
    return rows


def summarise(rows, ks, inventory, probe, t0):
    matched = [r for r in rows if r['status'] == 'matched']
    fit = None
    if len(matched) >= 3:
        kk = np.array([r['k'] for r in matched], float); nn = np.array([r['n_best'] for r in matched], float)
        b, a = np.polyfit(kk, nn, 1)
        offs = [r['offset_best'] for r in matched]
        fit = {'a': round(float(a), 4), 'b': round(float(b), 6), 'hypothesis': {'a': ARGS.offset, 'b': -1},
               'offset_histogram': {str(int(o)): int(c) for o, c in zip(*np.unique(offs, return_counts=True))},
               'identity_by': {s: sum(1 for r in matched if r['identity_by'] == s) for s in ('label', 'frame')},
               'label_and_frame_agree': int(sum(1 for r in matched if r['label_and_frame_agree'])),
               'label_and_frame_disagree': int(sum(1 for r in matched if r['label_and_frame_agree'] is False)),
               'label_margin_min': round(float(min(r['label_choice']['margin'] for r in matched if r['label_choice'] and r['label_choice']['margin'] is not None)), 4) if any(r['label_choice'] for r in matched) else None,
               'frame_margin_min': round(float(min(r['frame_choice']['margin'] for r in matched if r['frame_choice']['margin'] is not None)), 4),
               'best_at_window_edge': int(sum(r['best_at_window_edge'] for r in matched)), 'window': ARGS.window,
               'second_pass_kept': int(sum(1 for r in matched if r.get('pass') == 2)),
               'second_pass_rejected': int(sum(1 for r in matched if 'pass2_rejected' in r)),
               'third_pass_kept': int(sum(1 for r in matched if r.get('pass') == 3)),
               'third_pass_rejected': int(sum(1 for r in matched if 'pass3_rejected' in r)),
               'not_clean_after_all_passes': [r['k'] for r in matched if not is_clean(r)]}
    def stats(v):
        return {'median': round(float(np.median(v)), 4), 'min': round(float(v.min()), 4), 'max': round(float(v.max()), 4),
                'p95_abs_dev_from_median': round(float(np.percentile(np.abs(v - np.median(v)), 95)), 4)} if len(v) else None
    sims = np.array([[r['similarity']['tc_nlm_px'], r['similarity']['tr_nlm_px'], r['similarity']['scale_nlm_px_per_denver_px'],
                      r['similarity']['rotation_deg']] for r in matched]) if matched else np.zeros((0, 4))
    local_means = np.array([r['local_residual']['mean_nlm_px'] for r in matched if r['local_residual']['mean_nlm_px'] is not None])
    local_max = np.array([r['local_residual']['max_nlm_px'] for r in matched if r['local_residual']['max_nlm_px'] is not None])
    gray = np.array([r['gray_fit']['weights_rgb'] + [r['gray_fit']['bias'], r['gray_fit']['rms']] for r in matched]) if matched else None
    dense = ARGS.ks is None and ARGS.step == 1
    step = ARGS.step
    chosen_ns = [r['n_best'] for r in matched]
    unmatched_nlm = None; shared = None
    if dense and matched:
        lo, hi = min(chosen_ns), max(chosen_ns)
        files = {r['file'] for r in inventory['files']}
        unmatched_nlm = [nlm_name(n) for n in range(lo, hi + 1) if n not in set(chosen_ns) and nlm_name(n) in files
                         and nlm_name(n) not in set(inventory['summary']['constant_or_blank'])]
        cnt = {}
        for r in matched:
            cnt.setdefault(r['n_best'], []).append(r['k'])
        shared = {nlm_name(n): ks_ for n, ks_ in cnt.items() if len(ks_) > 1}
    summary = {
        'denver_slices_sampled': len(ks), 'matched': len(matched), 'step': ARGS.step,
        'statuses': {s: sum(1 for r in rows if r['status'] == s) for s in sorted({r['status'] for r in rows})},
        'orientation': 'flip_x (Denver = NLM photograph mirrored left-right)', 'orientation_probe_ncc_half': probe,
        'slice_identity_fit': fit,
        'regions': region_stats(matched) if matched else None,
        'similarity_all': {'tc_nlm_px': stats(sims[:, 0]), 'tr_nlm_px': stats(sims[:, 1]),
                           'scale_nlm_px_per_denver_px': stats(sims[:, 2]), 'rotation_deg': stats(sims[:, 3])} if len(sims) else None,
        'ncc_full': stats(np.array([r['similarity']['ncc_full'] for r in matched])) if matched else None,
        'local_residual_nlm_px': {'mean_of_slice_means': round(float(local_means.mean()), 4) if len(local_means) else None,
                                  'p95_of_slice_means': round(float(np.percentile(local_means, 95)), 4) if len(local_means) else None,
                                  'max_block': round(float(local_max.max()), 4) if len(local_max) else None,
                                  'slices_with_mean_above_1px': int((local_means > 1.0).sum()) if len(local_means) else None,
                                  'slices_with_mean_above_1px_k': [r['k'] for r in matched if _res(r) > 1.0]},
        'gray_fit': {'weights_rgb_median': [round(float(x), 4) for x in np.median(gray[:, :3], axis=0)],
                     'bias_median': round(float(np.median(gray[:, 3])), 3), 'rms_median': round(float(np.median(gray[:, 4])), 3)} if gray is not None else None,
        'criterion': {'statement': 'mean in-plane residual below one NLM pixel (1/3 mm) per slice, pelvis to feet, image to image',
                      'threshold_nlm_px': 1.0,
                      'passed_slices': int((local_means < 1.0).sum()) if len(local_means) else None,
                      'failed_slices': int((local_means >= 1.0).sum()) if len(local_means) else None},
        'nlm_photographs_in_range_no_denver_slice_chose': unmatched_nlm,
        'nlm_photographs_chosen_by_several_denver_slices': shared,
        'gaps': gap_report(inventory, rows),
        'geometry': {'denver': {'columns': DEN_W, 'rows': DEN_H, 'slices': DEN_N, 'pixel_mm': 0.666, 'slice_mm': 0.333,
                                'ijk_to_lps': 'x = 0.666 i + 316.35, y = 0.666 j + 311.022, z = 0.333 (k - 1) (VHF_Full.mat, transposed storage)'},
                     'nlm': {'columns': W, 'rows': H, 'declared_pixel_mm': 0.33, 'declared_slice_mm': 0.33, 'index': 'n = 3 (mm - 1001) + {a: 0, b: 1, c: 2}'},
                     'model': 'Denver k <-> NLM n = offset - k per region; Denver pixel (i, j) -> NLM (c, r) = s R(theta) (-i, j) + (tc, tr)'},
        'limits': ['image-to-image comparison of two publications of the same block; nothing anatomical',
                   'a similarity per slice: local block shifts above zero mean Denver applied more than a similarity to that slice',
                   'above the pelvis (NLM 1001 to about 1552) Denver has no aligned photographs; nothing here covers that region',
                   'the NLM pixel size is inferred from Denver\'s stated 0.666 mm through the measured scale: a ratio of pixel grids, not an absolute calibration',
                   'slice identity by label uses the handwritten card photographed with each slice; where no card is found the whole frame decides and neighbouring photographs differ little'],
        'seconds': round(time.time() - t0, 1),
    }
    if ARGS.compact:
        for r in rows:
            if 'initialisation' in r:
                r['initialisation'].pop('grid', None)
            if 'local_residual' in r and 'blocks' in r['local_residual']:
                r['local_residual']['blocks_textured_shift_nlm_px'] = [b.get('shift_nlm_px') for b in r['local_residual']['blocks'] if b.get('textured')]
                del r['local_residual']['blocks']
        summary['compact'] = True
    Path(ARGS.out).write_text(json.dumps({'summary': summary, 'slices': rows}, indent=1))
    print(json.dumps({'done': True, 'out': ARGS.out, 'matched': len(matched), 'seconds': summary['seconds'], 'fit': fit,
                      'local_residual': summary['local_residual_nlm_px'], 'regions': summary['regions']}))


if __name__ == '__main__':
    main()
