#!/usr/bin/env bash
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
xdotool windowactivate "$WIN" 2>/dev/null
# Clear any open menus.
for i in 1 2 3 4; do xdotool key Escape; sleep 0.2; done
sleep 0.5
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "cleared menus; is a content browser docked?"
