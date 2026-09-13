"""Extract one z block of Denver's ORIGINAL label map (VHF_Full.mat) as a compressed slab for the RGB pilot (plan B stage 2).

Denver's original hand-painted labels are the training and evaluation reference of the cryosection pilot (plan B 2.1:
training always uses the original maps, never the voxelised final meshes). This script copies the slices k_first..k_last of
`segmentation_data/label_data` (stored (k, j, i), uint8, 131 label values = index into `geometry_labels/name`) into one
.npz together with the label names, the ijk -> LPS/RAS matrix of the block and the SHA-256 of the .mat, so the slab can
travel to the GPU box without h5py and the RGB block builder can bind its manifest to the exact source bytes. The .mat is
read only; nothing is written back.

  .venv/bin/python scripts/extract-denver-label-block.py --k-first 2285 --k-last 3532 \
      --out data/derived/denver/label-blocks/block2-k2285-3532-labels.npz

Nothing here is anatomy: it copies bytes and records where they came from.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MAT = ROOT / 'data/raw/denver/extracted/Original Segmentation Labelmaps-mat_tif/VHF_Full.mat'


def sha256_file(p, chunk=1 << 24):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mat', default=str(MAT))
    ap.add_argument('--k-first', type=int, required=True)
    ap.add_argument('--k-last', type=int, required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    t0 = time.time()
    with h5py.File(a.mat, 'r') as f:
        g = f['segmentation_data']
        names = [''.join(chr(int(c)) for c in f[r][()].ravel()) for r in g['geometry_labels/name'][()].ravel()]
        raw_t = np.array(g['ijkToLpsTransform'][()], dtype=np.float64)
        ijk_to_lps = raw_t.T if abs(raw_t[3, 3] - 1.0) < 1e-9 and raw_t[3, 0] == 0 else raw_t     # stored transposed (translation in the last row)
        if not (abs(ijk_to_lps[3, 3] - 1.0) < 1e-9 and np.allclose(ijk_to_lps[3, :3], 0)):
            ijk_to_lps = raw_t.T
        ld = g['label_data']
        K = ld.shape[0]
        if not (0 <= a.k_first <= a.k_last < K):
            raise SystemExit(f'k range outside the label map (0..{K - 1})')
        slab = ld[a.k_first:a.k_last + 1]                     # (k, j, i) uint8
        scales = [float(np.array(g[n][()]).ravel()[0]) for n in ('x_scale', 'y_scale', 'z_scale')]
    counts = np.bincount(slab.ravel(), minlength=256)
    present = {int(v): int(c) for v, c in enumerate(counts) if c > 0}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    mat_sha = sha256_file(a.mat)
    meta = {
        'source': str(Path(a.mat).resolve().relative_to(ROOT)) if str(Path(a.mat).resolve()).startswith(str(ROOT)) else a.mat,
        'source_sha256': mat_sha, 'dataset': 'segmentation_data/label_data', 'storage_order': '(k, j, i)', 'dtype': 'uint8',
        'label_value_is_index_into_names': True, 'k_first': a.k_first, 'k_last': a.k_last, 'slices': int(slab.shape[0]),
        'full_shape_kji': [int(x) for x in ld.shape], 'ijk_to_lps_full': ijk_to_lps.tolist(), 'scales_xyz_mm': scales,
        'frame_note': 'ijkToLpsTransform as stored; the numbers place +i = subject right and +z superior in the canonical frame VHF-image-2022 (transforms/canonical-space.json); z(k) = 0.333 k - 0.333',
        'labels_present_in_block': present, 'names': names, 'date': time.strftime('%Y-%m-%d'),
        'statement': 'byte copy of Denver original labels for one block; originals untouched; nothing here is anatomy',
    }
    np.savez_compressed(out, labels=slab, meta=json.dumps(meta))
    print(json.dumps({'done': True, 'out': str(out), 'slices': int(slab.shape[0]), 'labels_present': len(present) - (1 if 0 in present else 0),
                      'npz_sha256': sha256_file(out), 'mat_sha256': mat_sha, 'seconds': round(time.time() - t0, 1)}))


if __name__ == '__main__':
    main()
