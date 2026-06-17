import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot

try:
    from PySide6.QtWebSockets import QWebSocket
except ImportError:  # pragma: no cover - depends on PySide6 build
    QWebSocket = None


DEFAULT_BRIDGE_URL = os.environ.get(
    "MOTIVON_BRIDGE_URL",
    "http://172.20.10.10:8000",
)


class GuiBridgeClient(QObject):
    status_received = Signal(dict)
    connection_changed = Signal(bool, str)

    def __init__(self, base_url=DEFAULT_BRIDGE_URL, parent=None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.ws_url = self.base_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        ) + "/ws/status"
        self.websocket = None
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_status)

    def start_status_stream(self):
        if QWebSocket is None:
            self.poll_timer.start(500)
            self.connection_changed.emit(False, "WebSocket unavailable; polling.")
            return

        self.websocket = QWebSocket()
        self.websocket.textMessageReceived.connect(self.on_ws_message)
        self.websocket.connected.connect(
            lambda: self.connection_changed.emit(True, "Connected")
        )
        self.websocket.disconnected.connect(self.on_ws_disconnected)
        self.websocket.open(QUrl(self.ws_url))

    @Slot(str)
    def on_ws_message(self, message):
        try:
            self.status_received.emit(json.loads(message))
        except json.JSONDecodeError:
            pass

    def on_ws_disconnected(self):
        self.connection_changed.emit(False, "Disconnected; retrying.")
        QTimer.singleShot(1500, self.start_status_stream)

    def poll_status(self):
        response = self.get("/api/status")
        if response.get("success", True):
            self.status_received.emit(response)

    def get(self, path):
        try:
            with urlopen(self.base_url + path, timeout=2.0) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as error:
            return {"success": False, "message": str(error)}

    def post(self, path, payload=None):
        body = json.dumps(payload or {}).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5.0) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as error:
            return {"success": False, "message": str(error)}

    def start_mission(self, requests):
        payload = {"requests": [self.request_to_payload(req) for req in requests]}
        return self.post("/api/mission/start", payload)

    def cancel_mission(self):
        return self.post("/api/mission/cancel")

    def confirm_manager_verified(self):
        return self.post("/api/mission/confirm-manager-verified")

    def confirm_manager_loaded(self):
        return self.post("/api/mission/confirm-manager-loaded")

    def confirm_user_verified(self):
        return self.post("/api/mission/confirm-user-verified")

    def confirm_user_received(self):
        return self.post("/api/mission/confirm-user-received")

    def set_mode(self, mode):
        return self.post("/api/mode", {"mode": mode})

    def send_manual_command(self, x, y, yaw=0.0):
        return self.post(
            "/api/manual-cmd",
            {"linear_x": x, "linear_y": y, "angular_z": yaw},
        )

    @staticmethod
    def request_to_payload(request):
        return {
            "request_id": request.request_id,
            "user_name": request.user_name,
            "object_requested": request.object_requested,
            "target_station": request.target_station,
        }
