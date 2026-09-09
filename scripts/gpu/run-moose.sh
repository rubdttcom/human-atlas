#!/usr/bin/env bash
# Run MOOSE bone models on the NLM VHF fresh CT, on the RTX 3080 only.
set -euo pipefail
BASE=/media/rub/Backups/VHF
export CUDA_VISIBLE_DEVICES=GPU-c6a8fe2b-851a-a14e-3dff-75aab4818c73   # RTX 3080; GT 1030 excluded
export TMPDIR=$BASE/tmp
export PIP_CACHE_DIR=$BASE/.pip-cache
MODELS=${MODELS:-"clin_ct_peripheral_bones clin_ct_all_bones_v1 clin_ct_ribs clin_ct_vertebrae"}
IN=$BASE/moose/input
mkdir -p "$IN/vhf" "$BASE/moose/logs"
[ -e "$IN/vhf/CT_vhf.nii.gz" ] || cp "$BASE/nlm-vhf/derived/vhf-fresh-ct.nii.gz" "$IN/vhf/CT_vhf.nii.gz"
sha256sum "$IN/vhf/CT_vhf.nii.gz" | tee "$BASE/moose/logs/input-sha256.txt"
source "$BASE/env/bin/activate"
python - <<'PY'
import torch; assert torch.cuda.is_available(), "no CUDA"
print("GPU:", torch.cuda.get_device_name(0), torch.cuda.device_count(), "device(s) visible")
PY
echo "START $(date -Is)  models: $MODELS"
# shellcheck disable=SC2086
moosez -d "$IN" -m $MODELS
echo "END $(date -Is)"
find "$IN" -name '*.nii*' -newer "$IN/vhf/CT_vhf.nii.gz" | sort
