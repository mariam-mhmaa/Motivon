import json
import math

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def finite_distance(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value) or value <= 0.0:
        return None
    return value


class ObstacleDecisionNode(Node):
    """Classify obstacles and command pose-based avoidance through the ESP bridge."""

    def __init__(self):
        super().__init__("obstacle_decision_node")

        self.declare_parameter("dead_zone_cm", 3.0)
        self.declare_parameter("emergency_stop_cm", 25.0)
        self.declare_parameter("front_blocked_cm", 45.0)
        self.declare_parameter("front_clear_cm", 60.0)
        self.declare_parameter("side_clear_cm", 75.0)
        self.declare_parameter("side_emergency_cm", 15.0)
        self.declare_parameter("static_wait_s", 10.0)
        self.declare_parameter("side_offset_m", 0.70)
        self.declare_parameter("pass_distance_m", 0.90)
        self.declare_parameter("pose_tolerance_m", 0.06)
        self.declare_parameter("yaw_tolerance_deg", 6.0)
        self.declare_parameter("decision_period_s", 0.10)
        self.declare_parameter("resume_saved_target", True)

        self.dead_zone_cm = float(self.get_parameter("dead_zone_cm").value)
        self.emergency_stop_cm = float(self.get_parameter("emergency_stop_cm").value)
        self.front_blocked_cm = float(self.get_parameter("front_blocked_cm").value)
        self.front_clear_cm = float(self.get_parameter("front_clear_cm").value)
        self.side_clear_cm = float(self.get_parameter("side_clear_cm").value)
        self.side_emergency_cm = float(self.get_parameter("side_emergency_cm").value)
        self.static_wait_s = float(self.get_parameter("static_wait_s").value)
        self.side_offset_m = float(self.get_parameter("side_offset_m").value)
        self.pass_distance_m = float(self.get_parameter("pass_distance_m").value)
        self.pose_tolerance_m = float(self.get_parameter("pose_tolerance_m").value)
        self.yaw_tolerance_deg = float(self.get_parameter("yaw_tolerance_deg").value)
        self.resume_saved_target = bool(self.get_parameter("resume_saved_target").value)

        self.command_pub = self.create_publisher(String, "/obstacle/motion_command", 10)
        self.state_pub = self.create_publisher(String, "/obstacle/state", 10)
        self.scan_sub = self.create_subscription(String, "/obstacle/scan", self.on_scan, 10)
        self.esp_data_sub = self.create_subscription(String, "/esp/data", self.on_esp_data, 10)

        self.state = "CLEAR"
        self.distances = {}
        self.esp_data = None
        self.blocked_since = None
        self.saved_target = None
        self.saved_pose_mode = False
        self.avoidance_side = None
        self.waypoints = []
        self.waypoint_index = 0
        self.current_waypoint_sent = False
        self.last_stop_command_s = 0.0
        self.last_state_log = None

        period = float(self.get_parameter("decision_period_s").value)
        self.create_timer(period, self.evaluate)
        self.get_logger().info("Obstacle decision node started.")

    def now_s(self):
        return self.get_clock().now().nanoseconds / 1_000_000_000.0

    def publish_command(self, command):
        msg = String()
        msg.data = json.dumps(command)
        self.command_pub.publish(msg)

    def publish_stop(self, reason):
        now = self.now_s()
        if now - self.last_stop_command_s < 0.25:
            return
        self.last_stop_command_s = now
        self.get_logger().warn(f"Publishing STOP command: {reason}")
        self.publish_command({"type": "stop", "reason": reason})

    def publish_state(self, extra=None):
        payload = {
            "state": self.state,
            "front_cm": self.front_distance(),
            "left_cm": self.distance("left"),
            "right_cm": self.distance("right"),
            "avoidance_side": self.avoidance_side,
            "waypoint_index": self.waypoint_index,
            "waypoint_count": len(self.waypoints),
        }
        if self.blocked_since is not None:
            payload["blocked_for_s"] = max(0.0, self.now_s() - self.blocked_since)
        if extra:
            payload.update(extra)

        msg = String()
        msg.data = json.dumps(payload)
        self.state_pub.publish(msg)

    def on_scan(self, msg):
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning("Ignoring malformed /obstacle/scan JSON.")
            return

        distances = payload.get("distances_cm", {})
        self.distances = {key: finite_distance(value) for key, value in distances.items()}

    def on_esp_data(self, msg):
        try:
            self.esp_data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning("Ignoring malformed /esp/data JSON.")

    def distance(self, key):
        value = self.distances.get(key)
        if value is None or value < self.dead_zone_cm:
            return None
        return value

    def front_distance(self):
        center = self.distance("front_center")
        if center is not None:
            return center

        candidates = [
            self.distance("front_left"),
            self.distance("front_right"),
        ]
        candidates = [value for value in candidates if value is not None]
        if not candidates:
            return None
        return min(candidates)

    def is_front_blocked(self):
        front = self.front_distance()
        return front is not None and front < self.front_blocked_cm

    def is_front_clear(self):
        front = self.front_distance()
        return front is None or front > self.front_clear_cm

    def emergency_obstacle(self, keys=None):
        if keys is None:
            keys = ("front_center", "front_left", "front_right", "left", "right")

        for key in keys:
            value = self.distance(key)
            if value is not None and value < self.emergency_stop_cm:
                return key, value
        return None, None

    def choose_avoidance_side(self):
        left = self.distance("left")
        right = self.distance("right")
        front_left = self.distance("front_left")
        front_right = self.distance("front_right")

        left_score = left or 0.0
        right_score = right or 0.0

        if front_left is not None:
            left_score += 0.20 * front_left
        if front_right is not None:
            right_score += 0.20 * front_right

        left_safe = left is not None and left > self.side_clear_cm

        right_safe = right is not None and right > self.side_clear_cm

        if left_safe and right_safe:
            return "left" if left_score >= right_score else "right"
        if left_safe:
            return "left"
        if right_safe:
            return "right"
        return None

    def current_pose(self):
        if not self.esp_data:
            return None

        pose = self.esp_data.get("pose", {})
        try:
            return {
                "x": float(pose["x"]),
                "y": float(pose["y"]),
                "yaw": float(pose["yaw"]),
            }
        except (KeyError, TypeError, ValueError):
            return None

    def remember_current_target(self):
        if not self.esp_data:
            self.saved_target = None
            self.saved_pose_mode = False
            return

        self.saved_pose_mode = bool(self.esp_data.get("poseMode", False))
        target = self.esp_data.get("target", {})
        try:
            self.saved_target = {
                "x": float(target["x"]),
                "y": float(target["y"]),
                "yaw": float(target["yaw"]),
            }
        except (KeyError, TypeError, ValueError):
            self.saved_target = None

    def build_waypoints(self, side):
        pose = self.current_pose()
        if pose is None:
            return None

        x0 = pose["x"]
        y0 = pose["y"]
        yaw = pose["yaw"]
        yaw_rad = math.radians(yaw)

        forward_x = math.cos(yaw_rad)
        forward_y = math.sin(yaw_rad)
        left_x = -math.sin(yaw_rad)
        left_y = math.cos(yaw_rad)
        side_sign = 1.0 if side == "left" else -1.0

        side_dx = side_sign * self.side_offset_m * left_x
        side_dy = side_sign * self.side_offset_m * left_y
        pass_dx = self.pass_distance_m * forward_x
        pass_dy = self.pass_distance_m * forward_y

        return [
            {
                "type": "pose",
                "x": x0 + side_dx,
                "y": y0 + side_dy,
                "yaw": yaw,
                "segment": f"strafe_{side}",
            },
            {
                "type": "pose",
                "x": x0 + side_dx + pass_dx,
                "y": y0 + side_dy + pass_dy,
                "yaw": yaw,
                "segment": "forward",
            },
            {
                "type": "pose",
                "x": x0 + pass_dx,
                "y": y0 + pass_dy,
                "yaw": yaw,
                "segment": f"return_from_{side}",
            },
        ]

    def pose_reached(self, waypoint):
        pose = self.current_pose()
        if pose is None:
            return False

        dx = waypoint["x"] - pose["x"]
        dy = waypoint["y"] - pose["y"]
        position_error = math.hypot(dx, dy)
        yaw_error = abs(self.wrap_deg(waypoint["yaw"] - pose["yaw"]))

        return position_error < self.pose_tolerance_m and yaw_error < self.yaw_tolerance_deg

    @staticmethod
    def wrap_deg(angle):
        while angle > 180.0:
            angle -= 360.0
        while angle < -180.0:
            angle += 360.0
        return angle

    def send_current_waypoint(self):
        waypoint = self.waypoints[self.waypoint_index]
        self.publish_command(
            {
                "type": "pose",
                "x": waypoint["x"],
                "y": waypoint["y"],
                "yaw": waypoint["yaw"],
                "segment": waypoint["segment"],
            }
        )
        self.current_waypoint_sent = True

    def current_segment_unsafe(self):
        if not self.waypoints:
            return None

        segment = self.waypoints[self.waypoint_index]["segment"]
        if segment == "forward":
            front = self.front_distance()
            if front is not None and front < self.front_blocked_cm:
                return f"front blocked during forward segment: {front:.1f} cm"

        if segment == "strafe_left":
            left = self.distance("left")
            if left is not None and left < self.side_emergency_cm:
                return f"left too close during strafe: {left:.1f} cm"

        if segment == "strafe_right":
            right = self.distance("right")
            if right is not None and right < self.side_emergency_cm:
                return f"right too close during strafe: {right:.1f} cm"

        if segment == "return_from_left":
            right = self.distance("right")
            if right is not None and right < self.side_emergency_cm:
                return f"right too close during return strafe: {right:.1f} cm"

        if segment == "return_from_right":
            left = self.distance("left")
            if left is not None and left < self.side_emergency_cm:
                return f"left too close during return strafe: {left:.1f} cm"

        return None

    def resume_original_target(self):
        if self.resume_saved_target and self.saved_pose_mode and self.saved_target:
            self.publish_command(
                {
                    "type": "pose",
                    "x": self.saved_target["x"],
                    "y": self.saved_target["y"],
                    "yaw": self.saved_target["yaw"],
                    "reason": "resume_saved_target",
                }
            )

    def evaluate(self):
        extra = {}

        if self.state == "CLEAR":
            if self.is_front_blocked():
                self.remember_current_target()
                self.publish_stop("front_obstacle")
                self.blocked_since = self.now_s()
                self.state = "WAITING_DYNAMIC"

        elif self.state == "WAITING_DYNAMIC":
            self.publish_stop("waiting_dynamic_front_blocked")
            if self.is_front_clear():
                self.resume_original_target()
                self.state = "CLEAR"
                self.blocked_since = None
            elif self.blocked_since is not None and self.now_s() - self.blocked_since >= self.static_wait_s:
                side = self.choose_avoidance_side()
                if side is None:
                    self.publish_stop("static_obstacle_no_safe_side")
                    extra["reason"] = "no_safe_side"
                else:
                    waypoints = self.build_waypoints(side)
                    if waypoints is None:
                        self.publish_stop("no_esp_pose")
                        extra["reason"] = "waiting_for_esp_pose"
                    else:
                        self.avoidance_side = side
                        self.waypoints = waypoints
                        self.waypoint_index = 0
                        self.current_waypoint_sent = False
                        self.state = "AVOIDING_STATIC"

        elif self.state == "AVOIDING_STATIC":
            key, value = self.emergency_obstacle(keys=("left", "right"))
            if key is not None:
                self.publish_stop(f"emergency_{key}_{value:.1f}_cm")
                self.state = "PAUSED_UNSAFE"
            else:
                unsafe_reason = self.current_segment_unsafe()
                if unsafe_reason:
                    self.publish_stop(unsafe_reason)
                    self.state = "PAUSED_UNSAFE"
                elif not self.current_waypoint_sent:
                    self.send_current_waypoint()
                elif self.pose_reached(self.waypoints[self.waypoint_index]):
                    self.waypoint_index += 1
                    self.current_waypoint_sent = False
                    if self.waypoint_index >= len(self.waypoints):
                        self.resume_original_target()
                        self.state = "CLEAR"
                        self.blocked_since = None
                        self.avoidance_side = None
                        self.waypoints = []
                        self.waypoint_index = 0

        elif self.state == "PAUSED_UNSAFE":
            key, value = self.emergency_obstacle(keys=("left", "right"))
            unsafe_reason = self.current_segment_unsafe()
            if key is None and unsafe_reason is None:
                self.state = "AVOIDING_STATIC"
                self.current_waypoint_sent = False
            else:
                self.publish_stop("paused_unsafe")

        if self.state != self.last_state_log:
            self.get_logger().warn(
                f"Obstacle state -> {self.state}, front={self.front_distance()}, "
                f"left={self.distance('left')}, right={self.distance('right')}"
            )
            self.last_state_log = self.state

        self.publish_state(extra)


def main(args=None):
    rclpy.init(args=args)
    node = ObstacleDecisionNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
