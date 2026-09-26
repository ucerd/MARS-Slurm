#!/usr/bin/env bash
set -euo pipefail
OUT=$1; shift
nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,memory.used,power.draw,temperature.gpu --format=csv -lms 1000 > "$OUT" &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
"$@"; RC=$?
kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true
exit $RC
