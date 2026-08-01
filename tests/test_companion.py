import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from proxitune.companion import CompanionServer


def test_phone_controller_switches_known_zone():
    switched = []
    controller = CompanionServer({"echo": "echo-id", "google": "google-id"}, "secret", switched.append)
    server = ThreadingHTTPServer(("127.0.0.1", 0), controller.make_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        body = json.dumps({"zone": "echo"})
        connection.request(
            "POST", "/zone?token=secret", body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert switched == ["echo-id"]
        assert controller.state.current_zone == "echo"
    finally:
        server.shutdown()
        server.server_close()


def test_phone_controller_rejects_invalid_token():
    controller = CompanionServer({"echo": "echo-id"}, "secret", lambda _: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), controller.make_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request("GET", "/status?token=nope")
        assert connection.getresponse().status == 401
    finally:
        server.shutdown()
        server.server_close()


def test_phone_controller_forwards_media_action():
    actions = []
    controller = CompanionServer({"echo": "echo-id"}, "secret", lambda _: None, lambda action: (actions.append(action) or True))
    server = ThreadingHTTPServer(("127.0.0.1", 0), controller.make_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "POST", "/media?token=secret", body=json.dumps({"action": "next"}),
            headers={"Content-Type": "application/json"},
        )
        assert connection.getresponse().status == 200
        assert actions == ["next"]
    finally:
        server.shutdown()
        server.server_close()


def test_phone_controller_forwards_proximity_readings_to_auto_router():
    class FakeEvent:
        kind = "candidate"
        zone = "echo"
        reason = "test"

    class FakeRouter:
        def __init__(self):
            self.readings = None

        def submit(self, readings):
            self.readings = readings
            return FakeEvent()

    router = FakeRouter()
    controller = CompanionServer({"echo": "echo-id"}, "secret", lambda _: None, auto_router=router)
    server = ThreadingHTTPServer(("127.0.0.1", 0), controller.make_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "POST", "/proximity?token=secret", body=json.dumps({"readings": {"echo": -52, "google": -70}}),
            headers={"Content-Type": "application/json"},
        )
        assert connection.getresponse().status == 200
        assert router.readings == {"echo": -52.0, "google": -70.0}
    finally:
        server.shutdown()
        server.server_close()
