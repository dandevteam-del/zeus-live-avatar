#!/usr/bin/env bash
set -x
echo "=== control_server processes ==="
pgrep -af control_server.py | head
echo "=== ctl.log tail (crash?) ==="
tail -15 /workspace/ctl.log 2>/dev/null
echo "=== port 8000 listening? ==="
(ss -ltnp 2>/dev/null||netstat -ltnp 2>/dev/null)|grep :8000|head
echo "=== python syntax check of server ==="
python3 -c "import py_compile,sys; py_compile.compile('/workspace/kit/pod/control_server.py',doraise=True); print('SYNTAX OK')" 2>&1 | tail -3
