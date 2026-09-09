#!/usr/bin/env bash
# Stage 1 of plan B: CT priors on Denver's aligned whole-body CT (cryosection frame). RTX 3080 only.
set -euo pipefail
BASE=/media/rub/Backups/VHF
export CUDA_VISIBLE_DEVICES=GPU-c6a8fe2b-851a-a14e-3dff-75aab4818c73
export TMPDIR=$BASE/tmp PIP_CACHE_DIR=$BASE/.pip-cache
D=$BASE/denver
mkdir -p $D/priors/moose/denverct $D/priors/totalseg $BASE/logs
# 1. HU volume: the DICOM stores HU + 1000 as uint16 (air 0, soft tissue ~1000-1060)
$BASE/env/bin/python - <<'PY'
import nibabel as nib, numpy as np
p='/media/rub/Backups/VHF/denver/aligned-ct-nii/denver_aligned_ct.nii.gz'
im=nib.load(p); a=np.asanyarray(im.dataobj).astype(np.int32)-1000
out=nib.Nifti1Image(a.astype(np.int16), im.affine); out.header.set_data_dtype(np.int16)
nib.save(out,'/media/rub/Backups/VHF/denver/aligned-ct-nii/denver_aligned_ct_hu.nii.gz'); print('HU volume written', a.min(), a.max())
PY
cp -n $D/aligned-ct-nii/denver_aligned_ct_hu.nii.gz $D/priors/moose/denverct/CT_denverct.nii.gz || true
sha256sum $D/aligned-ct-nii/denver_aligned_ct_hu.nii.gz | tee $D/priors/input-sha256.txt
# 2. MOOSE bones
source $BASE/env/bin/activate
echo "MOOSE START $(date -Is)"
moosez -d $D/priors/moose -m clin_ct_peripheral_bones clin_ct_all_bones_v1 clin_ct_ribs clin_ct_vertebrae
echo "MOOSE END $(date -Is)"
deactivate
# 3. TotalSegmentator total (own venv)
if [ ! -x $BASE/env-ts/bin/TotalSegmentator ]; then python3 -m venv $BASE/env-ts && $BASE/env-ts/bin/pip install -q -U pip && $BASE/env-ts/bin/pip install -q TotalSegmentator; fi
echo "TS START $(date -Is)"; $BASE/env-ts/bin/TotalSegmentator --version || true
$BASE/env-ts/bin/TotalSegmentator -i $D/aligned-ct-nii/denver_aligned_ct_hu.nii.gz -o $D/priors/totalseg/total.nii.gz --ml -ta total
echo "TS END $(date -Is)"
echo ALL_DONE
