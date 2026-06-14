#!/usr/bin/env bash
set -x
export DISPLAY=:1
EP=/home/ue4/UnrealEngine/Engine/Plugins/MetaHuman
echo "=== MetaHumanCharacter precompiled Linux binaries present? ==="
ls -la "$EP/MetaHumanCharacter/Binaries/Linux/" 2>&1 | head
echo "=== its module list (uplugin) ==="
grep -iE '"Name"|"Type"|"LoadingPhase"' "$EP/MetaHumanCharacter/MetaHumanCharacter.uplugin" 2>/dev/null | head -40
echo "=== which MetaHuman plugins HAVE Linux binaries ==="
for d in "$EP"/*/; do
  n=$(basename "$d")
  c=$(ls "$d"Binaries/Linux/*.so 2>/dev/null | wc -l)
  echo "$n: $c .so"
done
echo "=== force-restart editor ==="
ps -eo pid,comm,args | grep -iE 'UnrealEditor|UnrealGame' | grep -v grep | head
pkill -9 -f "UnrealEditor" 2>/dev/null; sleep 1
echo "killed; relaunch loop will restart. waiting 25s to catch fresh log..."
sleep 25
echo "=== fresh log: MetaHumanCharacter mount or failure ==="
tail -400 /workspace/ue.log | grep -iE 'Mounting.*MetaHuman|MetaHumanCharacter|unable to load|missing modules|incompatible' | tail -15
echo "diag done"
