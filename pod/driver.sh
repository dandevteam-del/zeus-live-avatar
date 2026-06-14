#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
echo "=== did MetaHumanCharacter modules load this 5.7 boot? ==="
grep -aiE "MetaHumanCharacterEditor|Mounting.*MetaHumanCharacter|LogMetaHumanCharacter" /workspace/ue.log | tail -8
echo "=== plugin enabled in project? ==="
grep -iE "MetaHumanCharacter" /workspace/ZeusAvatar/ZeusAvatar.uproject
# Drive the create menu to look for 'MetaHuman Character'
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
xdotool windowactivate "$WIN" 2>/dev/null; sleep 0.5
xdotool key Escape; sleep 0.3
xdotool mousemove 70 1068 click 1        # Content Drawer
sleep 1.5
xdotool mousemove 1000 980 click 3       # right-click content area
sleep 1.2
xdotool mousemove 1010 735               # hover MetaHuman category (approx)
sleep 1.2
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "create menu opened"
