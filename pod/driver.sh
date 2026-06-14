#!/usr/bin/env bash
set -x
export DISPLAY=:1
echo "=== is an editor process alive right now? ==="
ps -eo pid,etimes,comm,args | grep -iE 'UnrealEditor' | grep -v grep | head
echo "=== is the relaunch loop (cloud_init) alive? ==="
ps -eo pid,args | grep -iE 'cloud_init|while true' | grep -v grep | head
echo "=== REAL ue.log tail (last 25 lines) ==="
tail -25 /workspace/ue.log
echo "=== ue.log last-modified ==="
stat -c '%y' /workspace/ue.log 2>/dev/null
date -u
import -window root /workspace/web/screen.png 2>/dev/null
echo "diag done"
