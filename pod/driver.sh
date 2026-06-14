#!/usr/bin/env bash
# Server-side editor driver. Edit + push; the pod runs it within ~12s, output ->
# /driver.out, fresh /screen.png. xdotool drives UE on DISPLAY=:1.
set -x
export DISPLAY=:1

echo "=== ALL X windows (id | pid | class | name | geometry) ==="
for w in $(xdotool search --onlyvisible "" 2>/dev/null); do
  nm=$(xdotool getwindowname "$w" 2>/dev/null)
  cl=$(xprop -id "$w" WM_CLASS 2>/dev/null | sed 's/.*= //')
  geo=$(xdotool getwindowgeometry "$w" 2>/dev/null | tr '\n' ' ')
  pid=$(xdotool getwindowpid "$w" 2>/dev/null)
  echo "WIN $w | pid=$pid | class=$cl | name='$nm' | $geo"
done
echo "=== largest window (likely the editor) ==="
BEST=""; BESTA=0
for w in $(xdotool search --onlyvisible "" 2>/dev/null); do
  eval $(xdotool getwindowgeometry --shell "$w" 2>/dev/null)
  a=$(( ${WIDTH:-0} * ${HEIGHT:-0} ))
  if [ "$a" -gt "$BESTA" ]; then BESTA=$a; BEST=$w; fi
done
echo "largest win=$BEST area=$BESTA"
echo "probe2 done"
