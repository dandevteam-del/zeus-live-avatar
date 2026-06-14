#!/usr/bin/env bash
# Launch the fast control server now (no reboot needed).
set -x
export DISPLAY=:1
WORK=/workspace
if pgrep -f control_server.py >/dev/null 2>&1; then
  echo "control server already running"
else
  cd "$WORK/kit/pod"
  nohup env DISPLAY=:1 ZCTL_TOKEN=zeus python3 "$WORK/kit/pod/control_server.py" > "$WORK/ctl.log" 2>&1 &
  echo "launched control server pid $! -> :8000"
fi
sleep 3
echo "=== ctl.log ==="; tail -5 "$WORK/ctl.log" 2>/dev/null
echo "=== listening on 8000? ==="; (ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null) | grep ':8000' | head
echo "=== self-test /shot locally ==="
python3 - <<'PY' 2>&1 | head
import urllib.request
try:
    d=urllib.request.urlopen("http://127.0.0.1:8000/shot?t=zeus",timeout=10).read()
    print("local /shot bytes:", len(d))
except Exception as e:
    print("ERR", e)
PY
echo "driver done"
