#!/usr/bin/env bash
# Plan and preprocess both cryosection pilot datasets, then install the frozen split.
set -uo pipefail
source /media/rub/Backups/VHF/cryo-nnunet-env.sh
rc=0
for d in 501 502; do
  ds=$(ls -d "$nnUNet_raw"/Dataset${d}_* | head -1); name=$(basename "$ds")
  echo "=== $name ==="
  "$PY/nnUNetv2_plan_and_preprocess" -d "$d" -c 2d --verify_dataset_integrity || rc=1
  # nnU-Net writes its own 5-fold split; replace it with the frozen, spatially blocked one
  mkdir -p "$nnUNet_preprocessed/$name"
  cp "$ds/splits_final.json" "$nnUNet_preprocessed/$name/splits_final.json" || rc=1
  echo "--- frozen split installed for $name ---"
done
python3 - "$rc" <<'PY'
import json, os, sys, glob
pre = os.environ['nnUNet_preprocessed']
out = {}
for p in sorted(glob.glob(pre + '/Dataset*/nnUNetPlans.json')):
    plans = json.load(open(p))
    cfg = plans['configurations']['2d']
    name = os.path.basename(os.path.dirname(p))
    splits = json.load(open(os.path.dirname(p) + '/splits_final.json'))
    med = cfg['median_image_size_in_voxels']
    bad = []
    # the planner must see one slice of 434 x 666, not a stack of one-pixel strips
    if min(cfg['patch_size']) < 32:
        bad.append(f"patch_size {cfg['patch_size']} has a degenerate axis: the slice axis was reordered")
    if sorted(med) != sorted([1.0, 434.0, 666.0]) and sorted(med) != [434.0, 666.0]:
        bad.append(f'median_image_size_in_voxels {med} is not one 434 x 666 slice')
    if len(splits) != 4 or len(splits[0]['train']) != 187 or len(splits[0]['val']) != 10:
        bad.append(f"frozen split not installed: {len(splits)} folds, fold 0 = {len(splits[0]['train'])}/{len(splits[0]['val'])}")
    out[name] = {'patch_size': cfg['patch_size'], 'batch_size': cfg['batch_size'],
                 'spacing': cfg['spacing'], 'median_image_size': med, 'norm': cfg['normalization_schemes'],
                 'folds': len(splits), 'fold0_train': len(splits[0]['train']), 'fold0_val': len(splits[0]['val']),
                 'problems': bad}
ok = sys.argv[1] == '0' and bool(out) and not any(v['problems'] for v in out.values())
print('SENTINEL ' + json.dumps({'ok': ok, 'plans': out}))
PY
