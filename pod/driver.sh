#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
xdotool windowactivate "$WIN" 2>/dev/null; xdotool windowraise "$WIN" 2>/dev/null
sleep 1
xdotool mousemove 237 12 click 1
sleep 1
# Crop the open Tools dropdown (left column) at full res, scale 2x for readability.
import -window root -crop 230x340+8+28 +repage -resize 200% "$WEBDIR/toolsmenu.png" 2>/dev/null
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "tools menu cropped -> /toolsmenu.png"
