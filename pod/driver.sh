#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
xdotool windowactivate "$WIN" 2>/dev/null; xdotool windowraise "$WIN" 2>/dev/null
sleep 1
xdotool mousemove 237 12 click 1
sleep 1
# single full-res shot WHILE menu is open; crop locally
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "tools menu open, full shot saved"
