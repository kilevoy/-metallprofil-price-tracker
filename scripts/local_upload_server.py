from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "input"
UPDATE_SCRIPT = ROOT / "scripts" / "update_sandwich_panels.py"
HOST = "127.0.0.1"
PORT = 8765


def sanitize_filename(name: str) -> str:
    candidate = Path(name).name.strip().replace("\x00", "")
    if not candidate:
        candidate = f"price-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
    if not candidate.lower().endswith(".pdf"):
        candidate = f"{candidate}.pdf"
    return candidate


def resolve_target_path(file_name: str) -> Path:
    target = INPUT_DIR / file_name
    if not target.exists():
        return target
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return INPUT_DIR / f"{target.stem}-{stamp}{target.suffix}"


class LocalUploadHandler(BaseHTTPRequestHandler):
    server_version = "LocalUploadServer/1.0"

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self._json(
                {
                    "ok": True,
                    "message": "Local upload server is running",
                    "input_dir": str(INPUT_DIR),
                }
            )
            return
        self._json({"ok": False, "error": "Not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/upload":
            self._handle_upload(parsed)
            return
        if parsed.path == "/api/process":
            self._handle_process()
            return
        self._json({"ok": False, "error": "Not found"}, status=404)

    def _handle_upload(self, parsed) -> None:
        params = parse_qs(parsed.query)
        raw_name = params.get("name", ["uploaded-price.pdf"])[0]
        file_name = sanitize_filename(raw_name)

        try:
            content_len = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_len = 0

        if content_len <= 0:
            self._json({"ok": False, "error": "Empty request body"}, status=400)
            return

        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        target = resolve_target_path(file_name)
        data = self.rfile.read(content_len)

        if not data:
            self._json({"ok": False, "error": "Empty PDF data"}, status=400)
            return

        target.write_bytes(data)
        self._json(
            {
                "ok": True,
                "saved_as": target.name,
                "bytes": len(data),
            }
        )

    def _handle_process(self) -> None:
        try:
            proc = subprocess.run(
                [sys.executable, str(UPDATE_SCRIPT)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, status=500)
            return

        if proc.returncode != 0:
            self._json(
                {
                    "ok": False,
                    "error": "Parser failed",
                    "stdout": proc.stdout[-2000:],
                    "stderr": proc.stderr[-2000:],
                },
                status=500,
            )
            return

        self._json(
            {
                "ok": True,
                "message": "Parser completed",
                "stdout": proc.stdout[-2000:],
            }
        )


def main() -> None:
    print(f"[INFO] Local upload server: http://{HOST}:{PORT}")
    print(f"[INFO] Input folder: {INPUT_DIR}")
    print("[INFO] Endpoints: GET /api/status, POST /api/upload?name=..., POST /api/process")
    server = ThreadingHTTPServer((HOST, PORT), LocalUploadHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("\n[INFO] Server stopped.")


if __name__ == "__main__":
    main()

