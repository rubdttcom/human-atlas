"""Apply the versioned tissue map to one aligned RGB block: Denver original labels -> tissue classes with ignore (plan B stage 2).

Reads the block directory written by build-cryosection-rgb-block.py (rgb-kji.npy, denver-original-labels.nii.gz,
manifest.json) and registry/cryo-tissue-map.json, and writes tissue-classes.nii.gz (uint8, (i, j, k), same affine) plus a
report. The precedence is the one declared in the map and nothing else:
  1. slice status not usable / usable-flagged  -> every voxel 255 (ignore)
  2. Denver label != 0                          -> class of the table
  3. Denver 0 inside the body mask              -> 255 (ignore: unknown tissue, never background)
  4. Denver 0 outside the body mask             -> 0 (background: block, air, table)
The body mask is the colour rule of the map (R > B + 25 and max(R, G, B) > 60 on the resampled RGB, closing, hole filling,
components >= 811 px). It decides only background against unknown; label voxels never depend on it.

--selftest runs the precedence on a synthetic slice (label outside the body kept, unlabelled inside = ignore, excluded slice
all ignore) before touching the block. Nothing here is anatomy.

  .venv/bin/python scripts/build-cryo-tissue-classes.py --block data/derived/nlm-vhf/cryosections/block2 [--selftest]
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
TMAP = ROOT / 'registry/cryo-tissue-map.json'
IGNORE = 255
PAIRED = ('usable', 'usable-flagged')
MIN_COMPONENT_PX = 811


def sha256_file(p, chunk=1 << 24):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            h.update(b)
    return h.hexdigest()


def body_mask(rgb_ji3):
    R, G, B = [rgb_ji3[..., c].astype(np.int16) for c in range(3)]
    body = (R > B + 25) & (rgb_ji3.max(axis=2) > 60)
    body = ndimage.binary_closing(body, iterations=2)
    body = ndimage.binary_fill_holes(body)
    lab, n = ndimage.label(body)
    if n:
        sizes = np.bincount(lab.ravel())[1:]
        keep = np.where(sizes >= MIN_COMPONENT_PX)[0] + 1
        body = np.isin(lab, keep)
    return body


def classify_slice(rgb_ji3, labels_ji, lut, paired):
    if not paired:
        return np.full(labels_ji.shape, IGNORE, np.uint8), None
    out = lut[labels_ji]
    body = body_mask(rgb_ji3)
    unl = labels_ji == 0
    out[unl & body] = IGNORE
    out[unl & ~body] = 0
    return out, body


def selftest(lut):
    rgb = np.zeros((40, 60, 3), np.uint8); rgb[..., 2] = 120                       # blue block everywhere
    rgb[5:35, 10:50] = (200, 120, 100)                                              # a reddish body
    lab = np.zeros((40, 60), np.uint8)
    lab[10:20, 15:25] = 4                                                           # Left_Bone_Femur inside the body
    lab[1:3, 1:3] = 39                                                              # a muscle label outside the body (kept: labels are trusted)
    out, body = classify_slice(rgb, lab, lut, True)
    assert out[15, 20] == 1, 'bone label must map to class 1'
    assert out[2, 2] == 3, 'a label outside the body mask keeps its class'
    assert out[30, 40] == IGNORE, 'unlabelled inside the body is ignore'
    assert out[38, 58] == 0, 'unlabelled outside the body is background'
    out2, _ = classify_slice(rgb, lab, lut, False)
    assert (out2 == IGNORE).all(), 'an excluded slice is all ignore'
    rgb3 = rgb.copy(); rgb3[20:22, 30:32] = (10, 10, 120)                           # a blue hole inside the body: filled, still body
    out3, _ = classify_slice(rgb3, lab, lut, True)
    assert out3[20, 30] == IGNORE, 'holes inside the body are filled'
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--block', required=True)
    ap.add_argument('--tissue-map', default=str(TMAP))
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    t0 = time.time()
    tmap = json.loads(Path(a.tissue_map).read_text())
    lut = np.full(256, IGNORE, np.uint8)
    for r in tmap['labels']:
        lut[r['value']] = r['class']
    if a.selftest:
        selftest(lut)
        print(json.dumps({'selftest': 'passed'}))
    block = Path(a.block)
    man = json.loads((block / 'manifest.json').read_text())
    rgb = np.load(block / 'rgb-kji.npy', mmap_mode='r')
    limg = nib.load(str(block / 'denver-original-labels.nii.gz'))
    labels_ijk = np.asarray(limg.dataobj).astype(np.uint8)
    K = labels_ijk.shape[2]
    if rgb.shape[0] != K or man['block']['slices'] != K:
        raise SystemExit('rgb, labels and manifest disagree on the number of slices')
    if sha256_file(block / 'rgb-kji.npy') != man['outputs']['rgb_sha256'] or sha256_file(block / 'denver-original-labels.nii.gz') != man['outputs']['labels_sha256']:
        raise SystemExit('block files do not match the manifest hashes')
    present = {int(v) for v in np.unique(labels_ijk)}
    mapped = {r['value'] for r in tmap['labels']}
    if present - mapped:
        raise SystemExit(f'Denver label values without a map entry: {sorted(present - mapped)}')
    status = {r['k']: r['status'] for r in man['per_slice']}
    k_first = man['block']['k_first']
    out = np.empty_like(labels_ijk)
    per_slice = []
    for kk in range(K):
        k = k_first + kk
        paired = status[k] in PAIRED
        cls, body = classify_slice(np.asarray(rgb[kk]), labels_ijk[:, :, kk].T, lut, paired)
        out[:, :, kk] = cls.T
        row = {'k': k, 'status': status[k]}
        if body is not None:
            lab_ji = labels_ijk[:, :, kk].T
            row.update({'body_px': int(body.sum()), 'labelled_px': int((lab_ji != 0).sum()), 'labelled_outside_body_px': int(((lab_ji != 0) & ~body).sum()),
                        'ignore_inside_body_px': int(((lab_ji == 0) & body).sum()), 'ignore_fraction_of_body': round(float(((lab_ji == 0) & body).sum() / max(1, body.sum())), 4)})
        per_slice.append(row)
    img = nib.Nifti1Image(out, limg.affine)
    img.header.set_xyzt_units('mm')
    out_path = block / 'tissue-classes.nii.gz'
    nib.save(img, out_path)
    counts = np.bincount(out.ravel(), minlength=256)
    names = {c['value']: c['name'] for c in tmap['classes']}
    per_class = {names[v]: int(c) for v, c in enumerate(counts) if c}
    paired_rows = [r for r in per_slice if 'body_px' in r]
    report = {
        'id': 'cryo-tissue-classes-block%d' % man['block']['region'], 'date': time.strftime('%Y-%m-%d'), 'block': man['block'],
        'sources': {'manifest_sha256': sha256_file(block / 'manifest.json'), 'rgb_sha256': man['outputs']['rgb_sha256'], 'labels_sha256': man['outputs']['labels_sha256'],
                    'tissue_map': str(Path(a.tissue_map).relative_to(ROOT)), 'tissue_map_sha256': sha256_file(a.tissue_map), 'tissue_map_version': tmap['version']},
        'output': {'file': out_path.name, 'sha256': sha256_file(out_path), 'order': '(i, j, k) uint8, affine of the labels NIfTI', 'ignore_value': IGNORE},
        'voxels_per_class': per_class,
        'paired_slices': len(paired_rows), 'ignored_slices': K - len(paired_rows),
        'body': {'ignore_fraction_of_body_median': round(float(np.median([r['ignore_fraction_of_body'] for r in paired_rows])), 4) if paired_rows else None,
                 'labelled_outside_body_px_total': int(sum(r['labelled_outside_body_px'] for r in paired_rows)),
                 'labelled_px_total': int(sum(r['labelled_px'] for r in paired_rows)),
                 'note': 'labelled pixels outside the colour body mask are kept with their class (labels are trusted); the count says how often the colour rule and Denver disagree at the outline, nothing more'},
        'per_slice': per_slice,
        'statement': 'class-level derived volume for the loss and the metrics of the pilot; unknown tissue inside the body is ignore, never background; excluded slices are ignore; nothing here is anatomy',
        'seconds': round(time.time() - t0, 1),
    }
    rep_path = ROOT / 'generated' / ('cryo-tissue-classes-block%d.json' % man['block']['region'])
    rep_path.write_text(json.dumps(report, indent=1))
    print(json.dumps({'done': True, 'out': str(out_path), 'report': str(rep_path.relative_to(ROOT)), 'voxels_per_class': per_class, 'body': report['body'], 'sha256': report['output']['sha256'], 'seconds': report['seconds']}))


if __name__ == '__main__':
    main()
