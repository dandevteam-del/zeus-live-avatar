#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
# Confirm the running editor actually loaded MetaHumanCharacter (this boot).
echo "=== MetaHumanCharacter in ue.log (mount/load) ==="
grep -iE "MetaHumanCharacter" /workspace/ue.log | tail -5
echo "=== plugin load failures? ==="
grep -iE "unable to load|incompatible|missing modules" /workspace/ue.log | tail -5
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
echo "win=$WIN"
# Open the Content Drawer (Ctrl+Space) so we can reach the +Add / right-click create menu.
xdotool windowactivate "$WIN" 2>/dev/null
sleep 0.5
xdotool key --window "$WIN" ctrl+space
sleep 1.5
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "opened content drawer"
