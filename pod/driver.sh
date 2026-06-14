#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
xdotool windowactivate "$WIN" 2>/dev/null; sleep 0.4
xdotool key Escape; sleep 0.3
# Window menu -> hover "Content Browser" (2nd item, ~y=71) to open its submenu.
xdotool mousemove 168 12 click 1
sleep 1.0
xdotool mousemove 180 71
sleep 1.5
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "hovered Window>Content Browser submenu"
