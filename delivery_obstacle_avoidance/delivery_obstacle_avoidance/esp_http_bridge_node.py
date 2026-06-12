import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String


class EspHttpBridgeNode(Node):
    """Bridge ROS2 command topics to the ESP web server already in the PID sketch."""

    def __init__(self):
        super().__init__("esp_http_bridge_node")

        self.declare_parameter("esp_base_url", "http://192.168.1.112")
        self.declare_parameter("poll_period_s", 0.25)
        self.declare_parameter("poll_timeout_s", 0.30)
        self.declare_parameter("command_timeout_s", 0.75)
        self.declare_parameter("stop_heartbeat_s", 1.00)
        self.declare_parameter("status_refresh_s", 10.0)
        self.declare_parameter("poll_failure_backoff_s", 1.0)

        self.esp_base_url = self.get_parameter("esp_base_url").value.rstrip("/")
        self.poll_timeout_s = float(
            self.get_parameter("poll_timeout_s").value
        )
        self.command_timeout_s = float(
            self.get_parameter("command_timeout_s").value
        )
        self.stop_heartbeat_s = float(
            self.get_parameter("stop_heartbeat_s").value
        )
        self.status_refresh_s = float(
            self.get_parameter("status_refresh_s").value
        )
        self.poll_failure_backoff_s = float(
            self.get_parameter("poll_failure_backoff_s").value
        )

        self.data_pub = self.create_publisher(String, "/esp/data", 10)
        self.status_pub = self.create_publisher(String, "/esp/bridge_status", 10)
        self.operator_command_pub = self.create_publisher(
            String,
            "/operator/motion_command",
            10,
        )
        self.command_callback_group = MutuallyExclusiveCallbackGroup()
        self.poll_callback_group = MutuallyExclusiveCallbackGroup()
        self._request_lock = threading.Lock()
        self._command_active = threading.Event()
        self._last_stop_attempt_s = 0.0
        self._poll_suppressed_until_s = 0.0
        self._poll_failure_started_s = None
        self._last_poll_failure_log_s = 0.0
        self._next_poll_attempt_s = 0.0
        self._last_operator_request_id = 0
        self._obstacle_state_lock = threading.Lock()
        self._latest_obstacle_state = None
        self._last_status_signature = None
        self._last_status_push_s = 0.0

        command_qos = QoSProfile(depth=10)
        self.motion_command_sub = self.create_subscription(
            String,
            "/robot/motion_command",
            self.on_motion_command,
            command_qos,
            callback_group=self.command_callback_group,
        )
        self.obstacle_state_sub = self.create_subscription(
            String,
            "/obstacle/state",
            self.on_obstacle_state,
            10,
            callback_group=self.command_callback_group,
        )

        poll_period_s = float(self.get_parameter("poll_period_s").value)
        self.create_timer(
            poll_period_s,
            self.poll_esp_data,
            callback_group=self.poll_callback_group,
        )

        self.get_logger().info(
            f"ESP HTTP bridge using {self.esp_base_url}; "
            f"poll={poll_period_s:.2f}s, "
            f"poll_timeout={self.poll_timeout_s:.2f}s, "
            f"command_timeout={self.command_timeout_s:.2f}s"
        )

    def request_text(self, path, query=None, timeout_s=None):
        query = dict(query or {})
        query["source"] = "ros"
        query["controller"] = "obstacle_supervisor_v2"
        path = path + "?" + urllib.parse.urlencode(query)
        if timeout_s is None:
            timeout_s = self.command_timeout_s

        url = self.esp_base_url + path
        request = urllib.request.Request(
            url,
            headers={
                "Connection": "close",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(
            request,
            timeout=timeout_s,
        ) as response:
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

    def on_obstacle_state(self, msg):
        try:
            state = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        with self._obstacle_state_lock:
            self._latest_obstacle_state = state

    @staticmethod
    def query_distance(value):
        if value is None:
            return ""
        try:
            return f"{float(value):.1f}"
        except (TypeError, ValueError):
            return ""

    def push_obstacle_status_if_due(self):
        with self._obstacle_state_lock:
            state = (
                None
                if self._latest_obstacle_state is None
                else dict(self._latest_obstacle_state)
            )
        if state is None:
            return

        query = {
            "state": str(state.get("state", "")),
            "text": str(state.get("state_text", "")),
            "reason": str(state.get("reason", "")),
            "front": self.query_distance(state.get("front_cm")),
            "left": self.query_distance(state.get("left_cm")),
            "right": self.query_distance(state.get("right_cm")),
            "reset": "1" if state.get("reset_required", False) else "0",
        }
        final_destination = state.get("final_destination") or {}
        query.update(
            {
                "goal_x": self.query_distance(final_destination.get("x")),
                "goal_y": self.query_distance(final_destination.get("y")),
                "goal_yaw": self.query_distance(
                    final_destination.get("yaw")
                ),
            }
        )
        signature = (
            query["state"],
            query["text"],
            query["reason"],
            query["reset"],
            query["goal_x"],
            query["goal_y"],
            query["goal_yaw"],
        )
        now = time.monotonic()
        if (
            signature == self._last_status_signature
            and now - self._last_status_push_s < self.status_refresh_s
        ):
            return

        self.request_text("/rosStatus", query, timeout_s=self.poll_timeout_s)
        self._last_status_signature = signature
        self._last_status_push_s = now

    def forward_gui_operator_request(self, data):
        try:
            payload = json.loads(data)
            request = payload.get("operatorRequest", {})
            request_id = int(request.get("id", 0))
            pending = bool(request.get("pending", False))
        except (json.JSONDecodeError, TypeError, ValueError):
            return

        if (
            not pending
            or request_id <= 0
        ):
            return

        if request_id != self._last_operator_request_id:
            command_type = request.get("type")
            command = {"type": command_type, "source": "gui"}
            if command_type == "pose":
                try:
                    command.update(
                        {
                            "x": float(request["x"]),
                            "y": float(request["y"]),
                            "yaw": float(request["yaw"]),
                        }
                    )
                except (KeyError, TypeError, ValueError):
                    self.publish_status(
                        False,
                        "gui_operator_request",
                        "invalid_pose",
                    )
                    return
            elif command_type not in ("reset_trial", "zero_pose", "imu_cal"):
                self.publish_status(
                    False,
                    "gui_operator_request",
                    f"unsupported_{command_type}",
                )
                return

            self._last_operator_request_id = request_id
            msg = String()
            msg.data = json.dumps(command)
            self.operator_command_pub.publish(msg)
            self.get_logger().warn(
                f"Forwarded GUI operator request #{request_id}: {command_type}"
            )

        self.request_text(
            "/operatorAck",
            {"id": request_id},
            timeout_s=self.poll_timeout_s,
        )

    def service_gui_and_status(self, data):
        if self._command_active.is_set():
            return
        if not self._request_lock.acquire(blocking=False):
            return
        try:
            self.forward_gui_operator_request(data)
            self.push_obstacle_status_if_due()
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            self.get_logger().warning(f"ESP GUI/status relay failed: {exc}")
        finally:
            self._request_lock.release()

    def poll_esp_data(self):
        if (
            self._command_active.is_set()
            or time.monotonic() < self._poll_suppressed_until_s
            or time.monotonic() < self._next_poll_attempt_s
        ):
            return

        if not self._request_lock.acquire(blocking=False):
            return

        try:
            if self._command_active.is_set():
                return
            data = self.request_text(
                "/data",
                timeout_s=self.poll_timeout_s,
            )
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            now = time.monotonic()
            if self._poll_failure_started_s is None:
                self._poll_failure_started_s = now
            self._next_poll_attempt_s = now + self.poll_failure_backoff_s
            if now - self._last_poll_failure_log_s >= 1.0:
                failed_for_s = now - self._poll_failure_started_s
                self.get_logger().error(
                    "ESP telemetry request failed "
                    f"for {failed_for_s:.1f}s: {exc}"
                )
                self._last_poll_failure_log_s = now
            self.publish_status(False, "poll_data", str(exc))
            return
        finally:
            self._request_lock.release()

        if self._poll_failure_started_s is not None:
            failed_for_s = time.monotonic() - self._poll_failure_started_s
            self.get_logger().warn(
                f"ESP telemetry recovered after {failed_for_s:.1f}s."
            )
            self._poll_failure_started_s = None
        self._next_poll_attempt_s = 0.0

        msg = String()
        msg.data = data
        self.data_pub.publish(msg)
        self.service_gui_and_status(data)

    def on_motion_command(self, msg):
        try:
            command = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.publish_status(False, "parse_command", str(exc))
            return

        command_type = command.get("type")
        now = time.monotonic()
        if (
            command_type == "stop"
            and now - self._last_stop_attempt_s < self.stop_heartbeat_s
        ):
            self.publish_status(True, "stop_retry_limited")
            return
        if command_type == "stop":
            self._last_stop_attempt_s = now

        self._command_active.set()
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
                    self._last_stop_attempt_s = 0.0
                    self.get_logger().warn(f"Sent /pose to ESP: {query}")
                    self.publish_status(True, "pose", json.dumps(query))
                elif command_type == "zero_pose":
                    self.request_text("/zeroPose")
                    self.publish_status(True, "zero_pose")
                elif command_type == "imu_cal":
                    self.request_text("/imucal", timeout_s=8.0)
                    self.publish_status(True, "imu_cal")
                else:
                    self.publish_status(False, "unknown_command", str(command_type))
        except (KeyError, ValueError) as exc:
            self.get_logger().error(f"Invalid {command_type} command: {exc}")
            self.publish_status(False, "bad_command", str(exc))
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            self.get_logger().error(
                f"ESP {command_type} request failed: {exc}"
            )
            self.publish_status(False, str(command_type), str(exc))
        finally:
            self._poll_suppressed_until_s = time.monotonic() + 0.50
            self._command_active.clear()


def main(args=None):
    rclpy.init(args=args)
    node = EspHttpBridgeNode()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
