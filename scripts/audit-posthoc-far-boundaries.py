#!/usr/bin/env python
"""Where are the observable prediction boundaries that the post hoc metric measures as far away?

Reproduces the table of docs/findings-2026-09-20-observable-surface-posthoc.md section 3.3: for one class,
per variant and band, the observable prediction boundary voxels more than 10 mm from any reference boundary
of that class, the reference class under them and the predicted class across the boundary. Reads only
artefacts in the repository; writes nothing. Usage: audit-posthoc-far-boundaries.py [muscle|bone|cartilage]
"""
import json
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cryo_posthoc_surface as PH  # noqa: E402

BLOCK = ROOT / 'data/derived/nlm-vhf/cryosections/block2'
IGN = 255
CLASSES = {'background': 0, 'bone': 1, 'cartilage': 2, 'muscle': 3}
NAMES = {v: k for k, v in CLASSES.items()}
FAR_MM = 10.0


def main():
    cname = sys.argv[1] if len(sys.argv) > 1 else 'muscle'
    cval = CLASSES[cname]
    ref = np.asarray(nib.load(str(BLOCK / 'tissue-classes.nii.gz')).dataobj)
    man = json.loads((BLOCK / 'manifest.json').read_text())
    k0 = man['block']['k_first']
    st = {r['k']: r['status'] for r in man['per_slice']}
    bands = json.loads((ROOT / 'registry/cryo-eval-bands-v1.json').read_text())['bands']
    print(f'class {cname}: observable prediction boundaries farther than {FAR_MM:.0f} mm from any reference {cname} boundary')
    for name in ('rgb-only', 'rgb-plus-ct-prior'):
        pred = np.asarray(nib.load(str(ROOT / f'data/derived/nnunet/pred/pred-block2-{name}.nii.gz')).dataobj)
        for b in bands:
            lo, hi = b['k_first'], b['k_last']
            sl = slice(lo - k0, hi - k0 + 1)
            ok = np.array([st[k] in ('usable', 'usable-flagged') for k in range(lo, hi + 1)])
            r, p = ref[:, :, sl], pred[:, :, sl]
            E = (r != IGN) & ok[None, None, :]
            P, R = p == cval, r == cval
            faces = PH._faces(E.shape)
            sP, sR = PH._surface(P) & ~faces, PH._surface(R) & ~faces
            oP = PH._observable(P, sP, E)
            if not oP.any() or not sR.any():
                print(f'  {name} band {b["band"]}: no observable prediction boundary or no reference boundary'); continue
            d = ndi.distance_transform_edt(~sR, sampling=PH.SPACING)[oP]
            far = oP.copy(); far[oP] = d > FAR_MM
            n = int(far.sum())
            under = {NAMES.get(int(v), int(v)): int(c) for v, c in zip(*np.unique(r[far], return_counts=True))}
            across_mask = ndi.binary_dilation(far, PH.STRUCT6) & ~P
            across = {NAMES.get(int(v), int(v)): int(c) for v, c in zip(*np.unique(p[across_mask], return_counts=True))}
            print(f'  {name} band {b["band"]}: observable {int(oP.sum())}, far {n} ({100.0 * n / oP.sum():.1f} %); '
                  f'reference class under them {under}; predicted class across the boundary {across}')


if __name__ == '__main__':
    main()
