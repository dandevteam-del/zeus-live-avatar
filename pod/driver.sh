#!/usr/bin/env bash
# FIX: Epic's MCP server works on 127.0.0.1:8009 but the container is non-root (ue4)
# so socat couldn't apt-install. Bridge 0.0.0.0:8011 -> 127.0.0.1:8009 with pure
# Python (already present) so the RunPod proxy can reach /mcp. Output -> /driver.out
WORK=/workspace
cat > "$WORK/mcp_bridge.py" <<'PY'
import socket, threading
LISTEN=('0.0.0.0',8011); TARGET=('127.0.0.1',8009)
def pipe(a,b):
    try:
        while True:
            d=a.recv(65536)
            if not d: break
            b.sendall(d)
    except Exception: pass
    finally:
        try: b.shutdown(socket.SHUT_WR)
        except Exception: pass
def handle(c):
    try: s=socket.create_connection(TARGET,timeout=10)
    except Exception: c.close(); return
    threading.Thread(target=pipe,args=(c,s),daemon=True).start()
    threading.Thread(target=pipe,args=(s,c),daemon=True).start()
srv=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
srv.bind(LISTEN); srv.listen(128)
print("mcp_bridge listening",LISTEN,"->",TARGET,flush=True)
while True:
    c,_=srv.accept(); threading.Thread(target=handle,args=(c,),daemon=True).start()
PY
pkill -f mcp_bridge.py 2>/dev/null; sleep 1
nohup python3 "$WORK/mcp_bridge.py" > "$WORK/mcp_bridge.log" 2>&1 &
echo "bridge pid $!"
# self-heal supervisor so the bridge survives a kill / editor relaunch
if ! pgrep -f "mcp-bridge-sup" >/dev/null 2>&1; then
  nohup bash -c 'exec -a mcp-bridge-sup bash -c "while true; do pgrep -f mcp_bridge.py >/dev/null || (nohup python3 /workspace/mcp_bridge.py >>/workspace/mcp_bridge.log 2>&1 &); sleep 5; done"' >/dev/null 2>&1 &
  echo "started mcp-bridge-sup"
fi
sleep 2
echo "----- 8011 listening? -----"
(ss -tlnp 2>/dev/null||netstat -tlnp 2>/dev/null)|grep -E ':8011\b' || echo "8011 NOT listening"
echo "----- local probe 8011/mcp -----"
curl -s -m 8 -o /dev/null -w 'local 127.0.0.1:8011/mcp -> %{http_code}\n' -X POST http://127.0.0.1:8011/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"p","version":"1"}}}'
echo "BRIDGE_FIX_DONE"
