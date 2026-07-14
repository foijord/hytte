"""Dev server for the viewer: static files + save/reset of building edits.

Usage: python tools/serve.py [port]     (default 8123)

POST   /api/save  — body = full buildings array, written to web/buildings_edited.json
DELETE /api/save  — remove the edited file (viewer falls back to generated buildings.json)
"""
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDITED = os.path.join(ROOT, "web", "buildings_edited.json")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8123


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def _reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/save":
            return self._reply(404, {"error": "unknown endpoint"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            boxes = json.loads(self.rfile.read(n))
            assert isinstance(boxes, list)
        except Exception as e:
            return self._reply(400, {"error": f"bad payload: {e}"})
        with open(EDITED, "w", encoding="utf-8") as f:
            json.dump(boxes, f, indent=1)
        self._reply(200, {"ok": True, "count": len(boxes)})

    def do_DELETE(self):
        if self.path != "/api/save":
            return self._reply(404, {"error": "unknown endpoint"})
        existed = os.path.exists(EDITED)
        if existed:
            os.remove(EDITED)
        self._reply(200, {"ok": True, "removed": existed})


if __name__ == "__main__":
    print(f"serving {ROOT} on http://localhost:{PORT}/")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
