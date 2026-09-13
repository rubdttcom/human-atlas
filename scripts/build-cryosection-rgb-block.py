"""Aligned RGB volume of one Denver block from the NLM colour photographs (plan B stage 2, RGB pilot, step 1).

Runs on the box that holds the photographs and Denver's aligned grayscale slices (rub-pc):
  python3 scripts/build-cryosection-rgb-block.py --nlm /media/rub/Backups/VHF/Female-Images/fullbody \
      --denver "/media/rub/Backups/VHF/denver/aligned-cryo/Aligned Cryosection-DICOM" \
      --transform nlm-cryosection-to-vhf.json --pairs cryosection-pair-selection.json \
      --labels block2-k2285-3532-labels.npz --region 2 --out OUTDIR --workers 12

What it does. For every Denver slice k of the requested block it takes the photograph chosen by the transform
(`transforms/nlm-cryosection-to-vhf.json`, per-slice similarity Denver (i, j) -> photograph (c, r) = s R(theta) (-i, j) + (tc, tr),
mirror included) and resamples the photograph's RGB onto the Denver grid (666 x 434 at 0.666 mm): the photograph is first
averaged 2 x 2 (Denver derived its slices the same way; one Denver pixel = 2.0000 photograph pixels), then sampled
bilinearly at the mapped coordinates. The result is one uint8 volume (k, j, i, 3) plus Denver's ORIGINAL labels for the
same slices (from the .npz written by extract-denver-label-block.py, byte copy of VHF_Full.mat) written as NIfTI in the
canonical frame, and a manifest that binds everything by SHA-256: every photograph (compressed file and decompressed
bytes), the transform, the pair selection and its policy, the label slab and its .mat, the output volume.

Pair policy (generated/cryosection-pair-selection.json, pairs-v1) decides which slices carry a photograph:
  usable, usable-flagged      -> resampled (the flag travels with the slice in the manifest)
  excluded-identity           -> slice left zero, status recorded; the photograph is one of an ambiguity set 1/3 mm apart
  excluded-observability      -> slice left zero, status recorded (quarantine: frost or block under the labels)
  no-reference (Denver blank) -> slice left zero, status recorded
Zero slices are IGNORE for any consumer (never background, never training, never scoring); the manifest says which.

Check per resampled slice (image to image, not anatomy): NCC between the resampled luminance (Denver's own gray weights
0.218 R + 0.710 G + 0.089 B, measured on 13 September 2026) and Denver's aligned grayscale slice; every --control-every
slices the same with the Denver i axis mirrored (a negative control that must score lower). A slice below --ncc-min is
flagged in the manifest and counted; nothing is silently dropped.

Originals are read only. The output volume is a derived, hash-bound copy for the pilot. Nothing here is anatomy.
"""
import argparse
import hashlib
import json
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import nibabel as nib
import numpy as np
import pydicom
from scipy import ndimage

W, H = 2048, 1216
DEN_W, DEN_H = 666, 434
GRAY_W = np.array([0.218, 0.710, 0.089], dtype=np.float32)   # Denver gray from the photograph RGB, median fit of the alignment check
ARGS = None
PER = None


def nlm_name(n):
    return f'avf{1001 + n // 3:04d}{"abc"[n % 3]}.raw.Z'


def sha256_file(p, chunk=1 << 24):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            h.update(b)
    return h.hexdigest()


def load_photo(n):
    p = Path(ARGS.nlm) / nlm_name(n)
    if not p.exists():
        return None, None, None
    raw = subprocess.run(['gzip', '-dc', str(p)], capture_output=True, check=True, timeout=600).stdout
    if len(raw) != W * H * 3:
        return None, sha256_file(p), hashlib.sha256(raw).hexdigest()
    rgb = np.frombuffer(raw, np.uint8).reshape(3, H, W).transpose(1, 2, 0).astype(np.float32)
    return rgb, sha256_file(p), hashlib.sha256(raw).hexdigest()


