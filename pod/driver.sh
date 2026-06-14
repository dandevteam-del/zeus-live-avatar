#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
xdotool windowactivate "$WIN" 2>/dev/null; sleep 0.4
xdotool key Escape; sleep 0.3
xdotool mousemove 168 12 click 1
sleep 1.0
# Hover "Content Browser" (~230,111) to open its submenu, then move into submenu.
xdotool mousemove 230 111
sleep 1.0
xdotool mousemove 360 111
sleep 1.2
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "hovered Content Browser submenu"
