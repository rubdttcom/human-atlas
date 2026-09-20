"""Assemble the per-slice nnU-Net 2D predictions of one variant into the block volume the evaluator grades.

The evaluator refuses anything that is not the reference grid: same shape, same affine, integer dtype, values only in the
active output classes. This script writes exactly that and nothing else.

  slices predicted by nnU-Net: <case>.nii.gz of shape (i, j, 1), case = block2_kNNNNN
  output: (i, j, k) uint8 on the block affine, class 0 on every slice that was not predicted

A slice that was not predicted is written 0. That is not a claim: the evaluator scores only band slices with pair status
usable or usable-flagged, and the report records which slices carried a prediction. A predicted slice whose k is outside
the block, or a duplicate, is a hard error.

Every slice is checked BEFORE anything is converted or copied (Codex audit of 1af1c60, P1-1). The earlier version read
the unique values through int(), then cast with astype(uint8): both truncate, so a float slice holding 1.9 became class 1
and the assembled volume then passed the evaluator's prediction gate. It also ignored the input affine entirely and
replaced it with the reference one, so a slice placed a metre away was assembled without a word. The gate below refuses
a non-integral value, a non-finite value and an affine that is not this dataset's 2D case grid, and it refuses before
the slice reaches the volume.

  .venv/bin/python scripts/assemble-cryo-prediction.py --block data/derived/nlm-vhf/cryosections/block2 \
      --predictions data/derived/nnunet/pred/Dataset501.../ --variant rgb-only --out generated/... .nii.gz

Nothing here is anatomy.
"""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BANDS = ROOT / 'registry/cryo-eval-bands-v1.json'
PROTOCOL = ROOT / 'registry/machine-acceptance-protocol-v1.json'
CASE = re.compile(r'^block2_k(\d{5})\.nii\.gz$')
DUMMY_SLICE_SPACING_MM = 999.0   # the slice axis of a 2D case, written by scripts/build-cryo-nnunet-dataset.py
AFFINE_ATOL_MM = 1e-3            # NIfTI headers store float32, so an exact comparison would be brittle


def slice_gate(img, k, ni, nj, allowed, expected_affine):
    """Refuse a prediction slice before any conversion. Returns the validated integer array."""
    raw = np.asanyarray(img.dataobj)
    arr = np.squeeze(raw)
    if arr.shape != (ni, nj):
        return None, f'shape {arr.shape} differs from the case grid {(ni, nj)}'
    if not np.issubdtype(raw.dtype, np.integer):
        if not np.isfinite(arr).all():
            return None, f'dtype {raw.dtype} with non-finite values'
        if not np.array_equal(arr, np.rint(arr)):
            bad = arr[arr != np.rint(arr)]
            return None, f'dtype {raw.dtype} with fractional values, first {float(bad.flat[0])}'
        arr = np.rint(arr)
    vals = set(int(v) for v in np.unique(arr))      # safe now: every value is already integral
    if not vals <= allowed:
        return None, f'classes {sorted(vals - allowed)} outside the active output classes {sorted(allowed)}'
    if not np.allclose(img.affine, expected_affine, atol=AFFINE_ATOL_MM):
        return None, ('affine is not this dataset\'s 2D case grid; got diagonal '
                      f'{[round(float(img.affine[i, i]), 4) for i in range(3)]} and translation '
                      f'{[round(float(img.affine[i, 3]), 4) for i in range(3)]}')
    return arr.astype(np.uint8), None


def sha256_file(p, chunk=1 << 24):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--block', required=True)
    ap.add_argument('--predictions', required=True)
    ap.add_argument('--variant', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report-tag', default='',
                    help="suffix of the report name, e.g. '-v2' for a prior-version 2 run, so the version 1 report of the same variant is not overwritten")
    a = ap.parse_args()
    t0 = time.time()

    block = Path(a.block)
    man = json.loads((block / 'manifest.json').read_text())
    bands = json.loads(BANDS.read_text())
    protocol = json.loads(PROTOCOL.read_text())
    allowed = set(protocol['training']['active_output_classes'])

    ref = nib.load(block / 'tissue-classes.nii.gz')
    ni, nj, nk = ref.shape
    k_first = man['block']['k_first']
    out = np.zeros((ni, nj, nk), dtype=np.uint8)
    # the grid a 2D case was written on: block in-plane spacing, dummy spacing on the slice axis
    sx, sy, _ = man['grid']['spacing_mm_ijk']
    expected_affine = np.diag([sx, sy, DUMMY_SLICE_SPACING_MM, 1.0])

    files = sorted(Path(a.predictions).glob('block2_k*.nii.gz'))
    if not files:
        raise SystemExit(json.dumps({'ok': False, 'error': f'no prediction slice in {a.predictions}'}))
    written = []
    for f in files:
        m = CASE.match(f.name)
        if not m:
            raise SystemExit(json.dumps({'ok': False, 'error': f'unexpected file name {f.name}'}))
        k = int(m.group(1))
        z = k - k_first
        if not 0 <= z < nk:
            raise SystemExit(json.dumps({'ok': False, 'error': f'slice k {k} is outside the block'}))
        if z in written:
            raise SystemExit(json.dumps({'ok': False, 'error': f'slice k {k} predicted twice'}))
        arr, why = slice_gate(nib.load(f), k, ni, nj, allowed, expected_affine)
        if why is not None:
            raise SystemExit(json.dumps({'ok': False, 'error': f'slice k {k}: {why}'}))
        out[:, :, z] = arr
        written.append(z)

    op = Path(a.out)
    op.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(out, ref.affine, dtype=np.uint8), op)

    scoring = sorted({k for b in bands['bands'] for k in range(b['k_first'], b['k_last'] + 1)})
    status = {r['k']: r['status'] for r in man['per_slice']}
    eligible = [k for k in scoring if status.get(k) in ('usable', 'usable-flagged')]
    got = {z + k_first for z in written}
    missing = [k for k in eligible if k not in got]

    report = {
        'id': f'cryo-prediction-block2-{a.variant}', 'date': time.strftime('%Y-%m-%d'), 'variant': a.variant,
        'output': {'path': str(op), 'sha256': sha256_file(op), 'shape': [ni, nj, nk], 'dtype': 'uint8'},
        'slices': {'predicted': len(written), 'band_eligible': len(eligible),
                   'band_eligible_without_prediction': missing,
                   'outside_the_bands': sorted(k for k in got if k not in set(scoring))},
        'note': 'slices without a prediction are class 0; the evaluator scores only eligible band slices',
        'slice_gate': {
            'checked_before_conversion': ['squeezed shape', 'integer dtype or an exactly integral float',
                                          'finite values', 'only the active output classes',
                                          "the 2D case affine, diag(%.3f, %.3f, %.1f)" % (sx, sy, DUMMY_SLICE_SPACING_MM)],
            'affine_atol_mm': AFFINE_ATOL_MM,
            'reason': 'Codex audit of 1af1c60, P1-1: reading values through int() and casting with astype truncated a '
                      'fractional class, and the input affine was ignored, so a slice from another grid was accepted',
        },
        'seconds': round(time.time() - t0, 1),
    }
    rp = ROOT / f'generated/cryo-prediction-block2-{a.variant}{a.report_tag}.json'
    rp.write_text(json.dumps(report, indent=1) + '\n')
    shown = rp.relative_to(ROOT) if rp.is_relative_to(ROOT) else rp
    print(json.dumps({'ok': not missing, 'out': str(op), 'predicted': len(written),
                      'band_eligible_without_prediction': len(missing), 'report': str(shown)}))
    if missing:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
