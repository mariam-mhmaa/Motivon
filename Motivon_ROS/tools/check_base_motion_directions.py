#!/usr/bin/env python3

import argparse
import time
from typing import Dict, Optional, Tuple

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
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


class MotionDirectionTester(Node):
    def __init__(self) -> None:
        super().__init__("motivon_base_motion_direction_tester")
        self.wheel_velocities: Optional[Dict[str, float]] = None
        self.odom_twist: Optional[Tuple[float, float, float]] = None
        self.wheel_message_count = 0
        self.cmd_publisher = self.create_publisher(
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
            self._odom_callback,
            qos_profile_sensor_data,
        )

    def wait_for_command_subscribers(self, timeout: float = 8.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if (
                self.cmd_publisher.get_subscription_count() >= 1
                and self.enable_publisher.get_subscription_count() >= 1
            ):
                return True
        return False

    def _wheel_callback(self, message: JointState) -> None:
        if len(message.name) != len(message.velocity):
            return
        values = dict(zip(message.name, message.velocity))
        if all(name in values for name in WHEEL_NAMES):
            self.wheel_velocities = {
                name: float(values[name]) for name in WHEEL_NAMES
            }
            self.wheel_message_count += 1

    def wait_for_wheel_telemetry(self, timeout: float = 10.0) -> bool:
        starting_count = self.wheel_message_count
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self.wheel_message_count - starting_count >= 5:
                return True
        return False

    def _odom_callback(self, message: Odometry) -> None:
        twist = message.twist.twist
        self.odom_twist = (
            float(twist.linear.x),
            float(twist.linear.y),
            float(twist.angular.z),
        )

    def publish_enable(self, enabled: bool, duration: float) -> None:
        message = Bool()
        message.data = enabled
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.enable_publisher.publish(message)
            rclpy.spin_once(self, timeout_sec=0.05)
            time.sleep(0.05)

    def command_for(self, command: Twist, duration: float) -> None:
        deadline = time.monotonic() + duration
        next_publish = 0.0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_publish:
                self.cmd_publisher.publish(command)
                next_publish = now + 0.05
            rclpy.spin_once(self, timeout_sec=0.02)

    def stop_for(self, duration: float = 0.8) -> None:
        self.command_for(Twist(), duration)


def signs_match(
    values: Dict[str, float],
    expected_signs: Tuple[int, int, int, int],
    minimum_speed: float = 0.20,
) -> bool:
    ordered = tuple(values[name] for name in WHEEL_NAMES)
    return all(
        value * sign > minimum_speed
        for value, sign in zip(ordered, expected_signs)
    )


def odom_axis_matches(
    twist: Tuple[float, float, float],
    axis: int,
    minimum_value: float,
) -> bool:
    return twist[axis] > minimum_value


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Verify forward, left-strafe, and counterclockwise wheel signs."
        )
    )
    parser.add_argument(
        "--wheels-lifted",
        action="store_true",
        help="Required confirmation that all four wheels are off the floor.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.wheels_lifted:
        print("REFUSED: lift all four drive wheels and add --wheels-lifted")
        return 2

    tests = (
        (
            "forward",
            (1, 1, 1, 1),
            (0.04, 0.0, 0.0),
            0,
            0.02,
        ),
        (
            "left_strafe",
            (-1, 1, 1, -1),
            (0.0, 0.04, 0.0),
            1,
            0.015,
        ),
        (
            "counterclockwise",
            (-1, 1, -1, 1),
            (0.0, 0.0, 0.15),
            2,
            0.05,
        ),
    )

    rclpy.init()
    node = MotionDirectionTester()
    passed = True
    try:
        print("Waiting for fresh wheel telemetry...")
        if not node.wait_for_wheel_telemetry():
            print(
                "BASE MOTION DIRECTION TEST: FAIL "
                "(no fresh wheel telemetry within 10 seconds)"
            )
            return 1
        print("Fresh wheel telemetry received.")
        print("Waiting for ESP command subscriptions...")
        if not node.wait_for_command_subscribers():
            print(
                "BASE MOTION DIRECTION TEST: FAIL "
                "(ESP command subscriptions not matched)"
            )
            return 1
        print("ESP command subscriptions matched.")
        node.publish_enable(True, 1.0)
        for name, signs, values, odom_axis, minimum_odom in tests:
            command = Twist()
            command.linear.x = values[0]
            command.linear.y = values[1]
            command.angular.z = values[2]
            node.command_for(command, 2.0)

            wheel_passed = (
                node.wheel_velocities is not None
                and signs_match(node.wheel_velocities, signs)
            )
            odom_passed = (
                node.odom_twist is not None
                and odom_axis_matches(
                    node.odom_twist, odom_axis, minimum_odom
                )
            )
            test_passed = wheel_passed and odom_passed
            passed = passed and test_passed
            print(
                f"{name}: wheels={node.wheel_velocities}, "
                f"wheel_odom={node.odom_twist}, "
                f"{'PASS' if test_passed else 'FAIL'}"
            )
            node.stop_for()

        print(
            "BASE MOTION DIRECTION TEST: "
            + ("PASS" if passed else "FAIL")
        )
        return 0 if passed else 1
    finally:
        node.stop_for(0.3)
        node.publish_enable(False, 0.3)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
