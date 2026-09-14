#!/usr/bin/env bash
# Resume an interrupted cryosection pilot training from checkpoint_latest.pth, then predict the band slices.
# nnU-Net saves checkpoint_latest every 50 epochs, so a crash costs at most 50 epochs.
# Usage: run-cryo-resume.sh <dataset_id> <variant>
set -uo pipefail
source /media/rub/Backups/VHF/cryo-nnunet-env.sh
D="$1"; VARIANT="$2"
ds=$(ls -d "$nnUNet_raw"/Dataset${D}_* | head -1); name=$(basename "$ds")
ck="$nnUNet_results/$name/nnUNetTrainer__nnUNetPlans__2d/fold_0/checkpoint_latest.pth"
if [ ! -f "$ck" ]; then echo "SENTINEL {\"ok\": false, \"error\": \"no checkpoint_latest.pth for $name\"}"; exit 1; fi
t0=$(date +%s)

"$PY/python" - "$D" <<'PY' 
import sys, random, numpy as np, torch
random.seed(12345); np.random.seed(12345); torch.manual_seed(12345); torch.cuda.manual_seed_all(12345)
from nnunetv2.run.run_training import run_training
run_training(sys.argv[1], '2d', 0, 'nnUNetTrainer', 'nnUNetPlans',
             continue_training=True, device=torch.device('cuda'))
PY
rc=$?
# a crash in nnU-Net's own post-training validation must not discard a finished checkpoint:
# the graded result is the band prediction below, never that validation
if [ -f "$nnUNet_results/$name/nnUNetTrainer__nnUNetPlans__2d/fold_0/checkpoint_final.pth" ]; then rc=0; fi

pred="$VHF/nnunet/pred/$name"
rm -rf "$pred"; mkdir -p "$pred"
"$PY/nnUNetv2_predict" -i "$ds/imagesTs" -o "$pred" -d "$D" -c 2d -f 0 \
    -tr nnUNetTrainer -p nnUNetPlans -chk checkpoint_final.pth --disable_tta || rc=1

python3 - "$rc" "$name" "$VARIANT" "$t0" <<'PY'
import json, os, sys, glob, time
rc, name, variant, t0 = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
pred = os.environ['VHF'] + '/nnunet/pred/' + name
res = glob.glob(os.environ['nnUNet_results'] + f'/{name}/nnUNetTrainer__nnUNetPlans__2d/fold_0/checkpoint_final.pth')
print('SENTINEL ' + json.dumps({'ok': rc == '0' and bool(res), 'resumed': True, 'variant': variant,
                                'dataset': name, 'checkpoint': res[0] if res else None,
                                'predicted_slices': len(glob.glob(pred + '/block2_k*.nii.gz')),
                                'minutes': round((time.time() - t0) / 60, 1)}))
PY
