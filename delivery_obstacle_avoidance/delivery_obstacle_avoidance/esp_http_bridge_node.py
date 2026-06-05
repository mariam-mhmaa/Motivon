import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class EspHttpBridgeNode(Node):
    """Bridge ROS2 command topics to the ESP web server already in the PID sketch."""

    def __init__(self):
        super().__init__("esp_http_bridge_node")

        self.declare_parameter("esp_base_url", "http://172.20.10.3")
        self.declare_parameter("poll_period_s", 0.10)
        self.declare_parameter("http_timeout_s", 0.35)

        self.esp_base_url = self.get_parameter("esp_base_url").value.rstrip("/")
        self.http_timeout_s = float(self.get_parameter("http_timeout_s").value)

        self.data_pub = self.create_publisher(String, "/esp/data", 10)
        self.status_pub = self.create_publisher(String, "/esp/bridge_status", 10)
        self.motion_command_sub = self.create_subscription(
            String, "/obstacle/motion_command", self.on_motion_command, 10
        )

        poll_period_s = float(self.get_parameter("poll_period_s").value)
        self.create_timer(poll_period_s, self.poll_esp_data)

        self._request_lock = threading.Lock()
        self.get_logger().info(f"ESP HTTP bridge using {self.esp_base_url}")

    def request_text(self, path, query=None):
        if query:
            path = path + "?" + urllib.parse.urlencode(query)

        url = self.esp_base_url + path
        with urllib.request.urlopen(url, timeout=self.http_timeout_s) as response:
            return response.read().decode("utf-8", errors="replace")

    def publish_status(self, ok, action, detail=""):
        msg = String()
        msg.data = json.dumps(
            {
                "ok": ok,
                "action": action,
                "detail": detail,
            }
        )
        self.status_pub.publish(msg)

    def poll_esp_data(self):
        try:
            data = self.request_text("/data")
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            self.publish_status(False, "poll_data", str(exc))
            return

        msg = String()
        msg.data = data
        self.data_pub.publish(msg)

    def on_motion_command(self, msg):
        self.get_logger().warn(f"Received motion command: {msg.data}")
        try:
            command = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.publish_status(False, "parse_command", str(exc))
            return

        command_type = command.get("type")

        try:
            with self._request_lock:
                if command_type == "stop":
                    self.request_text("/stop")
                    self.get_logger().warn("Sent /stop to ESP")
                    self.publish_status(True, "stop")
                elif command_type == "pose":
                    query = {
                        "x": float(command["x"]),
                        "y": float(command["y"]),
                        "yaw": float(command["yaw"]),
                    }
                    self.request_text("/pose", query)
                    self.get_logger().warn(f"Sent /pose to ESP: {query}")
                    self.publish_status(True, "pose", json.dumps(query))
                elif command_type == "zero_pose":
                    self.request_text("/zeroPose")
                    self.publish_status(True, "zero_pose")
                elif command_type == "imu_cal":
                    self.request_text("/imucal")
                    self.publish_status(True, "imu_cal")
                else:
                    self.publish_status(False, "unknown_command", str(command_type))
        except (KeyError, ValueError) as exc:
            self.publish_status(False, "bad_command", str(exc))
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            self.publish_status(False, str(command_type), str(exc))


def main(args=None):
    rclpy.init(args=args)
    node = EspHttpBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
