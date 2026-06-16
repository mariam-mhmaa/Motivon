#!/usr/bin/env python3

import argparse
import math
import time
from typing import Optional, Tuple

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool


class SafeTimedCommand(Node):
    def __init__(self) -> None:
        super().__init__("motivon_safe_timed_command")
        self.wheel_messages = 0
        self.latest_odom: Optional[Tuple[float, float, float]] = None
        self.command_publisher = self.create_publisher(
            Twist, "/cmd_vel", qos_profile_sensor_data
        )
        self.enable_publisher = self.create_publisher(
            Bool, "/base/enable", 10
        )
        self.create_subscription(
            JointState,
            "/base/wheel_states",
            self._wheel_callback,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            Odometry,
            "/wheel/odometry",
            self._odometry_callback,
            qos_profile_sensor_data,
        )

    def wait_for_command_subscribers(self, timeout: float = 8.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if (
                self.command_publisher.get_subscription_count() >= 1
                and self.enable_publisher.get_subscription_count() >= 1
            ):
                return True
        return False

    def _wheel_callback(self, _message: JointState) -> None:
        self.wheel_messages += 1

    @staticmethod
    def _yaw(message: Odometry) -> float:
        quaternion = message.pose.pose.orientation
        return math.atan2(
            2.0
            * (
                quaternion.w * quaternion.z
                + quaternion.x * quaternion.y
            ),
            1.0
            - 2.0
            * (
                quaternion.y * quaternion.y
                + quaternion.z * quaternion.z
            ),
        )

    def _odometry_callback(self, message: Odometry) -> None:
        self.latest_odom = (
            float(message.pose.pose.position.x),
            float(message.pose.pose.position.y),
            self._yaw(message),
        )

    def wait_for_base(self, timeout: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self.wheel_messages >= 5:
                return True
        return False

    def publish_enable(self, enabled: bool, duration: float) -> None:
        message = Bool()
        message.data = enabled
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.enable_publisher.publish(message)
            rclpy.spin_once(self, timeout_sec=0.03)
            time.sleep(0.02)

    def publish_command(self, command: Twist, duration: float) -> None:
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.command_publisher.publish(command)
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.03)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send one short, bounded base command and then disable."
    )
    parser.add_argument("--x", type=float, default=0.0)
    parser.add_argument("--y", type=float, default=0.0)
    parser.add_argument("--wz", type=float, default=0.0)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument(
        "--area-clear",
        action="store_true",
        help="Required confirmation that the motion area is clear.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    values = (args.x, args.y, args.wz, args.duration)
    if not args.area_clear:
        print("REFUSED: clear the area and add --area-clear")
        return 2
    if not all(math.isfinite(value) for value in values):
        raise ValueError("All command values must be finite.")
    if abs(args.x) > 0.05 or abs(args.y) > 0.05:
        raise ValueError("Linear commands are limited to 0.05 m/s.")
    if abs(args.wz) > 0.20:
        raise ValueError("Yaw commands are limited to 0.20 rad/s.")
    if not 0.10 <= args.duration <= 2.0:
        raise ValueError("Duration must be between 0.10 and 2.0 seconds.")
    if abs(args.x) + abs(args.y) + abs(args.wz) == 0.0:
        raise ValueError("At least one command component must be nonzero.")

    rclpy.init()
    node = SafeTimedCommand()
    command = Twist()
    command.linear.x = args.x
    command.linear.y = args.y
    command.angular.z = args.wz
    try:
        if not node.wait_for_base():
            print("SAFE TIMED COMMAND: REFUSED (no wheel telemetry)")
            return 1
        if not node.wait_for_command_subscribers():
            print(
                "SAFE TIMED COMMAND: REFUSED "
                "(ESP command subscriptions not matched)"
            )
            return 1
        if node.latest_odom is None:
            print("SAFE TIMED COMMAND: REFUSED (no wheel odometry)")
            return 1
        start_pose = node.latest_odom
        node.publish_enable(True, 1.0)
        node.publish_command(command, args.duration)
        node.publish_command(Twist(), 0.6)
        end_pose = node.latest_odom
        if end_pose is None:
            print("SAFE TIMED COMMAND: FAIL (wheel odometry disappeared)")
            return 1
        delta_x = end_pose[0] - start_pose[0]
        delta_y = end_pose[1] - start_pose[1]
        delta_yaw = math.atan2(
            math.sin(end_pose[2] - start_pose[2]),
            math.cos(end_pose[2] - start_pose[2]),
        )
        print(
            f"wheel_odometry_delta: x={delta_x:.4f} m, "
            f"y={delta_y:.4f} m, "
            f"yaw={math.degrees(delta_yaw):.2f} deg"
        )
        print("SAFE TIMED COMMAND: COMPLETE")
        return 0
    finally:
        node.publish_command(Twist(), 0.3)
        node.publish_enable(False, 0.3)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
