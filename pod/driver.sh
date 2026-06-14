#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
xdotool windowactivate "$WIN" 2>/dev/null; sleep 0.6
xdotool key Escape; sleep 0.4
# Open Content Drawer
xdotool mousemove 70 1068 click 1
sleep 1.5
# Right-click low in the drawer content area
xdotool mousemove 1000 980 click 3
sleep 1.8
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "drawer + right-click create menu"
