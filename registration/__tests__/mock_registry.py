import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

SCENARIO = os.environ["SCENARIO"]
SLUG = os.environ["SLUG"]
LOG = []

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, obj=None):
        b = json.dumps(obj or {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _read(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n).decode() if n else ""

    def _auth_ok(self):
        return self.headers.get("Authorization") == "Bearer good-token"

    def handle_one(self, method):
        body = self._read()
        LOG.append({"m": method, "p": self.path, "body": body})
        if not self._auth_ok():
            return self._send(401, {"error": "Invalid token"})
        p = self.path
        if p == f"/api/v1/app-registry/apps/{SLUG}" and method == "GET":
            if SCENARIO == "fresh":
                return self._send(404, {"error": "not found"})
            # NOTE: pretty-printed WITH a space after the colon — the exact shape
            # that the old no-space grep silently mis-parsed.
            b = json.dumps({"slug": SLUG,
                            "status": "activated" if SCENARIO == "existing-active" else "registered"},
                           indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        if p == "/api/v1/app-registry/apps" and method == "POST":
            try:
                d = json.loads(body)
            except Exception as e:
                return self._send(400, {"error": f"body is not valid JSON: {e}"})
            if "manifest" not in d or not isinstance(d["manifest"], dict):
                return self._send(400, {"error": "missing .manifest object"})
            if d["manifest"].get("slug") != SLUG:
                return self._send(400, {"error": "manifest.slug did not round-trip"})
            return self._send(201, {"slug": SLUG, "status": "registered"})
        if method == "PUT" and p.endswith(f"/apps/{SLUG}"):
            json.loads(body)  # must be the raw manifest, valid JSON
            return self._send(200, {})
        if method == "POST" and p.endswith("/activate"):
            return self._send(200, {"status": "activated"})
        if method == "PUT" and (p.endswith("/policy") or p.endswith("/billing-profile")):
            json.loads(body)
            return self._send(200, {})
        return self._send(404, {"error": "no route"})

    def do_GET(self): self.handle_one("GET")
    def do_POST(self): self.handle_one("POST")
    def do_PUT(self): self.handle_one("PUT")

srv = HTTPServer(("127.0.0.1", int(sys.argv[1])), H)
import threading, signal
def dump(*a):
    open(os.environ["LOGFILE"], "w").write(json.dumps(LOG, indent=1)); os._exit(0)
signal.signal(signal.SIGTERM, dump)
srv.serve_forever()
