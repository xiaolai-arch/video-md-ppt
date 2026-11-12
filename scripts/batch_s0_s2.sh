#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
SRC="F:/学丞教育视频/就这样过英语四级/第一部分 四级通关必备——基础知识"
LOG="work/logs/batch_s0_s2.log"
: > "$LOG"
for n in 03 04 05 06 07 08 09 10 11 12; do
  f=$(ls "$SRC"/${n}\ *.mp4 2>/dev/null | head -1)
  echo "[$(date +%H:%M:%S)] START $n $(basename "$f")" | tee -a "$LOG"
  python scripts/probe.py "$f"      >> "$LOG" 2>&1; echo "[$(date +%H:%M:%S)] probe=$? $n" | tee -a "$LOG"
  python scripts/transcribe.py "$f" >> "$LOG" 2>&1; echo "[$(date +%H:%M:%S)] transcribe=$? $n" | tee -a "$LOG"
  python scripts/keyframes.py "$f"  >> "$LOG" 2>&1; echo "[$(date +%H:%M:%S)] frames=$? $n" | tee -a "$LOG"
done
echo "[$(date +%H:%M:%S)] BATCH DONE" | tee -a "$LOG"
