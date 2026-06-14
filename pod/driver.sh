#!/usr/bin/env bash
set -x
export DISPLAY=:1
WORK=/workspace
pkill -f control_server.py 2>/dev/null; sleep 1
nohup env DISPLAY=:1 ZCTL_TOKEN=zeus python3 "$WORK/kit/pod/control_server.py" > "$WORK/ctl.log" 2>&1 &
echo "launched control server pid $!"
# also install a tiny supervisor so a kill self-heals from now on
if ! pgrep -f "ctl-supervisor" >/dev/null 2>&1; then
  nohup bash -c 'exec -a ctl-supervisor bash -c "while true; do pgrep -f control_server.py >/dev/null || (DISPLAY=:1 ZCTL_TOKEN=zeus python3 /workspace/kit/pod/control_server.py >> /workspace/ctl.log 2>&1 &); sleep 5; done"' >/dev/null 2>&1 &
  echo "started ctl-supervisor"
fi
sleep 3
(ss -ltnp 2>/dev/null||netstat -ltnp 2>/dev/null)|grep :8000|head
echo "driver done"
