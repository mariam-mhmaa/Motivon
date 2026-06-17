#!/usr/bin/env python3

from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from motivon_interfaces.msg import ObstacleScan, ObstacleState
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from motivon_obstacles.obstacle_logic import (
    DistanceSet,
    classify_obstacle,
    command_direction,
    finite_distance,
)


class ObstacleManagerNode(Node):
    """Phase-1 ultrasonic obstacle classifier for autonomous navigation."""

    def __init__(self):
        super().__init__("obstacle_manager_node")

        self.declare_parameter("front_blocked_cm", 22.0)
        self.declare_parameter("front_clear_cm", 40.0)
        self.declare_parameter("back_blocked_cm", 22.0)
        self.declare_parameter("back_clear_cm", 40.0)
        self.declare_parameter("side_blocked_cm", 22.0)
        self.declare_parameter("side_clear_cm", 40.0)
        self.declare_parameter("static_wait_s", 10.0)
        self.declare_parameter("sensor_stale_timeout_s", 0.35)
        self.declare_parameter("release_confirm_s", 0.50)
        self.declare_parameter("command_epsilon_mps", 0.02)
        self.declare_parameter("decision_period_s", 0.10)

        self.front_blocked_cm = float(
            self.get_parameter("front_blocked_cm").value
        )
        self.front_clear_cm = float(
            self.get_parameter("front_clear_cm").value
        )
        self.back_blocked_cm = float(
            self.get_parameter("back_blocked_cm").value
        )
        self.back_clear_cm = float(self.get_parameter("back_clear_cm").value)
        self.side_blocked_cm = float(
            self.get_parameter("side_blocked_cm").value
        )
        self.side_clear_cm = float(self.get_parameter("side_clear_cm").value)
        self.static_wait_s = float(self.get_parameter("static_wait_s").value)
        self.sensor_stale_timeout_s = float(
            self.get_parameter("sensor_stale_timeout_s").value
        )
        self.release_confirm_s = float(
            self.get_parameter("release_confirm_s").value
        )
        self.command_epsilon_mps = float(
            self.get_parameter("command_epsilon_mps").value
        )

        self.latest_scan: Optional[ObstacleScan] = None
        self.last_scan_time_s: Optional[float] = None
        self.latest_command = Twist()
        self.blocked_since_s: Optional[float] = None
        self.blocked_direction = ""
        self.release_since_s: Optional[float] = None
        self.last_state = ""

        self.state_pub = self.create_publisher(
            ObstacleState, "/obstacle/state", 10
        )
        self.create_subscription(
            ObstacleScan,
            "/obstacle/scan",
            self.on_scan,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            Twist,
            "/navigation/cmd_vel_raw",
            self.on_navigation_command,
            qos_profile_sensor_data,
        )

        period = float(self.get_parameter("decision_period_s").value)
        self.create_timer(period, self.evaluate)
        self.get_logger().info("Obstacle manager ready for Phase-1 stop/wait/resume.")

    def now_s(self) -> float:
        return self.get_clock().now().nanoseconds / 1_000_000_000.0

    def on_scan(self, msg: ObstacleScan):
        self.latest_scan = msg
        self.last_scan_time_s = self.now_s()

    def on_navigation_command(self, msg: Twist):
        self.latest_command = msg

    def scan_fresh(self, now_s: float) -> bool:
        return (
            self.latest_scan is not None
            and self.last_scan_time_s is not None
            and now_s - self.last_scan_time_s <= self.sensor_stale_timeout_s
        )

    def distances(self) -> DistanceSet:
        scan = self.latest_scan
        if scan is None:
            return DistanceSet()
        return DistanceSet(
            front=finite_distance(scan.front_cm) if scan.front_valid else None,
            back=finite_distance(scan.back_cm) if scan.back_valid else None,
            left=finite_distance(scan.left_cm) if scan.left_valid else None,
            right=finite_distance(scan.right_cm) if scan.right_valid else None,
        )

    def active_direction(self) -> str:
        return command_direction(
            self.latest_command.linear.x,
            self.latest_command.linear.y,
            self.command_epsilon_mps,
        )

    def release_ready(self, now_s: float, decision_direction: str) -> bool:
        if not decision_direction or self.latest_scan is None:
            self.release_since_s = None
            return False
        distances = self.distances()
        clear_thresholds = {
            "front": self.front_clear_cm,
            "back": self.back_clear_cm,
            "left": self.side_clear_cm,
            "right": self.side_clear_cm,
        }
        value = getattr(distances, decision_direction, None)
        threshold = clear_thresholds.get(decision_direction)
        if value is None or threshold is None or value < threshold:
            self.release_since_s = None
            return False
        if self.release_since_s is None:
            self.release_since_s = now_s
            return False
        return now_s - self.release_since_s >= self.release_confirm_s

    def evaluate(self):
        now_s = self.now_s()
        data_valid = self.scan_fresh(now_s)
        active_direction = self.active_direction()
        currently_blocked = self.blocked_since_s is not None
        duration = 0.0
        if self.blocked_since_s is not None:
            duration = now_s - self.blocked_since_s

        direction_for_release = (
            self.blocked_direction if currently_blocked else active_direction
        )
        decision = classify_obstacle(
            data_valid=data_valid,
            active_direction=active_direction,
            distances=self.distances(),
            currently_blocked=currently_blocked,
            blocked_direction=self.blocked_direction,
            blocked_duration_s=duration,
            release_ready=self.release_ready(now_s, direction_for_release),
            static_wait_s=self.static_wait_s,
            front_blocked_cm=self.front_blocked_cm,
            front_clear_cm=self.front_clear_cm,
            back_blocked_cm=self.back_blocked_cm,
            back_clear_cm=self.back_clear_cm,
            side_blocked_cm=self.side_blocked_cm,
            side_clear_cm=self.side_clear_cm,
        )

        if decision.blocked and self.blocked_since_s is None:
            self.blocked_since_s = now_s
            self.blocked_direction = decision.blocked_direction
            self.release_since_s = None
        elif not decision.blocked:
            self.blocked_since_s = None
            self.blocked_direction = ""
            self.release_since_s = None

        self.publish_state(now_s, data_valid, decision)

    def publish_state(self, now_s, data_valid, decision):
        distances = self.distances()
        msg = ObstacleState()
        msg.stamp = self.get_clock().now().to_msg()
        msg.state = decision.state
        msg.data_valid = data_valid
        msg.blocked = decision.blocked
        msg.static_obstacle = decision.static_obstacle
        msg.blocked_direction = decision.blocked_direction
        msg.recommended_detour_side = decision.recommended_detour_side
        msg.front_cm = distances.front if distances.front is not None else float("nan")
        msg.back_cm = distances.back if distances.back is not None else float("nan")
        msg.left_cm = distances.left if distances.left is not None else float("nan")
        msg.right_cm = distances.right if distances.right is not None else float("nan")
        msg.blocked_duration_s = decision.blocked_duration_s
        msg.detail = decision.detail
        self.state_pub.publish(msg)

        if msg.state != self.last_state:
            self.get_logger().warning(
                f"OBSTACLE: {msg.state} | blocked={msg.blocked}, "
                f"direction={msg.blocked_direction}, "
                f"detour={msg.recommended_detour_side}, detail={msg.detail}"
            )
            self.last_state = msg.state


def main(args=None):
    rclpy.init(args=args)
    node = ObstacleManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
