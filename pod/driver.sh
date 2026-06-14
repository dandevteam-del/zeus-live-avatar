#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
xdotool windowactivate "$WIN" 2>/dev/null; sleep 0.4
# Re-open content drawer (it dismisses on focus loss), then right-click the empty content area.
xdotool mousemove 70 1068 click 1
sleep 1.2
xdotool mousemove 1200 850 click 3
sleep 1.5
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "right-clicked content area"