def half(img):
    """2 x 2 box average; half pixel (rh, ch) has its centre at full-resolution (2 rh + 0.5, 2 ch + 0.5)."""
    return img.reshape(H // 2, 2, W // 2, 2, img.shape[2]).mean(axis=(1, 3))


def denver_grid_coords(p, mirror_i=False):
    """Full-resolution photograph coordinates (r, c) of every Denver pixel (j row, i col), shape (DEN_H, DEN_W)."""
    tc, tr, s, th = p['tc'], p['tr'], p['s'], np.radians(p['theta_deg'])
    jj, ii = np.mgrid[0:DEN_H, 0:DEN_W].astype(np.float32)
    if mirror_i:
        ii = (DEN_W - 1) - ii
    u, v = -ii, jj
    c = s * (np.cos(th) * u - np.sin(th) * v) + tc
    r = s * (np.sin(th) * u + np.cos(th) * v) + tr
    return r, c


def resample(hrgb, r, c):
    rh, ch = (r - 0.5) / 2.0, (c - 0.5) / 2.0
    out = np.empty((DEN_H, DEN_W, 3), dtype=np.float32)
    for ch_i in range(3):
        out[..., ch_i] = ndimage.map_coordinates(hrgb[..., ch_i], [rh, ch], order=1, mode='constant', cval=0.0)
    return out


def ncc(a, b):
    a = a - a.mean(); b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def load_denver(k):
    return pydicom.dcmread(Path(ARGS.denver) / f'VHF_Full_VHF_Scan{k:04d}.dcm').pixel_array.astype(np.float32)


def one(task):
    k, p, status, control = task
    row = {'k': k, 'n': p['n'], 'nlm': nlm_name(p['n']), 'status': status, 'identity_status': p['identity_status'],
           'tc': p['tc'], 'tr': p['tr'], 's': p['s'], 'theta_deg': p['theta_deg']}
    rgb, sha_c, sha_raw = load_photo(p['n'])
    row['photo_compressed_sha256'] = sha_c
    row['photo_raw_sha256'] = sha_raw
    if rgb is None:
        row['status'] = 'photograph-unreadable'
        return row, None
    hrgb = half(rgb)
    r, c = denver_grid_coords(p)
    out = resample(hrgb, r, c)
    den = load_denver(k)
    row['denver_sha256'] = hashlib.sha256(den.astype(np.uint8).tobytes()).hexdigest()
    lum = out @ GRAY_W
    row['ncc_luminance_vs_denver'] = round(ncc(lum, den), 4)
    row['outside_photograph_fraction'] = round(float(((r < 0) | (r > H - 1) | (c < 0) | (c > W - 1)).mean()), 4)
    if control:
        rm, cm = denver_grid_coords(p, mirror_i=True)
        row['ncc_mirror_control'] = round(ncc(resample(hrgb, rm, cm) @ GRAY_W, den), 4)
    return row, np.clip(np.rint(out), 0, 255).astype(np.uint8)


def main():
    global ARGS, PER
    ap = argparse.ArgumentParser()
    ap.add_argument('--nlm', required=True)
    ap.add_argument('--denver', required=True)
    ap.add_argument('--transform', required=True)
    ap.add_argument('--pairs', required=True)
    ap.add_argument('--labels', required=True)
    ap.add_argument('--region', type=int, required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--control-every', type=int, default=25)
    ap.add_argument('--ncc-min', type=float, default=0.95)
    ARGS = ap.parse_args()
    t0 = time.time()
    doc = json.loads(Path(ARGS.transform).read_text())
    pairs = json.loads(Path(ARGS.pairs).read_text())
    transform_sha = hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()
    if pairs['source']['transform_sha256'] != transform_sha:
        raise SystemExit('pair selection was made from another transform (sha256 mismatch)')
    region = next(g for g in doc['regions'] if g['region'] == ARGS.region)
    k_first, k_last = region['k_first'], region['k_last']
    PER = {p['k']: p for p in doc['per_slice']}
    status = {}
    for k in pairs['usable_k']:
        status[k] = 'usable'
    for e in pairs['usable_flagged']:
        status[e['k']] = 'usable-flagged'
    for e in pairs['excluded_identity']:
        status[e['k']] = 'excluded-identity'
    for e in pairs['excluded_observability']:
        status[e['k']] = 'excluded-observability'
    for k in pairs['no_reference_blank_denver_k']:
        status[k] = 'no-reference-blank-denver'
    ks = list(range(k_first, k_last + 1))
    missing = [k for k in ks if k not in status]
    if missing:
        raise SystemExit(f'slices without a pair-selection status: {missing[:10]}...')

    lab = np.load(ARGS.labels, allow_pickle=False)
    lmeta = json.loads(str(lab['meta']))
    labels = lab['labels']
    if lmeta['k_first'] != k_first or lmeta['k_last'] != k_last:
        raise SystemExit(f"label slab covers k {lmeta['k_first']}..{lmeta['k_last']}, block is {k_first}..{k_last}")
    if labels.shape != (len(ks), DEN_H, DEN_W):
        raise SystemExit(f'label slab shape {labels.shape} does not match the block')

    out = Path(ARGS.out)
    out.mkdir(parents=True, exist_ok=True)
    rgb_path = out / 'rgb-kji.npy'
    vol = np.lib.format.open_memmap(rgb_path, mode='w+', dtype=np.uint8, shape=(len(ks), DEN_H, DEN_W, 3))
    vol[:] = 0
    tasks = [(k, PER[k], status[k], (idx % ARGS.control_every) == 0) for idx, k in enumerate(ks) if status[k] in ('usable', 'usable-flagged')]
    rows = {}
    with ProcessPoolExecutor(ARGS.workers) as ex:
        for row, sl in ex.map(one, tasks, chunksize=4):
            rows[row['k']] = row
            if sl is not None:
                vol[row['k'] - k_first] = sl
    vol.flush()
    del vol
    for k in ks:
        if k not in rows:
            p = PER.get(k)
            rows[k] = {'k': k, 'status': status[k], 'n': p['n'] if p else None, 'nlm': nlm_name(p['n']) if p else None,
                       'identity_status': p['identity_status'] if p else None, 'photo_compressed_sha256': None, 'note': 'slice left zero: ignore'}
            if status[k] == 'excluded-identity':
                e = next(e for e in pairs['excluded_identity'] if e['k'] == k)
                rows[k]['ambiguity_set_nlm'] = e['ambiguity_set_nlm']; rows[k]['ambiguity_span_mm'] = e['ambiguity_span_mm']
            if status[k] == 'excluded-observability':
                e = next(e for e in pairs['excluded_observability'] if e['k'] == k)
                rows[k]['reason'] = e['reason']; rows[k]['photo_compressed_sha256'] = e['photo_compressed_sha256']
    table = [rows[k] for k in ks]

    # Denver original labels of the block as NIfTI (i, j, k) in the canonical frame.
    A = np.array(lmeta['ijk_to_lps_full'], dtype=np.float64)
    affine = A.copy()
    affine[:3, 3] = (A @ np.array([0, 0, k_first, 1.0]))[:3]
    lab_ijk = np.ascontiguousarray(labels.transpose(2, 1, 0))
    img = nib.Nifti1Image(lab_ijk, affine)
    img.header.set_xyzt_units('mm')
    labels_path = out / 'denver-original-labels.nii.gz'
    nib.save(img, labels_path)

    resampled = [r for r in table if r['status'] in ('usable', 'usable-flagged') and 'ncc_luminance_vs_denver' in r]
    nccs = np.array([r['ncc_luminance_vs_denver'] for r in resampled])
    low = [r['k'] for r in resampled if r['ncc_luminance_vs_denver'] < ARGS.ncc_min]
    ctrl = [(r['ncc_luminance_vs_denver'], r['ncc_mirror_control']) for r in resampled if 'ncc_mirror_control' in r]
    counts = {}
    for r in table:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    manifest = {
        'id': f'cryosection-rgb-block{ARGS.region}', 'date': time.strftime('%Y-%m-%d'), 'block': {'region': ARGS.region, 'k_first': k_first, 'k_last': k_last, 'slices': len(ks),
                                                                                                     'z_mm': [round(0.333 * k_first - 0.333, 3), round(0.333 * k_last - 0.333, 3)], 'nlm_first': region['nlm_first'], 'nlm_last': region['nlm_last']},
        'grid': {'storage_order_rgb': '(k, j, i, channel) uint8, channel = R, G, B', 'shape_kji3': [len(ks), DEN_H, DEN_W, 3], 'spacing_mm_ijk': [0.666, 0.666, 0.333],
                 'ijk_to_ras_block': affine.tolist(), 'frame': 'VHF-image-2022 (Denver label-map frame; +i subject right, +j anterior, +k superior)',
                 'labels_nifti_order': '(i, j, k) uint8, same affine'},
        'method': {'photograph_prefilter': '2 x 2 box average (Denver derived its aligned slices the same way; 1 Denver px = 2.0000 photograph px)',
                   'sampling': 'bilinear (scipy map_coordinates order 1) at Denver pixel centres mapped by the per-slice similarity of the transform; outside the photograph = 0',
                   'similarity': 'Denver (i, j) -> photograph (c, r) = s R(theta) (-i, j) + (tc, tr); the -i is the left-right mirror Denver applied',
                   'check': 'NCC of 0.218 R + 0.710 G + 0.089 B against Denver aligned gray slice k; mirror control every %d slices' % ARGS.control_every},
        'sources': {'transform': Path(ARGS.transform).name, 'transform_sha256': transform_sha, 'transform_id': doc['id'],
                    'pairs': Path(ARGS.pairs).name, 'pairs_sha256': hashlib.sha256(json.dumps(pairs, sort_keys=True).encode()).hexdigest(), 'pairs_policy': pairs['policy']['id'],
                    'labels_npz': Path(ARGS.labels).name, 'labels_npz_sha256': sha256_file(ARGS.labels), 'labels_mat': lmeta['source'], 'labels_mat_sha256': lmeta['source_sha256'],
                    'photographs_dir': ARGS.nlm, 'denver_aligned_dir': ARGS.denver},
        'outputs': {'rgb': rgb_path.name, 'rgb_sha256': sha256_file(rgb_path), 'rgb_bytes': rgb_path.stat().st_size,
                    'labels': labels_path.name, 'labels_sha256': sha256_file(labels_path), 'labels_present': lmeta['labels_present_in_block'], 'label_names': lmeta['names']},
        'counts': counts,
        'check': {'ncc_min_threshold': ARGS.ncc_min, 'resampled': len(resampled), 'ncc_median': round(float(np.median(nccs)), 4) if len(nccs) else None,
                  'ncc_p05': round(float(np.quantile(nccs, 0.05)), 4) if len(nccs) else None, 'ncc_min': round(float(nccs.min()), 4) if len(nccs) else None,
                  'below_threshold_k': low, 'mirror_controls': len(ctrl),
                  'mirror_control_lower_in_all': bool(all(m < n for n, m in ctrl)) if ctrl else None,
                  'mirror_control_median': round(float(np.median([m for _, m in ctrl])), 4) if ctrl else None},
        'ignore_rule': 'slices with status other than usable / usable-flagged are zero in the RGB volume and are IGNORE for every consumer: never background, never training, never scoring; the labels NIfTI still holds Denver labels there, the status column decides',
        'per_slice': table,
        'limits': ['image-to-image resampling of one publication onto the grid of another; no anatomical content is checked',
                   'usable-flagged slices rest on the whole-frame identity only; the flag is in the status column',
                   'excluded slices are not wrong: their photograph is one of the ambiguity set; they wait for a different criterion, never a lower threshold',
                   'observability was measured only in the block-boundary bands; an unflagged slice elsewhere was not inspected'],
        'seconds': round(time.time() - t0, 1),
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    print(json.dumps({'done': True, 'out': str(out), 'counts': counts, 'check': manifest['check'], 'rgb_sha256': manifest['outputs']['rgb_sha256'], 'seconds': manifest['seconds']}))


if __name__ == '__main__':
    main()
