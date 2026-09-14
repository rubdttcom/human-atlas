#!/usr/bin/env bash
# Train fold 0 of one cryosection pilot variant, then predict the frozen band slices.
# Usage: run-cryo-train.sh <dataset_id> <variant>
#
# A sentinel is printed on EVERY exit path, including a crash and a signal. The first version ran
# `|| exit 1` before the sentinel, and on 2026-09-14 that happened for real: rgb-only finished its
# 1000 epochs and wrote checkpoint_final.pth, then nnU-Net crashed in its own post-training
# validation with "Some background workers are no longer alive", the script exited silently, and
# run-cryo-chain.sh waited for a sentinel that never came. Raised as P2 by the Codex audit of
# 1af1c60 and deferred; it cost an idle GPU. A watcher must never have to distinguish "still
# running" from "died".
set -uo pipefail
source /media/rub/Backups/VHF/cryo-nnunet-env.sh
D="$1"; VARIANT="$2"
ds=$(ls -d "$nnUNet_raw"/Dataset${D}_* | head -1); name=$(basename "$ds")
t0=$(date +%s)
train_rc=1; predict_rc=1; stage='start'

sentinel() {
  local res="$nnUNet_results/$name/nnUNetTrainer__nnUNetPlans__2d/fold_0/checkpoint_final.pth"
  local pred="$VHF/nnunet/pred/$name"
  python3 - "$train_rc" "$predict_rc" "$stage" "$VARIANT" "$name" "$res" "$pred" "$t0" <<'PY'
import json, sys, glob, os, time
tr, pr, stage, variant, name, res, pred, t0 = sys.argv[1:9]
print('SENTINEL ' + json.dumps({
    'ok': tr == '0' and pr == '0', 'stage_reached': stage, 'variant': variant, 'dataset': name,
    'train_rc': int(tr), 'predict_rc': int(pr),
    'checkpoint': res if os.path.exists(res) else None,
    'predicted_slices': len(glob.glob(pred + '/block2_k*.nii.gz')),
    'minutes': round((time.time() - int(t0)) / 60, 1)}), flush=True)
PY
}
trap sentinel EXIT

# The seed is set in the main process only. nnU-Net passes seeds=None to its batch-generator
# workers, so augmentation is not seeded and the run is not bit-reproducible. Recorded as a limit.
"$PY/python" - "$D" <<'PY'
import sys, random, numpy as np, torch
random.seed(12345); np.random.seed(12345); torch.manual_seed(12345); torch.cuda.manual_seed_all(12345)
from nnunetv2.run.run_training import run_training
run_training(sys.argv[1], '2d', 0, 'nnUNetTrainer', 'nnUNetPlans', device=torch.device('cuda'))
PY
train_rc=$?
stage='trained'

# nnU-Net's own post-training validation is not the graded result: the pilot is scored on the frozen
# bands below. A crash there must not discard a finished checkpoint, so it is not fatal here.
if [ ! -f "$nnUNet_results/$name/nnUNetTrainer__nnUNetPlans__2d/fold_0/checkpoint_final.pth" ]; then
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
