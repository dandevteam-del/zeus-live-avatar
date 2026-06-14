#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
# No windowactivate (it races and dismisses the menu). Editor is the only window.
xdotool mousemove 237 12
sleep 0.3
xdotool click 1
sleep 0.6
# Move cursor INTO the open dropdown to hover-hold it, then shoot.
xdotool mousemove 120 80
sleep 0.6
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "tools click + hover-hold shot"
