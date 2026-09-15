#!/usr/bin/env bash
# Resume an interrupted cryosection pilot training from checkpoint_latest.pth, then predict the band slices.
# nnU-Net saves checkpoint_latest every 50 epochs, so an interruption costs at most 50 epochs.
# Usage: run-cryo-resume.sh <dataset_id> <variant>
#
# Same sentinel contract as run-cryo-train.sh: a sentinel is printed on EVERY exit path, including a
# crash and a signal. A watcher must never have to distinguish "still running" from "died".
set -uo pipefail
source /media/rub/Backups/VHF/cryo-nnunet-env.sh
D="$1"; VARIANT="$2"
ds=$(ls -d "$nnUNet_raw"/Dataset${D}_* | head -1); name=$(basename "$ds")
model="$nnUNet_results/$name/nnUNetTrainer__nnUNetPlans__2d/fold_0"
t0=$(date +%s)
train_rc=1; predict_rc=1; stage='start'; resumed_from='unknown'

sentinel() {
  local pred="$VHF/nnunet/pred/$name"
  python3 - "$train_rc" "$predict_rc" "$stage" "$VARIANT" "$name" "$model/checkpoint_final.pth" "$pred" "$t0" "$resumed_from" <<'PY'
import json, sys, glob, os, time
tr, pr, stage, variant, name, res, pred, t0, rf = sys.argv[1:10]
print('SENTINEL ' + json.dumps({
    'ok': tr == '0' and pr == '0', 'resumed': True, 'resumed_from_epoch': rf, 'stage_reached': stage,
    'variant': variant, 'dataset': name, 'train_rc': int(tr), 'predict_rc': int(pr),
    'checkpoint': res if os.path.exists(res) else None,
    'predicted_slices': len(glob.glob(pred + '/block2_k*.nii.gz')),
    'minutes': round((time.time() - int(t0)) / 60, 1)}), flush=True)
PY
}
trap sentinel EXIT

if [ ! -f "$model/checkpoint_latest.pth" ]; then
  echo "no checkpoint_latest.pth for $name: nothing to resume" >&2
  exit 1
fi
resumed_from=$("$PY/python" -c "
import torch, sys
print(torch.load(sys.argv[1], map_location='cpu', weights_only=False).get('current_epoch', 'unknown'))
" "$model/checkpoint_latest.pth" 2>/dev/null || echo unknown)
echo "resuming $name from epoch $resumed_from"

"$PY/python" "$VHF/cryo-entry.py" "$D" --mode resume
train_rc=$?
stage='trained'

# nnU-Net's own post-training validation is not the graded result: the pilot is scored on the frozen
# bands below. A crash there must not discard a finished checkpoint.
if [ ! -f "$model/checkpoint_final.pth" ]; then
  echo "no checkpoint_final.pth: training did not finish" >&2
  exit 1
fi
train_rc=0

pred="$VHF/nnunet/pred/$name"
rm -rf "$pred"; mkdir -p "$pred"
"$PY/nnUNetv2_predict" -i "$ds/imagesTs" -o "$pred" -d "$D" -c 2d -f 0 \
    -tr nnUNetTrainer -p nnUNetPlans -chk checkpoint_final.pth --disable_tta
predict_rc=$?
stage='predicted'
exit $predict_rc
