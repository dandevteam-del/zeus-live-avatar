#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
xdotool windowactivate "$WIN" 2>/dev/null; sleep 0.4
xdotool key Escape; sleep 0.3
# Open the Window menu (x=168 y=12) and screenshot it.
xdotool mousemove 168 12 click 1
sleep 1.2
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "opened Window menu"
