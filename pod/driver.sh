#!/usr/bin/env bash
# Server-side editor driver. Edit + push; pod runs within ~12s -> /driver.out + /screen.png.
set -x
export DISPLAY=:1
WEBDIR=/workspace/web
WIN=$(xdotool search --name "ZeusAvatar - Unreal Editor" 2>/dev/null | head -1)
echo "UE win=$WIN"
xdotool windowactivate "$WIN" 2>/dev/null; xdotool windowraise "$WIN" 2>/dev/null
sleep 1
# Crop the top menu bar (full res) so we can read label x-positions precisely.
import -window root -crop 700x34+0+0 +repage "$WEBDIR/menubar.png" 2>/dev/null
echo "menubar crop saved -> /menubar.png"
# Also a full shot for context
import -window root "$WEBDIR/screen.png" 2>/dev/null
echo "driver done"
