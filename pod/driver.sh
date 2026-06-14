#!/usr/bin/env bash
# Server-side editor driver. Edit + push; pod runs within ~12s -> /driver.out + /screen.png.
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
xdotool windowactivate "$WIN" 2>/dev/null; xdotool windowraise "$WIN" 2>/dev/null
sleep 1
# Open the Tools menu (x=237 y=12) and screenshot the open dropdown.
xdotool mousemove 237 12 click 1
sleep 1
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "opened Tools menu"
