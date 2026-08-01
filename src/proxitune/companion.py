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

    def __init__(self, zone_devices: dict[str, str], token: str, switch: Callable[[str], None], media: Callable[[str], bool] | None = None, auto_router=None) -> None:
        if not token:
            raise ValueError("token must not be empty")
        self.zone_devices = zone_devices
        self.token = token
        self.switch = switch
        self.media = media
        self.auto_router = auto_router
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
                if path == "/media-status":
                    if not self._authorized():
                        self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid token"})
                        return
                    self._json(HTTPStatus.OK, {"available": owner.media is not None})
                    return
                if path == "/auto-status":
                    if not self._authorized():
                        self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid token"})
                        return
                    self._json(HTTPStatus.OK, {"enabled": owner.auto_router is not None})
                    return
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if not self._authorized():
                    self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid request"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length))
                    if path == "/zone":
                        zone = str(payload["zone"])
                        device_id = owner.zone_devices[zone]
                    elif path == "/media":
                        action = str(payload["action"])
                        if owner.media is None:
                            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "media controls are unavailable"})
                            return
                    elif path == "/proximity":
                        if owner.auto_router is None:
                            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "automatic mode is disabled"})
                            return
                        raw_readings = payload["readings"]
                        if not isinstance(raw_readings, dict) or not raw_readings:
                            raise ValueError("readings must be a non-empty object")
                        readings = {str(zone): float(rssi) for zone, rssi in raw_readings.items()}
                    
                    else:
                        raise KeyError(path)
                except (ValueError, KeyError, json.JSONDecodeError):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "expected a known zone"})
                    return
                try:
                    if path == "/zone":
                        owner.switch(device_id)
                        if owner.auto_router is not None:
                            owner.auto_router.set_current(zone)
                    elif path == "/media":
                        if not owner.media(action):
                            raise RuntimeError(f"media action was not accepted: {action}")
                    else:
                        event = owner.auto_router.submit(readings)
                        if event.kind == "switch" and event.zone is not None:
                            owner.state.current_zone = event.zone
                        self._json(HTTPStatus.OK, {"kind": event.kind, "zone": event.zone, "reason": event.reason})
                        return
                except Exception as exc:  # noqa: BLE001 - return useful device error to client
                    with owner._lock:
                        owner.state.last_error = str(exc)
                    self._json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
                    return
                with owner._lock:
                    owner.state.updated_at = time()
                    owner.state.last_error = None
                    if path == "/zone":
                        owner.state.current_zone = zone
                self._json(HTTPStatus.OK, {"zone": zone, "ok": True} if path == "/zone" else {"action": action, "ok": True})

            def _page(self) -> None:
                token = owner.token
                buttons = "".join(
                    f'<button onclick="selectZone(\'{zone}\')">{zone.title()}</button>'
                    for zone in owner.zone_devices
                )
                body = f"""<!doctype html>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ProxiTune</title>
<style>body{{font:18px system-ui;max-width:420px;margin:40px auto;padding:0 20px}}button{{padding:18px;margin:6px;font-size:20px;border-radius:12px;border:1px solid #888;background:#f3f3f3}}.zones button{{display:block;width:100%}}.media{{display:flex;justify-content:center;margin:14px 0}}.media button{{min-width:72px}}#status{{margin-top:24px}}</style>
<h1>ProxiTune</h1><p>Choose the nearest listening zone.</p><div class="zones">{buttons}</div><h2>Media</h2><div class="media"><button onclick="media('previous')">⏮</button><button onclick="media('toggle')">⏯</button><button onclick="media('next')">⏭</button></div><div id="status">Ready</div>
<script>
const token={json.dumps(token)};
async function selectZone(zone){{
  const status=document.getElementById('status'); status.textContent='Switching…';
  const response=await fetch('/zone?token='+encodeURIComponent(token),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{zone}})}});
  const result=await response.json(); status.textContent=response.ok ? 'Playing in '+result.zone : result.error;
}}
async function media(action){{
  const status=document.getElementById('status'); status.textContent='Sending media command…';
  const response=await fetch('/media?token='+encodeURIComponent(token),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{action}})}});
  const result=await response.json(); status.textContent=response.ok ? 'Media command sent' : result.error;
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
        except KeyboardInterrupt:
            print("\nProxiTune phone controller stopped.")
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
    parser.add_argument("--auto", action="store_true", help="enable automatic switching from /proximity readings")
    args = parser.parse_args()
    zone_devices = _load_zone_devices(args.config)
    from .media import MediaController
    auto_router = None
    if args.auto:
        from .auto import AutoRouter
        auto_router = AutoRouter(zone_devices, NativeWindowsSwitcher().set_default)
    CompanionServer(zone_devices, args.token, NativeWindowsSwitcher().set_default, MediaController().control, auto_router).serve(args.host, args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
