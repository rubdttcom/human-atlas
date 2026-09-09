"""Stitch Skellytour chunk outputs back onto the full CT grid, deterministically and with provenance.

Usage: merge-skellytour.py <ct.nii.gz> <outdir> [--allow-missing]

Rules (the only fusion; run-skellytour-chunked.sh calls this script, it has no copy of its own):
  * every chunk of chunks/plan.json must have exactly one candidate output: `*_postprocessed.nii.gz`
    when present, otherwise exactly one other `*.nii.gz` that is not `temp`; zero or several candidates
    stop the merge (exit 2) unless --allow-missing is given, and even then the missing chunks are listed
    in the manifest and the merge is marked `complete: false`, never silently zero-filled;
  * the core band of each chunk [core0, core1) is copied; the overlap outside the core is used only to
    check label identity across the seam (same label on both sides of core1 where both chunks predict);
  * the manifest skellytour_high.json records per chunk the file used, its SHA-256, the labels present
    and the seam agreement, plus the crop box (voxels outside the crop were never processed).
"""
import glob
import hashlib
import json
import sys

import nibabel as nib
import numpy as np

args = [a for a in sys.argv[1:] if not a.startswith('--')]
allow_missing = '--allow-missing' in sys.argv
inp, out = args
im = nib.load(inp)
plan = json.load(open(f'{out}/chunks/plan.json'))
i0, i1, j0, j1 = plan['crop']
full = np.zeros(im.shape, np.uint8)
manifest = {'source': inp, 'plan': f'{out}/chunks/plan.json', 'crop_ijk': {'i': [i0, i1], 'j': [j0, j1]},
            'processed_region_note': 'voxels outside crop_ijk were never given to the model (unprocessed, not negative)',
            'chunks': [], 'missing': [], 'seams': []}
prev = None   # (chunk dict, seg array) of the previous chunk, for the seam check


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


for p in plan['chunks']:
    c = p['chunk']
    post = sorted(glob.glob(f'{out}/chunks/out{c}/*_postprocessed.nii.gz'))
    raw = sorted(f for f in glob.glob(f'{out}/chunks/out{c}/*.nii.gz') if 'temp' not in f and not f.endswith('_postprocessed.nii.gz'))
    cands = post or raw
    if len(cands) != 1:
        msg = f'chunk {c}: {len(cands)} candidates {cands or "(none)"} (postprocessed {len(post)}, raw {len(raw)})'
        if not allow_missing or cands:
            sys.exit('merge stopped: ' + msg)
        print('MISSING', msg, flush=True)
        manifest['missing'].append(c)
        prev = None
        continue
    seg = np.asanyarray(nib.load(cands[0]).dataobj).astype(np.uint8)
    assert seg.shape == (i1 - i0, j1 - j0, p['z1'] - p['z0']), (c, seg.shape)
    a, b = p['core0'] - p['z0'], p['core1'] - p['z0']
    full[i0:i1, j0:j1, p['core0']:p['core1']] = seg[:, :, a:b]
    labels = [int(x) for x in np.unique(seg) if x]
    manifest['chunks'].append({'chunk': c, 'file': cands[0].split('/')[-1], 'kind': 'postprocessed' if post else 'raw', 'sha256': sha(cands[0]),
                               'z0': p['z0'], 'z1': p['z1'], 'core0': p['core0'], 'core1': p['core1'], 'labels': labels})
    print('chunk', c, cands[0].split('/')[-1], 'labels', len(labels), flush=True)
    if prev is not None:
        # seam at z = p['core0'] (= prev core1): both chunks predicted the band [p['z0'], prev['z1'])
        q, pseg = prev
        lo, hi = max(q['z0'], p['z0']), min(q['z1'], p['z1'])
        A = pseg[:, :, lo - q['z0']:hi - q['z0']]
        B = seg[:, :, lo - p['z0']:hi - p['z0']]
        both = (A > 0) & (B > 0)
        n = int(both.sum())
        same = int((A[both] == B[both]).sum())
        pairs = {}
        if n:
            u, cnt = np.unique(np.stack([A[both], B[both]]), axis=1, return_counts=True)
            for (x, y), k in zip(u.T, cnt):
                if x != y:
                    pairs[f'{int(x)}->{int(y)}'] = int(k)
        manifest['seams'].append({'between': [q['chunk'], c], 'seam_z': p['core0'], 'overlap_z': [lo, hi], 'voxels_both_labelled': n,
                                  'same_label_fraction': round(same / n, 4) if n else None,
                                  'label_changes': dict(sorted(pairs.items(), key=lambda kv: -kv[1])[:20])})
        print('seam', q['chunk'], c, 'z', p['core0'], 'agreement', manifest['seams'][-1]['same_label_fraction'], 'changes', len(pairs), flush=True)
    prev = (p, seg)

nib.save(nib.Nifti1Image(full, im.affine), f'{out}/skellytour_high.nii.gz')
u, n = np.unique(full, return_counts=True)
manifest.update({'complete': not manifest['missing'], 'chunks_done': [c['chunk'] for c in manifest['chunks']], 'chunks_planned': len(plan['chunks']),
                 'labels': int(len(u) - 1), 'label_voxels': {int(k): int(v) for k, v in zip(u[1:], n[1:])},
                 'merged_sha256': sha(f'{out}/skellytour_high.nii.gz')})
json.dump(manifest, open(f'{out}/skellytour_high.json', 'w'), indent=1)
print('merged labels', len(u) - 1, 'voxels', int(n[1:].sum()), 'chunks', manifest['chunks_done'], 'of', len(plan['chunks']), 'complete', manifest['complete'])
