#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
xdotool windowactivate "$WIN" 2>/dev/null; sleep 0.5
xdotool key Escape; sleep 0.3
xdotool mousemove 70 1068 click 1        # Content Drawer
sleep 1.5
xdotool mousemove 1000 980 click 3       # right-click content area
sleep 1.2
xdotool mousemove 1016 782               # hover MetaHuman category
sleep 1.5
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "hovered MetaHuman category on 5.7"
