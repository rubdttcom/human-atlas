"""Observability of the tissue under Denver's original labels, per slice, around the block boundaries (Codex RGB review, 13 September 2026).

The frozen body was cut in blocks; the photographs at a block face show frost, damaged or missing tissue while Denver's
labels continue over them (seen at k 1207, 1210 and 2259, identity settled, NCC above 0.99: identity and integrity do
not protect against this). This script measures, for every Denver slice of the requested bands, the colour of the
photograph pixels under the original labels once mapped with the per-slice transform:
  tissue-like   the rest (red, pink, yellow, cream, white bone)
  block-like    B > R + 10 (the blue block or gelatin showing through)
  dark          max(R, G, B) < 60
  frost-like    min(R, G, B) > 140 and max - min < 45 and B >= R - 5 (a neutral whitish or bluish-white opaque surface)
Per band, the interior slices (10 or more slices away from the boundary) give a baseline (median and MAD of the
non-tissue fraction); a slice is flagged when its non-tissue fraction exceeds the baseline by 3 MAD and by an absolute
floor of 0.10. Flags delimit the quarantine extent; they are not a universal artefact detector and they decide nothing
about slices outside the requested bands. Runs on rub-pc:
  python3 scripts/cryosection-observability-band.py --nlm DIR --slabs denver-label-slabs.npz --transform nlm-cryosection-to-vhf.json --out band.json
"""
import argparse
import hashlib
import json
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy import ndimage

W, H = 2048, 1216
DEN_W, DEN_H = 666, 434
ARGS = None
SLABS = None
PER = None
BANDS = {'feet_start': (7, 39, 'start of the feet-knee block'), 'knee_boundary': (1170, 1249, 'feet-knee block end (k 1207) and knee-thigh block start (k 1210)'),
         'thigh_boundary': (2225, 2259, 'knee-thigh block end'), 'pelvis_start': (2285, 2329, 'mid-thigh-pelvis block start'), 'pelvis_end': (3490, 3532, 'top of the Denver range')}
BOUNDARY_KS = {7, 1207, 1210, 2259, 2285, 3532}


def nlm_name(n):
    return f'avf{1001 + n // 3:04d}{"abc"[n % 3]}.raw.Z'


def load_rgb(n):
    p = Path(ARGS.nlm) / nlm_name(n)
    raw = subprocess.run(['gzip', '-dc', str(p)], capture_output=True, check=True, timeout=600).stdout
    return np.frombuffer(raw, np.uint8).reshape(3, H, W).transpose(1, 2, 0).astype(np.float32), hashlib.sha256(raw).hexdigest()


def one(k):
    p = PER.get(k)
    row = {'k': k}
    if p is None:
        row['status'] = 'no-transform-row'; return row
    lab = SLABS[str(k)].astype(bool)
    if lab.sum() == 0:
        row['status'] = 'no-denver-labels'; row['n'] = p['n']; return row
    rgb, sha = load_rgb(p['n'])
    tc, tr, s, th = p['tc'], p['tr'], p['s'], np.radians(p['theta_deg'])
    jj, ii = np.nonzero(lab)
    u, v = -ii.astype(np.float32), jj.astype(np.float32)
    c = s * (np.cos(th) * u - np.sin(th) * v) + tc; r = s * (np.sin(th) * u + np.cos(th) * v) + tr
    R, G, B = [ndimage.map_coordinates(rgb[..., ch], [r, c], order=1, mode='nearest') for ch in range(3)]
    mx, mn = np.maximum(np.maximum(R, G), B), np.minimum(np.minimum(R, G), B)
    block = B > R + 10
    dark = mx < 60
    frost = (mn > 140) & ((mx - mn) < 45) & (B >= R - 5)
    non_tissue = block | dark | frost
    row.update({'status': 'measured', 'n': p['n'], 'nlm': nlm_name(p['n']), 'photo_raw_sha256': sha, 'labelled_px': int(lab.sum()),
                'fraction_block_like': round(float(block.mean()), 4), 'fraction_dark': round(float(dark.mean()), 4),
                'fraction_frost_like': round(float(frost.mean()), 4), 'fraction_non_tissue': round(float(non_tissue.mean()), 4),
                'identity_status': p['identity_status']})
    return row


def main():
    global ARGS, SLABS, PER
    ap = argparse.ArgumentParser()
    ap.add_argument('--nlm', required=True); ap.add_argument('--slabs', required=True); ap.add_argument('--transform', required=True)
    ap.add_argument('--out', default='observability-band.json'); ap.add_argument('--workers', type=int, default=8)
    ARGS = ap.parse_args()
    t0 = time.time()
    SLABS = dict(np.load(ARGS.slabs))
    tr = json.loads(Path(ARGS.transform).read_text())
    PER = {p['k']: p for p in tr['per_slice']}
    ks = sorted(int(k) for k in SLABS)
    with ProcessPoolExecutor(ARGS.workers) as ex:
        rows = list(ex.map(one, ks, chunksize=4))
    by_k = {r['k']: r for r in rows}
    bands = {}
    flagged = []
    for name, (k0, k1, desc) in BANDS.items():
        rs = [by_k[k] for k in range(k0, k1 + 1) if k in by_k and by_k[k]['status'] == 'measured']
        interior = [r for r in rs if all(abs(r['k'] - b) >= 10 for b in BOUNDARY_KS)]
        vals = np.array([r['fraction_non_tissue'] for r in interior]) if interior else np.array([])
        if len(vals) >= 5:
            med = float(np.median(vals)); mad = float(np.median(np.abs(vals - med))) or 0.01
            thr = max(med + 3 * mad, med + 0.10)
        else:
            med = mad = None; thr = 0.25
        fl = [r['k'] for r in rs if r['fraction_non_tissue'] > thr]
        flagged += fl
        bands[name] = {'k_range': [k0, k1], 'description': desc, 'measured': len(rs), 'interior_slices': len(interior),
                       'baseline_non_tissue': {'median': round(med, 4) if med is not None else None, 'mad': round(mad, 4) if mad is not None else None, 'threshold': round(thr, 4)},
                       'flagged_k': fl,
                       'profile': [{'k': r['k'], 'nlm': r['nlm'], 'non_tissue': r['fraction_non_tissue'], 'block': r['fraction_block_like'], 'dark': r['fraction_dark'], 'frost': r['fraction_frost_like']} for r in rs]}
    out = {'summary': {'bands': bands, 'flagged_k': sorted(set(flagged)), 'rule': 'non-tissue fraction under the original labels > max(median + 3 MAD, median + 0.10) of the band interior (>= 10 slices from a block boundary)',
                       'colour_classes': {'block_like': 'B > R + 10', 'dark': 'max(R,G,B) < 60', 'frost_like': 'min(R,G,B) > 140 and max - min < 45 and B >= R - 5'},
                       'limits': ['bands only; nothing is said about slices outside them', 'colour thresholds, not a universal artefact detector; a flagged slice is quarantined whole, unflagged slices are not thereby clean',
                                  'Denver labels are measured where they exist; slices without original labels report no-denver-labels'],
                       'seconds': round(time.time() - t0, 1)}, 'rows': rows}
    Path(ARGS.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({'done': True, 'flagged_k': out['summary']['flagged_k'], 'bands': {n: (b['baseline_non_tissue'], b['flagged_k']) for n, b in bands.items()}}))


if __name__ == '__main__':
    main()
