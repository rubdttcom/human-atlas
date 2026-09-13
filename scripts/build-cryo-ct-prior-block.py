"""Carry the fresh-CT TotalSegmentator labels onto one cryosection block grid as pilot tissue classes (plan B stage 2).

Input for the rgb-plus-ct-prior variant only. The prior never enters the loss target, the reference or the metrics: the
target stays registry/cryo-tissue-map.json applied to the Denver original labels (tissue-classes.nii.gz).

  block voxel (i, j, k) --ijk_to_ras_block--> VHF-image-2022 mm --inverse(nlm-ct-to-vhf)--> CT RAS mm
                        --inverse(CT affine)--> CT voxel --nearest neighbour--> TotalSegmentator label
                        --registry/cryo-ct-prior-map.json--> 0 none / 1 bone / 2 cartilage / 3 muscle

Nearest neighbour, never interpolation: a label is not a number. Voxels outside the CT field of view are 0 (none), which
says "the prior is silent here", never "background". The placement is the published pelvis-fitted rigid transform; its
measured per-structure error (femora 7.5 to 8.7 mm in this block) is copied into the report and is not corrected here.

  .venv/bin/python scripts/build-cryo-ct-prior-block.py --block data/derived/nlm-vhf/cryosections/block2 [--selftest]

Writes <block>/ct-prior-tissue.nii.gz (uint8, (i, j, k), the block affine) and generated/cryo-ct-prior-block2.json with the
coverage measured per class, per slice stratum and against the Denver reference. Nothing here is anatomy.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PRIOR_MAP = ROOT / 'registry/cryo-ct-prior-map.json'
TRANSFORM = ROOT / 'transforms/nlm-ct-to-vhf.json'
CT_LABELS = ROOT / 'data/derived/nlm-vhf/totalseg.nii'
BANDS = ROOT / 'registry/cryo-eval-bands-v1.json'
CLASS_VALUE = {'none': 0, 'bone': 1, 'cartilage': 2, 'muscle': 3}


def sha256_file(p, chunk=1 << 24):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            h.update(b)
    return h.hexdigest()


def lut_from_map(pmap):
    """Exhaustive lookup table: every declared label value -> class value, everything else 0 (none)."""
    values = [e['value'] for e in pmap['labels']]
    lut = np.zeros(max(values) + 1, dtype=np.uint8)
    for e in pmap['labels']:
        lut[e['value']] = CLASS_VALUE[e['class']]
    return lut


def sample_slice(k, A_block, M_inv, ct_inv, ct_data, lut, shape_ij):
    """Nearest-neighbour sample of the CT label volume at the centres of one block slice."""
    ni, nj = shape_ij
    ii, jj = np.meshgrid(np.arange(ni, dtype=np.float64), np.arange(nj, dtype=np.float64), indexing='ij')
    ones = np.ones(ii.size)
    hom = np.stack([ii.ravel(), jj.ravel(), np.full(ii.size, float(k)), ones])
    ras = A_block @ hom                      # VHF-image-2022 mm
    ct_ras = M_inv @ ras                     # CT RAS mm
    vox = ct_inv @ ct_ras                    # CT voxel
    idx = np.rint(vox[:3]).astype(np.int64)
    inside = np.ones(idx.shape[1], dtype=bool)
    for d in range(3):
        inside &= (idx[d] >= 0) & (idx[d] < ct_data.shape[d])
    out = np.zeros(idx.shape[1], dtype=np.uint8)
    if inside.any():
        raw = ct_data[idx[0][inside], idx[1][inside], idx[2][inside]]
        out[inside] = lut[np.clip(raw, 0, len(lut) - 1)]
    return out.reshape(ni, nj), inside.reshape(ni, nj)


def selftest():
    """A synthetic CT whose only labels are one bone and one muscle value, sampled through an identity placement."""
    lut = np.zeros(200, dtype=np.uint8)
    lut[75] = CLASS_VALUE['bone']
    lut[80] = CLASS_VALUE['muscle']
    ct = np.zeros((4, 4, 4), dtype=np.uint8)
    ct[1, 1, 1] = 75
    ct[2, 2, 2] = 80
    ct[3, 3, 3] = 51                       # an organ label: must map to none
    eye = np.eye(4)
    got = {}
    for k in range(4):
        cls, inside = sample_slice(k, eye, eye, eye, ct, lut, (4, 4))
        got[k] = cls
    assert got[1][1, 1] == CLASS_VALUE['bone'], 'bone label lost'
    assert got[2][2, 2] == CLASS_VALUE['muscle'], 'muscle label lost'
    assert got[3][3, 3] == 0, 'organ label did not map to none'
    assert got[0].sum() == 0, 'label invented on an empty slice'
    # a voxel outside the CT grid must be none and must be reported outside
    far = np.eye(4)
    far[0, 3] = 1000.0
    cls, inside = sample_slice(1, far, np.eye(4), np.eye(4), ct, lut, (4, 4))
    assert cls.sum() == 0 and not inside.any(), 'out-of-field voxels were not silent'
    print(json.dumps({'selftest': 'ok'}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--block', required=True)
    ap.add_argument('--out', default=None)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    t0 = time.time()

    block = Path(a.block)
    man = json.loads((block / 'manifest.json').read_text())
    pmap = json.loads(PRIOR_MAP.read_text())
    tf = json.loads(TRANSFORM.read_text())
    bands = json.loads(BANDS.read_text())

    nk, nj, ni = man['grid']['shape_kji3'][:3]
    A_block = np.array(man['grid']['ijk_to_ras_block'], dtype=np.float64)
    M = np.array(tf['matrix_row_major'], dtype=np.float64).reshape(4, 4)
    M_inv = np.linalg.inv(M)

    img = nib.load(CT_LABELS)
    ct_data = np.asanyarray(img.dataobj)
    ct_inv = np.linalg.inv(img.affine)
    lut = lut_from_map(pmap)

    prior = np.zeros((ni, nj, nk), dtype=np.uint8)
    in_field = np.zeros(nk, dtype=np.int64)
    for k in range(nk):
        cls, inside = sample_slice(k, A_block, M_inv, ct_inv, ct_data, lut, (ni, nj))
        prior[:, :, k] = cls
        in_field[k] = int(inside.sum())

    canonical = block / 'ct-prior-tissue.nii.gz'
    out = Path(a.out) if a.out else canonical
    ref = nib.load(block / 'tissue-classes.nii.gz')
    nib.save(nib.Nifti1Image(prior, ref.affine, dtype=np.uint8), out)

    # coverage, per class and per slice stratum
    te = bands['training_eligibility']
    k_first = man['block']['k_first']
    primary = sorted({k for lo, hi in te['primary_k_ranges'] for k in range(lo, hi + 1)})
    scoring = sorted({k for b in bands['bands'] for k in range(b['k_first'], b['k_last'] + 1)})

    tissue = np.asanyarray(nib.load(block / 'tissue-classes.nii.gz').dataobj)

    def stratum(ks):
        idx = [k - k_first for k in ks if 0 <= k - k_first < nk]
        p = prior[:, :, idx]
        r = tissue[:, :, idx]
        row = {'slices': len(idx), 'prior_voxels': {}, 'reference_voxels': {}, 'prior_recall_of_reference': {}}
        for name, v in (('bone', 1), ('cartilage', 2), ('muscle', 3)):
            pv = int((p == v).sum())
            rv = int((r == v).sum())
            hit = int(((p == v) & (r == v)).sum())
            row['prior_voxels'][name] = pv
            row['reference_voxels'][name] = rv
            row['prior_recall_of_reference'][name] = round(hit / rv, 4) if rv else None
        row['prior_any_voxels'] = int((p > 0).sum())
        return row

    report = {
        'id': 'cryo-ct-prior-block2',
        'date': time.strftime('%Y-%m-%d'),
        'block': man['block'],
        'inputs': {
            'prior_map': str(PRIOR_MAP.relative_to(ROOT)), 'prior_map_sha256': sha256_file(PRIOR_MAP),
            'transform': str(TRANSFORM.relative_to(ROOT)), 'transform_sha256': sha256_file(TRANSFORM),
            'ct_labels': str(CT_LABELS.relative_to(ROOT)), 'ct_labels_sha256': sha256_file(CT_LABELS),
            'block_manifest_sha256': sha256_file(block / 'manifest.json'),
            'tissue_classes_sha256': sha256_file(block / 'tissue-classes.nii.gz'),
            'bands': str(BANDS.relative_to(ROOT)), 'bands_sha256': sha256_file(BANDS),
        },
        'outputs': {'prior': out.name, 'prior_sha256': sha256_file(out), 'dtype': 'uint8', 'order': '(i, j, k)'},
        'method': {
            'resampling': 'nearest neighbour on the block voxel centres; no interpolation of label values',
            'placement': pmap['placement'],
            'outside_field_of_view': 'class 0 (none): the prior is silent, never background',
        },
        'coverage': {
            'slices_with_any_ct_field_of_view': int((in_field > 0).sum()),
            'whole_block': stratum(range(k_first, k_first + nk)),
            'primary_training_slices': stratum(primary),
            'band_scoring_slices': stratum(scoring),
        },
        'limits': pmap['limits'] + [
            'prior_recall_of_reference is the fraction of Denver reference voxels of a class that the placed CT prior also '
            'calls that class; it mixes segmentation difference, placement error and posture, and separates none of them',
            'reference voxels here include every voxel of the class, ignored slices excluded only where the reference is 255',
        ],
        'seconds': round(time.time() - t0, 1),
    }
    # A throwaway run must not overwrite the canonical report. The earlier version always wrote to the fixed
    # path, so an audit run with --out pointing at a discard file replaced the committed report with one naming
    # a volume that never existed there, and git add -A swept it into 97cf1b5 (found while applying the Codex
    # audit of 1af1c60). The report now follows the output it describes.
    rp = ROOT / 'generated/cryo-ct-prior-block2.json' if out == canonical else out.with_suffix('').with_suffix('.report.json')
    report['outputs']['path'] = str(out)
    report['outputs']['is_canonical'] = out == canonical
    rp.write_text(json.dumps(report, indent=1) + '\n')
    shown = rp.relative_to(ROOT) if rp.is_relative_to(ROOT) else rp   # a scratch build reports outside the repo
    print(json.dumps({'ok': True, 'out': str(out), 'report': str(shown),
                      'primary': report['coverage']['primary_training_slices'],
                      'seconds': report['seconds']}))


if __name__ == '__main__':
    main()
