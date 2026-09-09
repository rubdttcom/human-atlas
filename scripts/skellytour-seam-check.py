"""Label continuity of the stitched Skellytour volume across its chunk seams (local check, no chunk files needed).

Usage: python scripts/skellytour-seam-check.py nlm | denver

For every seam z = core1 of chunks/plan.json: agreement of labels between slice z-1 (previous chunk) and
slice z (next chunk) over voxels labelled on both, compared with the same figure on the slices around it
(z-4..z-1 and z..z+3, inside one chunk). A seam whose agreement falls clearly below its neighbourhood, or
or a vertebra label whose voxels at z-1 mostly carry another label at z (identity kept < 0.5), means the
chunk-local vertebra numbering changed at the seam. Boundary jitter between two neighbouring vertebrae
that both cross the seam keeps identity > 0.5 and is not renumbering. Also lists every label whose
z-extent crosses a seam (Skellytour scatters a few SKULL and label-60 voxels along the whole body, so
those two cross every seam).
Output: generated/skellytour-seams-<ct>.json
"""
import json
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
CT = sys.argv[1]
D = ROOT / ('data/derived/nlm-vhf/skellytour' if CT == 'nlm' else 'data/derived/denver/priors/skellytour')
plan = json.loads((D / 'plan.json').read_text())
arr = np.asanyarray(nib.load(D / 'skellytour_high.nii.gz').dataobj).astype(np.uint8)
NAMES = {1: 'SKULL', 2: 'PELVIS', 3: 'STERNUM', 4: 'LEFT_FEMUR', 5: 'RIGHT_FEMUR', 6: 'LEFT_HUMERUS', 7: 'RIGHT_HUMERUS', 8: 'LEFT_SCAPULA', 9: 'RIGHT_SCAPULA', 10: 'LEFT_CLAVICLE', 11: 'RIGHT_CLAVICLE'}
NAMES.update({11 + i: f'LEFT_RIB_{i}' for i in range(1, 13)})
NAMES.update({23 + i: f'RIGHT_RIB_{i}' for i in range(1, 13)})
NAMES.update({35 + i: f'VERT_{i}' for i in range(1, 25)})


def agreement(z):
    a, b = arr[:, :, z - 1], arr[:, :, z]
    both = (a > 0) & (b > 0)
    n = int(both.sum())
    if not n:
        return None, {}
    changes = {}
    u, cnt = np.unique(np.stack([a[both], b[both]]), axis=1, return_counts=True)
    for (x, y), k in zip(u.T, cnt):
        if x != y:
            changes[f'{NAMES.get(int(x), int(x))}->{NAMES.get(int(y), int(y))}'] = int(k)
    return round(float((a[both] == b[both]).sum() / n), 4), dict(sorted(changes.items(), key=lambda kv: -kv[1])[:10])


objs = ndimage.find_objects(arr)
extent = {i + 1: (o[2].start, o[2].stop) for i, o in enumerate(objs) if o is not None}
seams = []
for p in plan['chunks'][1:]:
    z = p['core0']
    ag, ch = agreement(z)
    around = [agreement(zz)[0] for zz in list(range(z - 4, z - 1)) + list(range(z + 1, z + 4)) if 0 < zz < arr.shape[2]]
    around = [x for x in around if x is not None]
    # identity kept across the seam, per label present on both sides: of the voxels labelled l at z-1 that are labelled at z, which fraction keep l
    a, b = arr[:, :, z - 1], arr[:, :, z]
    keep, count = {}, {}
    for l in np.unique(a[(a > 0) & (b > 0)]):
        m = (a == l) & (b > 0)
        if m.sum() >= 20:
            keep[NAMES.get(int(l), int(l))] = round(float((b[m] == l).sum() / m.sum()), 4)
            count[NAMES.get(int(l), int(l))] = int(m.sum())
    crossing = [NAMES.get(l, l) for l, (z0, z1) in extent.items() if z0 < z < z1]
    # a renumbering moves a whole vertebra cross-section (hundreds of voxels), not the tip of a body ending at the seam
    renumbered = [k for k, v in keep.items() if k.startswith('VERT') and v < 0.5 and count[k] >= 200]
    seams.append({'seam_z': z, 'agreement_at_seam': ag, 'agreement_neighbours_min': min(around) if around else None, 'agreement_neighbours_mean': round(float(np.mean(around)), 4) if around else None,
                  'label_changes_at_seam': ch, 'labels_crossing_seam': crossing, 'identity_kept_fraction': keep, 'identity_voxels_tested': count,
                  'vertebrae_losing_identity_at_seam': renumbered, 'vertebra_renumbering_suspected': bool(renumbered)})
    print('seam', z, 'agreement', ag, 'neighbours', seams[-1]['agreement_neighbours_min'], 'kept', {k: v for k, v in keep.items() if k.startswith('VERT')}, 'renumbered', renumbered, flush=True)
out = {'ct': CT, 'volume': str((D / 'skellytour_high.nii.gz').relative_to(ROOT)), 'crop_ijk': plan['crop'], 'seams': seams,
       'any_vertebra_renumbering_suspected': any(s['vertebra_renumbering_suspected'] for s in seams)}
dest = ROOT / f'generated/skellytour-seams-{CT}.json'
dest.write_text(json.dumps(out, indent=1) + '\n')
print('->', dest.relative_to(ROOT), 'renumbering suspected', out['any_vertebra_renumbering_suspected'])
