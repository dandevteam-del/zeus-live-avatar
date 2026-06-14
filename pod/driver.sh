#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
xdotool windowactivate "$WIN" 2>/dev/null; sleep 0.4
# Click the "Content Drawer" button at the very bottom-left of the status bar.
xdotool mousemove 70 1068 click 1
sleep 1.5
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "clicked Content Drawer (70,1068)"
