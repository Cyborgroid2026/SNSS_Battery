"""브라우저 속 Blender — 서버 (snss_battery/bldesign.py serve_web 가 부름).

blender -b cad_out/blender/SNSS_Design.blend --python blender/serve_web.py -- [--port 8790] [--host 127.0.0.1]
→ http://127.0.0.1:8790/  (VS Code: Ctrl+Shift+P → 'Browser: Open Integrated Browser' 에 붙여 넣기)
"""

import json
import queue
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from snss_design import web  # noqa: E402

JOBS: "queue.Queue" = queue.Queue()


def on_main(fn, *a, **kw):
    """bpy 는 주 실에서만 — 일을 줄에 넣고 끝날 때까지 기다림."""
    ev, box = threading.Event(), {}
    JOBS.put((fn, a, kw, ev, box))
    ev.wait()
    if "err" in box:
        raise box["err"]
    return box["out"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype: str, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", code)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/info":
                return self._json(on_main(web.info))
            if u.path == "/api/geom":
                return self._send(on_main(web.geometry, q["scene"]), "application/octet-stream")
            if u.path == "/api/frame":
                return self._json(on_main(web.frame, q["scene"]))
            if u.path == "/api/meta":
                return self._json(on_main(web.meta_get, q["object"]))
            if u.path == "/api/check":
                return self._json(on_main(web.run_check, q["scene"]))
            if u.path == "/api/process":
                return self._json(on_main(web.process_get))
            if u.path == "/api/log":
                return self._json(on_main(web.log))
            body, ctype = web.static(unquote(u.path))
            if body is not None:
                return self._send(body, ctype)
            self._json({"error": "없음"}, 404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._json({"error": str(e)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        b = json.loads(self.rfile.read(n) or b"{}")
        try:
            if u.path == "/api/set":
                return self._json(on_main(web.set_dim, b["scene"], b["key"], b["value"]))
            if u.path == "/api/meta":
                return self._json(on_main(web.meta_set, b["object"], int(b.get("i", 0)), co=b.get("co"), r=b.get("r"),
                                          size=b.get("size"), add=b.get("add"), remove=bool(b.get("remove"))))
            if u.path == "/api/send":
                return self._json(on_main(web.send, b["machine"], b.get("object")))
            if u.path == "/api/hw":
                return self._json(on_main(web.hw, b.pop("scene"), b.pop("action"), **b))
            if u.path == "/api/render":
                png = on_main(web.render, b["scene"], b["eye"], b["target"], b.get("fov", 40), b.get("w", 960), b.get("h", 640),
                              b.get("engine", "BLENDER_EEVEE"))
                return self._send(png, "image/png")
            if u.path == "/api/process":
                return self._json(on_main(web.process_set, b["op"], b["step"], b.get("to")))
            if u.path == "/api/save":
                return self._json(on_main(web.save))
            self._json({"error": "없음"}, 404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._json({"error": str(e)}, 500)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 8790
    host = argv[argv.index("--host") + 1] if "--host" in argv else "127.0.0.1"
    srv = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"브라우저 속 Blender: http://{host}:{port}/  (VS Code: Browser: Open Integrated Browser) — 멈추려면 Ctrl+C", flush=True)
    while True:
        try:
            fn, a, kw, ev, box = JOBS.get(timeout=0.1)
        except queue.Empty:
            continue
        except KeyboardInterrupt:
            break
        try:
            box["out"] = fn(*a, **kw)
        except Exception as e:  # noqa: BLE001
            box["err"] = e
        ev.set()
    srv.shutdown()


main()
