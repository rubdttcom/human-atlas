#!/usr/bin/env bash
# Wait for the rgb-only run to write its sentinel, then start rgb-plus-ct-prior on the same GPU.
# The two variants cannot share the RTX 3080 (about 6.5 GB each against 9.6 GB), so they run in order.
# Launched with setsid nohup so it survives the session that started it.
set -uo pipefail
VHF=/media/rub/Backups/VHF
first="$VHF/logs/cryo-train-501.log"
while ! grep -q SENTINEL "$first" 2>/dev/null; do sleep 120; done
if ! grep SENTINEL "$first" | grep -q '"ok": true'; then
  echo "CHAIN-SENTINEL {\"ok\": false, \"error\": \"rgb-only did not finish cleanly; rgb-plus-ct-prior not started\"}"
  exit 1
fi
cd "$VHF" && ./run-cryo-train.sh 502 rgb-plus-ct-prior > logs/cryo-train-502.log 2>&1
echo "CHAIN-SENTINEL $(grep SENTINEL logs/cryo-train-502.log | tail -1)"
