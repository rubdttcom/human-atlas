#!/usr/bin/env bash
# Wait for the rgb-only run to write its sentinel, then start rgb-plus-ct-prior on the same GPU.
# The two variants cannot share the RTX 3080 (about 6.5 GB each against 9.6 GB), so they run in order.
# Launched with setsid nohup so it survives the session that started it.
#
# The wait is bounded. The first version looped on `grep -q SENTINEL` with no deadline, and on
# 2026-09-14 the first run died without printing one, so this watcher waited for hours while the GPU
# sat idle. Raised as P2 by the Codex audit of 1af1c60 and deferred. A watcher that cannot give up
# is a watcher that hides a failure.
set -uo pipefail
VHF=/media/rub/Backups/VHF
first="$VHF/logs/cryo-train-501.log"
DEADLINE_MIN=${CHAIN_DEADLINE_MIN:-1200}          # 20 h; a variant takes about 12.5 h
waited=0
while ! grep -q SENTINEL "$first" 2>/dev/null; do
  if [ "$waited" -ge "$DEADLINE_MIN" ]; then
    echo "CHAIN-SENTINEL {\"ok\": false, \"error\": \"no sentinel from rgb-only after ${DEADLINE_MIN} min; rgb-plus-ct-prior not started\"}"
    exit 1
  fi
  sleep 60; waited=$((waited + 1))
done
if ! grep SENTINEL "$first" | tail -1 | grep -q '"ok": true'; then
  echo "CHAIN-SENTINEL {\"ok\": false, \"error\": \"rgb-only did not finish cleanly; rgb-plus-ct-prior not started\"}"
  exit 1
fi
cd "$VHF" && ./run-cryo-train.sh 502 rgb-plus-ct-prior > logs/cryo-train-502.log 2>&1
echo "CHAIN-SENTINEL $(grep SENTINEL logs/cryo-train-502.log | tail -1)"
