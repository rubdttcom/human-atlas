"""Measure the reference figure of the cartilage required-neighbour term of acceptance protocol version 2.

The protocol compares the median in-plane distance from predicted cartilage to predicted bone (same section) with the
same figure on the reference plus one diagonal pixel. Until the external audit of b02dd3b (2026-09-20) the reference
figure, 1.332 mm, sat in the protocol without a recorded measurement. This script measures it with the frozen metric
module on the frozen block and writes generated/cryo-required-neighbour-reference-block2.json with the hashes of what it
read; scripts/validate-cryo-pilot.py checks that the protocol's reference_median_mm equals this file's figure and that
the file was measured with the pinned metric module. It also reports the figure under the 3D definition the first
implementation used (nearest bone anywhere in the volume) so the two can be compared on the record.

  .venv/bin/python scripts/measure-cryo-required-neighbour.py            # about one minute, writes the JSON

Nothing here is anatomy: a distance between two Denver label classes on one block.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cryo_metrics_v2 as M  # noqa: E402

BLOCK = ROOT / 'data/derived/nlm-vhf/cryosections/block2'
BANDS = ROOT / 'registry/cryo-eval-bands-v1.json'
TMAP = ROOT / 'registry/cryo-tissue-map.json'
OUT = ROOT / 'generated/cryo-required-neighbour-reference-block2.json'
PAIRED = ('usable', 'usable-flagged')


def sha_file(p, chunk=1 << 24):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''):
            h.update(b)
    return h.hexdigest()


def main():
    t0 = time.time()
    man = json.loads((BLOCK / 'manifest.json').read_text())
    bands = json.loads(BANDS.read_text())
    tmap = json.loads(TMAP.read_text())
    values = {c['name']: c['value'] for c in tmap['classes']}
    ref = np.asarray(nib.load(str(BLOCK / 'tissue-classes.nii.gz')).dataobj)
    K = ref.shape[2]
    k_first = man['block']['k_first']
    status = {r['k']: r['status'] for r in man['per_slice']}
    scoring = []
    for b in bands['bands']:
        scoring += [k for k in range(b['k_first'], b['k_last'] + 1) if status[k] in PAIRED]
    elig = np.zeros(K, bool); elig[[k - k_first for k in scoring]] = True
    cart = ref == values['cartilage']; bone = ref == values['bone']
    same_section = M.required_neighbour_distance(cart, bone, elig)
    # the definition the first implementation used, kept for comparison only: 3D EDT, nearest bone anywhere
    src = cart & elig[None, None, :]
    d3 = ndimage.distance_transform_edt(~bone, sampling=M.SPACING)[src]
    per_band = {}
    for b in bands['bands']:
        e = np.zeros(K, bool); e[[k - k_first for k in range(b['k_first'], b['k_last'] + 1) if status[k] in PAIRED]] = True
        per_band['band_%d' % b['band']] = M.required_neighbour_distance(cart, bone, e)
    sections = [int(k) for k in np.flatnonzero((cart & elig[None, None, :]).any(axis=(0, 1))) + k_first]
    out = {
        'id': 'cryo-required-neighbour-reference-block2', 'date': time.strftime('%Y-%m-%d'),
        'definition': 'median in-plane distance (2D EDT per section, 0.666 x 0.666 mm) from every reference cartilage voxel on the scoring slices of both bands to the nearest reference bone voxel of the SAME section, whole slice, blind to ignore; scripts/cryo_metrics_v2.py required_neighbour_distance',
        'reference_same_section': same_section,
        'reference_median_mm': round(same_section['median_mm'], 4),
        'per_band': per_band,
        'cartilage_sections': {'count': len(sections), 'k_first': sections[0], 'k_last': sections[-1]},
        'comparison_3d_nearest_bone_anywhere': {'median_mm': float(np.median(d3)), 'p90_mm': float(np.quantile(d3, 0.9)), 'max_mm': float(d3.max()),
                                                'note': 'the definition of the first implementation (audit finding 2); the median is the same figure on this reference, p90 is not; not used by the protocol'},
        'inputs': {'tissue_classes_volume_sha256': sha_file(BLOCK / 'tissue-classes.nii.gz'), 'rgb_block_manifest_sha256': sha_file(BLOCK / 'manifest.json'),
                   'eval_bands_sha256': sha_file(BANDS), 'tissue_map_sha256': sha_file(TMAP), 'metrics_sha256': sha_file(ROOT / 'scripts/cryo_metrics_v2.py'), 'metrics': 'scripts/cryo_metrics_v2.py'},
        'scoring_slices': len(scoring), 'seconds': round(time.time() - t0, 1),
        'statement': 'a distance between two Denver label classes on one block; not anatomy',
    }
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps({'ok': True, 'out': str(OUT.relative_to(ROOT)), 'reference_median_mm': out['reference_median_mm'], 'median_3d_mm': out['comparison_3d_nearest_bone_anywhere']['median_mm'], 'seconds': out['seconds']}))


if __name__ == '__main__':
    main()
