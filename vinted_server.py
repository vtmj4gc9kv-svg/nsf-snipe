"""Local web server for the NSF Snipebot phone app (standard library only)."""
import json, os, secrets, socket, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DIR = Path(__file__).parent
HITS_FILE, KEY_FILE = DIR / "hits.json", DIR / "app_key.txt"
state = {"category": None, "last_check": None, "scanning": None}
_lock = threading.Lock()


def get_key():
    if os.environ.get("APP_KEY"):
        return os.environ["APP_KEY"].strip()
    if not KEY_FILE.exists():
        KEY_FILE.write_text(secrets.token_urlsafe(12))
    return KEY_FILE.read_text().strip()


def _hits():
    try:
        return json.loads(HITS_FILE.read_text())
    except Exception:
        return []


def add_hit(hit):
    with _lock:
        hits = _hits()
        hits.insert(0, {**hit, "ts": int(time.time())})
        HITS_FILE.write_text(json.dumps(hits[:600]))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _auth(self):
        q = parse_qs(urlparse(self.path).query)
        return q.get("k", [""])[0] == get_key()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self._send(200, (DIR / "app.html").read_bytes(), "text/html")
        if not self._auth():
            return self._send(401, "{}")
        if path == "/api/state":
            return self._send(200, json.dumps({"state": state, "hits": _hits()}))
        self._send(404, "{}")

    def do_POST(self):
        if not self._auth():
            return self._send(401, "{}")
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if urlparse(self.path).path == "/api/category":
            cat = body.get("category")
            state["category"] = cat if cat in ("clothing", "accessories") else None
        self._send(200, "{}")


def start(port=None):
    port = port or int(os.environ.get("PORT", 8765))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
    except Exception:
        ip = "localhost"
    print(f"NSF Snipebot app: http://{ip}:{port}/?k={get_key()}")
