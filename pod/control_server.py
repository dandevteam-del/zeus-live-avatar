#!/usr/bin/env python3
"""Zeus pod control server — low-latency xdotool/screenshot bridge for the UE editor.
Runs on DISPLAY=:1, listens on :8000 (RunPod-proxied -> https://<pod>-8000.proxy.runpod.net/).
Every action returns a FRESH screenshot inline so the caller gets click->verify in one ~1s round-trip.

Endpoints (all accept a ?t=<TOKEN> guard):
  GET  /shot[?region=WxH+X+Y][&scale=PCT]      -> image/png (fresh capture)
  GET  /click?x=&y=&b=1[&n=1]                   -> JSON {ok} then caller can /shot
  GET  /rclick?x=&y=                            -> right click
  GET  /move?x=&y=                              -> move only
  GET  /key?k=ctrl+space                        -> xdotool key
  GET  /type?s=<text>                           -> xdotool type
  GET  /exec?c=<base64 shell>                   -> JSON {rc, out}
  GET  /act?x=&y=&b=1&shot=1                    -> click THEN return png (one round-trip)
  GET  /win                                     -> JSON list of windows
"""
import base64, json, subprocess, os, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("ZCTL_TOKEN", "zeus")
DISPLAY = ":1"
ENV = dict(os.environ, DISPLAY=DISPLAY)

def run(cmd, timeout=30):
    p = subprocess.run(cmd, shell=isinstance(cmd, str), env=ENV,
                       capture_output=True, timeout=timeout)
    return p.returncode, (p.stdout or b"") + (p.stderr or b"")

def shot_png(region=None, scale=None):
    args = ["import", "-window", "root"]
    if region:
        args += ["-crop", region, "+repage"]
    if scale:
        args += ["-resize", f"{scale}%"]
    args += ["png:-"]
    p = subprocess.run(args, env=ENV, capture_output=True, timeout=20)
    return p.stdout

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass
    def _png(self, data):
        self.send_response(200); self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data))); self.end_headers()
        self.wfile.write(data)
    def _json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers()
        self.wfile.write(b)
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        g = lambda k, d=None: (q.get(k, [d])[0])
        if g("t", "zeus") != TOKEN:
            self._json({"ok": False, "err": "bad token"}); return
        path = u.path
        try:
            if path == "/shot":
                self._png(shot_png(g("region"), g("scale"))); return
            if path in ("/click", "/rclick", "/move", "/act"):
                x, y = g("x"), g("y")
                b = g("b", "3" if path == "/rclick" else "1")
                n = g("n", "1")
                if x and y:
                    run(["xdotool", "mousemove", "--sync", str(x), str(y)])
                if path != "/move":
                    run(["xdotool", "click", "--repeat", str(n), str(b)])
                if path == "/act" and g("shot", "1") == "1":
                    import time; time.sleep(float(g("wait", "0.6")))
                    self._png(shot_png(g("region"), g("scale"))); return
                self._json({"ok": True}); return
            if path == "/key":
                run(["xdotool", "key", "--clearmodifiers", g("k", "Escape")])
                self._json({"ok": True}); return
            if path == "/type":
                run(["xdotool", "type", "--clearmodifiers", g("s", "")])
                self._json({"ok": True}); return
            if path == "/exec":
                rc, out = run(base64.b64decode(g("c", "")).decode())
                self._json({"rc": rc, "out": out.decode("utf-8", "replace")[:8000]}); return
            if path == "/win":
                rc, out = run("for w in $(xdotool search --onlyvisible '' 2>/dev/null); do "
                              "echo \"$w|$(xdotool getwindowname $w 2>/dev/null)|"
                              "$(xdotool getwindowgeometry $w 2>/dev/null|tr '\\n' ' ')\"; done")
                self._json({"ok": True, "out": out.decode("utf-8", "replace")}); return
            self._json({"ok": False, "err": "unknown path"})
        except Exception as e:
            self._json({"ok": False, "err": str(e)})

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
