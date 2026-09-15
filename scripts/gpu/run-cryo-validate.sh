#!/usr/bin/env bash
set -uo pipefail
source /media/rub/Backups/VHF/cryo-nnunet-env.sh
D="$1"; VARIANT="$2"
ds=$(ls -d "$nnUNet_raw"/Dataset${D}_* | head -1); name=$(basename "$ds")
model="$nnUNet_results/$name/nnUNetTrainer__nnUNetPlans__2d/fold_0"
t0=$(date +%s)
val_rc=1; stage='start'

sentinel() {
  python3 - "$val_rc" "$stage" "$VARIANT" "$name" "$model/validation/summary.json" "$t0" <<'PY'
import json, sys, os, time
rc, stage, variant, name, summary, t0 = sys.argv[1:7]
mean = None
if os.path.exists(summary):
    with open(summary) as fh:
        mean = json.load(fh).get('foreground_mean')
print('SENTINEL ' + json.dumps({
    'ok': rc == '0' and mean is not None, 'stage_reached': stage, 'variant': variant,
    'dataset': name, 'val_rc': int(rc), 'foreground_mean': mean,
    'minutes': round((time.time() - int(t0)) / 60, 1)}), flush=True)
PY
}
trap sentinel EXIT

if [ ! -f "$model/checkpoint_final.pth" ]; then
  echo "no checkpoint_final.pth for $name: nothing to validate" >&2
  exit 1
fi

# A previous hung attempt leaves an empty validation/; nnU-Net is happy to refill it.
"$PY/python" "$VHF/cryo-entry.py" "$D" --mode validate
val_rc=$?
stage='validated'
exit $val_rc
