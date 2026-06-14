#!/usr/bin/env python3

import argparse
import time
from typing import Dict, Optional

from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool


WHEEL_NAMES = (
    "front_left_wheel_joint",
    "front_right_wheel_joint",
    "rear_left_wheel_joint",
    "rear_right_wheel_joint",
)


class CommandPathTester(Node):
    def __init__(self) -> None:
        super().__init__("motivon_base_command_path_tester")
        self.latest_velocities: Optional[Dict[str, float]] = None
        self.create_subscription(
            JointState,
            "/base/wheel_states",
            self.wheel_callback,
            qos_profile_sensor_data,
        )
        self.cmd_publisher = self.create_publisher(
            Twist, "/cmd_vel", qos_profile_sensor_data
        )
        self.enable_publisher = self.create_publisher(
            Bool, "/base/enable", 10
        )

    def wheel_callback(self, message: JointState) -> None:
        if len(message.name) != len(message.velocity):
            return
        values = dict(zip(message.name, message.velocity))
        if all(name in values for name in WHEEL_NAMES):
            self.latest_velocities = {
                name: float(values[name]) for name in WHEEL_NAMES
            }

    def spin_for(self, duration: float, command: Optional[Twist] = None) -> None:
        deadline = time.monotonic() + duration
        next_publish = 0.0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if command is not None and now >= next_publish:
                self.cmd_publisher.publish(command)
                next_publish = now + 0.1
            rclpy.spin_once(self, timeout_sec=0.02)

    def publish_enable_for(self, enabled: bool, duration: float) -> None:
        message = Bool()
        message.data = enabled
        deadline = time.monotonic() + duration
        next_publish = 0.0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_publish:
                self.enable_publisher.publish(message)
                next_publish = now + 0.1
            rclpy.spin_once(self, timeout_sec=0.02)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Test enable, cmd_vel, wheel response, and watchdog stop."
    )
    parser.add_argument(
        "--wheels-lifted",
        action="store_true",
        help="Required confirmation that every drive wheel is off the floor.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.wheels_lifted:
        print("REFUSED: rerun only after lifting all wheels, with:")
        print("  --wheels-lifted")
        return 2

    rclpy.init()
    node = CommandPathTester()
    command = Twist()
    command.linear.x = 0.05

    try:
        node.spin_for(1.0)
        if node.latest_velocities is None:
            print("COMMAND PATH TEST: FAIL (no wheel telemetry)")
            return 1

        node.publish_enable_for(True, 0.5)
        node.spin_for(2.0, command)
        moving = node.latest_velocities is not None and all(
            velocity > 0.20
            for velocity in node.latest_velocities.values()
        )
        print(
            "forward_response: "
            + ("PASS" if moving else "FAIL")
            + f" {node.latest_velocities}"
        )

        node.spin_for(1.0)
        stopped = node.latest_velocities is not None and all(
            abs(velocity) < 0.20
            for velocity in node.latest_velocities.values()
        )
        print(
            "500_ms_watchdog_stop: "
            + ("PASS" if stopped else "FAIL")
            + f" {node.latest_velocities}"
        )

        passed = moving and stopped
        print("COMMAND PATH TEST: " + ("PASS" if passed else "FAIL"))
        return 0 if passed else 1
    finally:
        node.publish_enable_for(False, 0.3)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
