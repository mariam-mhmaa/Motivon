#!/usr/bin/env python3

import argparse
import math
import time
from typing import List, Optional

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu


def yaw_from_odometry(message: Odometry) -> float:
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


class ImuYawDirectionMonitor(Node):
    def __init__(self) -> None:
        super().__init__("motivon_imu_yaw_direction_monitor")
        self.angular_z_samples: List[float] = []
        self.first_yaw: Optional[float] = None
        self.last_yaw: Optional[float] = None
        self.create_subscription(
            Imu,
            "/imu/data_raw",
            self._imu_callback,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            Odometry,
            "/odometry/filtered",
            self._odometry_callback,
            qos_profile_sensor_data,
        )

    def _imu_callback(self, message: Imu) -> None:
        value = float(message.angular_velocity.z)
        if math.isfinite(value):
            self.angular_z_samples.append(value)

    def _odometry_callback(self, message: Odometry) -> None:
        yaw = yaw_from_odometry(message)
        if not math.isfinite(yaw):
            return
        if self.first_yaw is None:
            self.first_yaw = yaw
        self.last_yaw = yaw


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Verify that a manual counterclockwise turn produces positive "
            "IMU yaw rate and positive filtered yaw."
        )
    )
    parser.add_argument(
        "--rotate-counterclockwise",
        action="store_true",
        help=(
            "Required confirmation: manually rotate the robot 45-90 degrees "
            "counterclockwise during the measurement window."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.rotate_counterclockwise:
        print(
            "REFUSED: prepare a manual 45-90 degree counterclockwise turn "
            "and add --rotate-counterclockwise"
        )
        return 2

    rclpy.init()
    node = ImuYawDirectionMonitor()
    try:
        print("Keep the robot still for 3 seconds.")
        still_deadline = time.monotonic() + 3.0
        while time.monotonic() < still_deadline:
            rclpy.spin_once(node, timeout_sec=0.05)

        node.angular_z_samples.clear()
        node.first_yaw = node.last_yaw
        print(
            "Now rotate the robot 45-90 degrees COUNTERCLOCKWISE, then "
            "hold it still."
        )
        motion_deadline = time.monotonic() + 8.0
        while time.monotonic() < motion_deadline:
            rclpy.spin_once(node, timeout_sec=0.05)

        if (
            not node.angular_z_samples
            or node.first_yaw is None
            or node.last_yaw is None
        ):
            print("IMU YAW DIRECTION TEST: FAIL (missing data)")
            return 1

        peak_positive_rate = max(node.angular_z_samples)
        yaw_delta = math.atan2(
            math.sin(node.last_yaw - node.first_yaw),
            math.cos(node.last_yaw - node.first_yaw),
        )
        passed = peak_positive_rate >= 0.10 and yaw_delta >= 0.15
        print(f"peak_positive_imu_z: {peak_positive_rate:.3f} rad/s")
        print(
            f"filtered_yaw_change: {math.degrees(yaw_delta):.1f} degrees"
        )
        print(
            "IMU YAW DIRECTION TEST: " + ("PASS" if passed else "FAIL")
        )
        return 0 if passed else 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
