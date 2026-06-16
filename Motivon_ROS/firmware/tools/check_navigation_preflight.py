#!/usr/bin/env python3

import argparse
from dataclasses import dataclass, field
import math
import time
from typing import List, Optional, Tuple

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, JointState

WHEEL_NAMES = {
    "front_left_wheel_joint",
    "front_right_wheel_joint",
    "rear_left_wheel_joint",
    "rear_right_wheel_joint",
}


@dataclass
class StreamStats:
    arrivals: List[float] = field(default_factory=list)

    def record(self) -> None:
        self.arrivals.append(time.monotonic())

    @property
    def rate_hz(self) -> float:
        if len(self.arrivals) < 2:
            return 0.0
        duration = self.arrivals[-1] - self.arrivals[0]
        return (
            (len(self.arrivals) - 1) / duration
            if duration > 0.0
            else 0.0
        )

    @property
    def maximum_gap_s(self) -> float:
        if len(self.arrivals) < 2:
            return math.inf
        return max(
            current - previous
            for previous, current in zip(
                self.arrivals, self.arrivals[1:]
            )
        )


class NavigationPreflight(Node):
    def __init__(self) -> None:
        super().__init__("motivon_navigation_preflight")
        self.wheels = StreamStats()
        self.imu = StreamStats()
        self.filtered = StreamStats()
        self.invalid_messages = 0
        self.first_pose: Optional[Tuple[float, float, float]] = None
        self.last_pose: Optional[Tuple[float, float, float]] = None
        self.create_subscription(
            JointState,
            "/base/wheel_states",
            self._wheel_callback,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            Imu,
            "/imu/data_raw",
            self._imu_callback,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            Odometry,
            "/odometry/filtered",
            self._odom_callback,
            qos_profile_sensor_data,
        )

    def _wheel_callback(self, message: JointState) -> None:
        values = list(message.position) + list(message.velocity)
        valid = (
            len(message.name) == 4
            and set(message.name) == WHEEL_NAMES
            and len(message.position) == 4
            and len(message.velocity) == 4
            and all(math.isfinite(float(value)) for value in values)
        )
        if not valid:
            self.invalid_messages += 1
            return
        self.wheels.record()

    def _imu_callback(self, message: Imu) -> None:
        values = (
            message.angular_velocity.x,
            message.angular_velocity.y,
            message.angular_velocity.z,
        )
        if (
            message.header.frame_id != "base_link"
            or not all(math.isfinite(float(value)) for value in values)
        ):
            self.invalid_messages += 1
            return
        self.imu.record()

    @staticmethod
    def _yaw(message: Odometry) -> float:
        q = message.pose.pose.orientation
        return math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )

    def _odom_callback(self, message: Odometry) -> None:
        pose = (
            float(message.pose.pose.position.x),
            float(message.pose.pose.position.y),
            self._yaw(message),
        )
        if (
            message.header.frame_id != "odom"
            or message.child_frame_id != "base_link"
            or not all(math.isfinite(value) for value in pose)
        ):
            self.invalid_messages += 1
            return
        self.filtered.record()
        if self.first_pose is None:
            self.first_pose = pose
        self.last_pose = pose


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Check stationary base streams and filtered odometry before "
            "navigation."
        )
    )
    parser.add_argument("--duration", type=float, default=20.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.duration < 5.0:
        raise ValueError("--duration must be at least 5 seconds")

    rclpy.init()
    node = NavigationPreflight()
    deadline = time.monotonic() + args.duration
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)

        streams = (
            ("wheel_states", node.wheels, 20.0, 0.15),
            ("imu_raw", node.imu, 20.0, 0.15),
            # Navigation runs at 20 Hz. Requiring 30 Hz gives 50% margin,
            # while the gap limit independently catches unsafe pauses.
            ("odometry_filtered", node.filtered, 30.0, 0.10),
        )
        passed = node.invalid_messages == 0
        for name, stats, minimum_rate, maximum_gap in streams:
            stream_passed = (
                stats.rate_hz >= minimum_rate
                and stats.maximum_gap_s <= maximum_gap
            )
            passed = passed and stream_passed
            print(
                f"{name}: rate={stats.rate_hz:.2f} Hz, "
                f"max_gap={stats.maximum_gap_s:.3f} s, "
                f"{'PASS' if stream_passed else 'FAIL'}"
            )

        if node.first_pose is None or node.last_pose is None:
            position_drift = math.inf
            yaw_drift = math.inf
            drift_passed = False
        else:
            position_drift = math.hypot(
                node.last_pose[0] - node.first_pose[0],
                node.last_pose[1] - node.first_pose[1],
            )
            yaw_drift = abs(
                math.atan2(
                    math.sin(node.last_pose[2] - node.first_pose[2]),
                    math.cos(node.last_pose[2] - node.first_pose[2]),
                )
            )
            drift_passed = position_drift <= 0.03 and yaw_drift <= 0.05
        passed = passed and drift_passed
        print(
            f"stationary_drift: position={position_drift:.4f} m, "
            f"yaw={math.degrees(yaw_drift):.2f} deg, "
            f"{'PASS' if drift_passed else 'FAIL'}"
        )
        print(f"invalid_messages: {node.invalid_messages}")
        print(
            "NAVIGATION PREFLIGHT: " + ("PASS" if passed else "FAIL")
        )
        return 0 if passed else 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
