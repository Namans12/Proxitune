"""Local phone companion for manual zone selection.

The server intentionally uses only the Python standard library. A phone on the
same Wi-Fi network can open the small control page and send a signed-by-token
zone selection to the Windows agent.
"""

from __future__ import annotations

import argparse
import json
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import time
from typing import Callable
from urllib.parse import parse_qs, urlparse

from .audio import NativeWindowsSwitcher


@dataclass
class CompanionState:
    current_zone: str | None = None
    updated_at: float | None = None
    last_error: str | None = None


class CompanionServer:
    """Authenticated local HTTP controller for manual zone changes."""

    def __init__(self, zone_devices: dict[str, str], token: str, switch: Callable[[str], None]) -> None:
        if not token:
            raise ValueError("token must not be empty")
        self.zone_devices = zone_devices
        self.token = token
        self.switch = switch
        self.state = CompanionState()
        self._lock = threading.Lock()

    def make_handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args) -> None:  # noqa: A002
                return

            def _authorized(self) -> bool:
                query_token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
                header = self.headers.get("Authorization", "")
                return query_token == owner.token or header == f"Bearer {owner.token}"

            def _json(self, status: HTTPStatus, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path == "/" or path == "/control":
                    if not self._authorized():
                        self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid token"})
                        return
                    self._page()
                    return
                if path == "/status":
                    if not self._authorized():
                        self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid token"})
                        return
                    with owner._lock:
                        self._json(HTTPStatus.OK, owner.state.__dict__.copy())
                    return
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                if urlparse(self.path).path != "/zone" or not self._authorized():
                    self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid request"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length))
                    zone = str(payload["zone"])
                    device_id = owner.zone_devices[zone]
                except (ValueError, KeyError, json.JSONDecodeError):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "expected a known zone"})
                    return
                try:
                    owner.switch(device_id)
                except Exception as exc:  # noqa: BLE001 - return useful device error to client
                    with owner._lock:
                        owner.state.last_error = str(exc)
                    self._json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
                    return
                with owner._lock:
                    owner.state.current_zone = zone
                    owner.state.updated_at = time()
                    owner.state.last_error = None
                self._json(HTTPStatus.OK, {"zone": zone, "ok": True})

            def _page(self) -> None:
                token = owner.token
                buttons = "".join(
                    f'<button onclick="selectZone(\'{zone}\')">{zone.title()}</button>'
                    for zone in owner.zone_devices
                )
                body = f"""<!doctype html>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ProxiTune</title>
<style>body{{font:18px system-ui;max-width:420px;margin:40px auto;padding:0 20px}}button{{display:block;width:100%;padding:18px;margin:12px 0;font-size:20px;border-radius:12px;border:1px solid #888;background:#f3f3f3}}#status{{margin-top:24px}}</style>
<h1>ProxiTune</h1><p>Choose the nearest listening zone.</p>{buttons}<div id="status">Ready</div>
<script>
const token={json.dumps(token)};
async function selectZone(zone){{
  const status=document.getElementById('status'); status.textContent='Switching…';
  const response=await fetch('/zone?token='+encodeURIComponent(token),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{zone}})}});
  const result=await response.json(); status.textContent=response.ok ? 'Playing in '+result.zone : result.error;
}}
</script>""".encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def serve(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        server = ThreadingHTTPServer((host, port), self.make_handler())
        print(f"ProxiTune phone controller: http://<this-PC-IP>:{port}/?token={self.token}")
        try:
            server.serve_forever()
        finally:
            server.server_close()


def _load_zone_devices(path: str) -> dict[str, str]:
    with open(path, encoding="utf-8") as handle:
        config = json.load(handle)
    return {zone: details["audio_device_id"] for zone, details in config["zones"].items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the ProxiTune phone controller")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--token", required=True, help="shared token used by the phone page")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    zone_devices = _load_zone_devices(args.config)
    CompanionServer(zone_devices, args.token, NativeWindowsSwitcher().set_default).serve(args.host, args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
