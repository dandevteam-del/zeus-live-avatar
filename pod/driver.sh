#!/usr/bin/env bash
# Server-side editor driver. Edit + push this file; the pod's driver-runner loop
# (in cloud_init.sh) pulls and executes it within ~12s, writing output to
# /workspace/web/driver.out and a fresh /screen.png. xdotool drives the UE editor
# on DISPLAY=:1. Keep each run idempotent and quick.
set -x
export DISPLAY=:1

echo "=== windows (wmctrl) ==="
wmctrl -l 2>/dev/null || echo "wmctrl: none"
echo "=== xdotool search for the UnrealEditor window ==="
WIN=$(xdotool search --name "ZeusAvatar" 2>/dev/null | head -1)
[ -z "$WIN" ] && WIN=$(xdotool search --name "Unreal" 2>/dev/null | head -1)
echo "UE window id: ${WIN:-<none>}"
if [ -n "$WIN" ]; then
  xdotool windowactivate "$WIN" 2>/dev/null
  xdotool getwindowgeometry "$WIN" 2>/dev/null
fi
echo "=== screen size ==="
xdotool getdisplaygeometry 2>/dev/null
echo "probe done"
