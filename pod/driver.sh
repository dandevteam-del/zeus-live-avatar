#!/usr/bin/env bash
set -x
echo "=== editor process (5.7) alive? ==="
ps -eo pid,etimes,comm,args 2>/dev/null | grep -iE 'UnrealEditor' | grep -v grep | head -2
echo "=== REAL /workspace/ue.log tail (newest activity) ==="
tail -12 /workspace/ue.log 2>/dev/null
echo "=== shader compile progress? ==="
grep -aE 'Using [0-9]+ local workers|Engine is initialized|FlushShaderFileCache|Shaders left' /workspace/ue.log | tail -4
import -window root /workspace/web/screen.png 2>/dev/null
echo "diag done"
