#!/usr/bin/env bash
# Skellytour high on whole-body CTs of the VHF donor, RTX 3080 only, 31 GB RAM box.
# v3: targets on the command line (nlm denver), CORE/OV from the environment. Denver (0.72 mm) needs CORE=150 OV=30: its 340-slice chunks hold 96 M voxels and the export worker dies.
# v2 (2026-09-09): Skellytour's own estimate for `high` is 38 GB RAM for a 109 L chunk (v1 died at export).
# Memory scales with volume, so each chunk is cropped in-plane to the body bounding box and limited to
# CORE z slices (+OV overlap on both sides). Chunks run one after another; cores are stitched back onto
# the full grid, so the output is in the CT voxel frame like TotalSegmentator and MOOSE.
set -uo pipefail
BASE=/media/rub/Backups/VHF
export CUDA_VISIBLE_DEVICES=GPU-c6a8fe2b-851a-a14e-3dff-75aab4818c73
export TMPDIR=$BASE/tmp
PY=$BASE/env/bin/python
CORE=${CORE:-260}; OV=${OV:-40}
run_one () {   # $1 input nifti, $2 out dir
  IN=$1; OUT=$2; rm -rf $OUT/chunks; mkdir -p $OUT/chunks
  $PY - "$IN" "$OUT" $CORE $OV <<'PY'
import sys, json, nibabel as nib, numpy as np
from scipy import ndimage
inp, out, core, ov = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
im = nib.load(inp); a = np.asanyarray(im.dataobj)
body = ndimage.binary_opening(a > -500, iterations=2)
lab, n = ndimage.label(body); sizes = np.bincount(lab.ravel())[1:]
body = lab == (np.argmax(sizes) + 1)
proj = body.any(axis=2)
ii = np.where(proj.any(axis=1))[0]; jj = np.where(proj.any(axis=0))[0]
m = 12
i0, i1 = max(ii[0] - m, 0), min(ii[-1] + m + 1, a.shape[0]); j0, j1 = max(jj[0] - m, 0), min(jj[-1] + m + 1, a.shape[1])
nz = a.shape[2]; edges = list(range(0, nz, core)) + [nz]
plan = {'crop': [int(i0), int(i1), int(j0), int(j1)], 'chunks': []}
for c in range(len(edges) - 1):
    z0 = max(edges[c] - ov, 0); z1 = min(edges[c + 1] + ov, nz)
    sub = im.slicer[i0:i1, j0:j1, z0:z1]
    nib.save(sub, f"{out}/chunks/chunk{c}.nii.gz")
    plan['chunks'].append({'chunk': c, 'z0': int(z0), 'z1': int(z1), 'core0': int(edges[c]), 'core1': int(edges[c + 1])})
    print('chunk', c, sub.shape, 'litres %.1f' % (np.prod(sub.shape) * np.prod(im.header.get_zooms()) / 1e6), flush=True)
json.dump(plan, open(f"{out}/chunks/plan.json", 'w'))
print('crop', plan['crop'], 'chunks', len(plan['chunks']), flush=True)
PY
  N=$($PY -c "import json;print(len(json.load(open('$OUT/chunks/plan.json'))['chunks']))")
  for c in $(seq 0 $((N-1))); do
    mkdir -p $OUT/chunks/out$c
    echo "chunk $c start $(date -Is) free $(free -g | awk '/Mem/{print $7}') GB"
    $BASE/env-skelly/bin/skellytour -i $OUT/chunks/chunk$c.nii.gz -o $OUT/chunks/out$c -m high -d gpu -g 0 -c 1 --overwrite 2>&1 | grep -vE "CUDACachingAllocator|^\s*[0-9]+%"
    echo "chunk $c exit ${PIPESTATUS[0]} $(date -Is)"
    rm -f $OUT/chunks/out$c/temp.nii.gz
  done
  # single deterministic fusion with provenance and seam checks; stops on missing or ambiguous chunks
  $PY "$(dirname "$0")/merge-skellytour.py" "$IN" "$OUT" || { echo "MERGE FAILED $(date -Is)"; return 1; }
}
echo "START $(date -Is) CORE=$CORE OV=$OV targets=$*"
STATUS=0
for t in "$@"; do case $t in nlm) run_one $BASE/nlm-vhf/derived/vhf-fresh-ct.nii.gz $BASE/skellytour/nlm || STATUS=1;; denver) run_one $BASE/denver/aligned-ct-nii/denver_aligned_ct_hu.nii.gz $BASE/skellytour/denver || STATUS=1;; esac; done
echo "END $(date -Is) status=$STATUS"
exit $STATUS
