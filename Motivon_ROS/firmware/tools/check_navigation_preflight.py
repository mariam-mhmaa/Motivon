#!/usr/bin/env python3

import argparse
from dataclasses import dataclass, field
import math
import threading
import time
from typing import List, Optional, Tuple

import rclpy
from rclpy.executors import MultiThreadedExecutor
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

    def copy(self) -> "StreamStats":
        return StreamStats(arrivals=list(self.arrivals))

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

    def excessive_gaps(self, measurement_start: float, limit_s: float):
        return [
            (current - measurement_start, current - previous)
            for previous, current in zip(
                self.arrivals, self.arrivals[1:]
            )
            if current - previous > limit_s
        ]


class NavigationPreflight(Node):
    def __init__(self) -> None:
        super().__init__("motivon_navigation_preflight")
        self.data_lock = threading.Lock()
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
            with self.data_lock:
                self.invalid_messages += 1
            return
        with self.data_lock:
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
            with self.data_lock:
                self.invalid_messages += 1
            return
        with self.data_lock:
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
            with self.data_lock:
                self.invalid_messages += 1
            return
        with self.data_lock:
            self.filtered.record()
            if self.first_pose is None:
                self.first_pose = pose
            self.last_pose = pose

    def ready(self) -> bool:
        discovered_nodes = set(self.get_node_names())
        with self.data_lock:
            return (
                "esp32_base_node" in discovered_nodes
                and "wheel_odometry_node" in discovered_nodes
                and "ekf_filter_node" in discovered_nodes
                and len(self.wheels.arrivals) >= 10
                and len(self.imu.arrivals) >= 10
                and len(self.filtered.arrivals) >= 10
            )

    def reset_measurement(self) -> None:
        with self.data_lock:
            self.wheels = StreamStats()
            self.imu = StreamStats()
            self.filtered = StreamStats()
            self.invalid_messages = 0
            self.first_pose = None
            self.last_pose = None

    def snapshot(self):
        with self.data_lock:
            return (
                self.wheels.copy(),
                self.imu.copy(),
                self.filtered.copy(),
                self.invalid_messages,
                self.first_pose,
                self.last_pose,
            )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Check stationary base streams and filtered odometry before "
            "navigation."
        )
    )
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--ready-timeout", type=float, default=20.0)
    parser.add_argument(
        "--settle-time",
        type=float,
        default=5.0,
        help="Seconds to let EKF/gyro settle after streams are ready.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.duration < 5.0:
        raise ValueError("--duration must be at least 5 seconds")
    if args.ready_timeout <= 0.0:
        raise ValueError("--ready-timeout must be positive")
    if args.settle_time < 0.0:
        raise ValueError("--settle-time must be non-negative")

    rclpy.init()
    node = NavigationPreflight()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()
    try:
        print(
            "Waiting for ESP, wheel odometry, and EKF streams before "
            "starting the timed preflight..."
        )
        ready_deadline = time.monotonic() + args.ready_timeout
        while time.monotonic() < ready_deadline and not node.ready():
            time.sleep(0.05)
        if not node.ready():
            print("NAVIGATION PREFLIGHT: FAIL (session not ready)")
            return 1

        if args.settle_time > 0.0:
            print(
                f"Streams ready. Letting localization settle for "
                f"{args.settle_time:.1f} seconds."
            )
            time.sleep(args.settle_time)

        node.reset_measurement()
        measurement_start = time.monotonic()
        deadline = measurement_start + args.duration
        print(f"Session ready. Measuring for {args.duration:.1f} seconds.")
        while time.monotonic() < deadline:
            time.sleep(0.05)

        (
            wheels,
            imu,
            filtered,
            invalid_messages,
            first_pose,
            last_pose,
        ) = node.snapshot()
        streams = (
            ("wheel_states", wheels, 10.0, 0.75, False),
            ("imu_raw", imu, 10.0, 0.75, False),
            ("odometry_filtered", filtered, 15.0, 0.75, True),
        )
        passed = invalid_messages == 0
        for name, stats, minimum_rate, maximum_gap, required in streams:
            stream_passed = (
                stats.rate_hz >= minimum_rate
                and stats.maximum_gap_s <= maximum_gap
            )
            if required:
                passed = passed and stream_passed
            print(
                f"{name}: rate={stats.rate_hz:.2f} Hz, "
                f"max_gap={stats.maximum_gap_s:.3f} s, "
                f"{'PASS' if stream_passed else 'WARN'}"
            )
            excessive_gaps = stats.excessive_gaps(
                measurement_start, maximum_gap
            )
            if excessive_gaps:
                details = ", ".join(
                    f"t={elapsed:.2f}s gap={gap:.3f}s"
                    for elapsed, gap in excessive_gaps[:10]
                )
                if len(excessive_gaps) > 10:
                    details += (
                        f", ... {len(excessive_gaps) - 10} more"
                    )
                print(f"  excessive_gaps: {details}")
            if not required and not stream_passed:
                print(
                    "  diagnostic_only: base telemetry quality is enforced "
                    "by check_base_topics.py."
                )

        if first_pose is None or last_pose is None:
            position_drift = math.inf
            yaw_drift = math.inf
            drift_passed = False
        else:
            position_drift = math.hypot(
                last_pose[0] - first_pose[0],
                last_pose[1] - first_pose[1],
            )
            yaw_drift = abs(
                math.atan2(
                    math.sin(last_pose[2] - first_pose[2]),
                    math.cos(last_pose[2] - first_pose[2]),
                )
            )
            drift_passed = position_drift <= 0.03 and yaw_drift <= 0.10
        passed = passed and drift_passed
        print(
            f"stationary_drift: position={position_drift:.4f} m, "
            f"yaw={math.degrees(yaw_drift):.2f} deg, "
            f"{'PASS' if drift_passed else 'FAIL'}"
        )
        print(f"invalid_messages: {invalid_messages}")
        print(
            "NAVIGATION PREFLIGHT: " + ("PASS" if passed else "FAIL")
        )
        return 0 if passed else 1
    finally:
        executor.remove_node(node)
        executor.shutdown()
        spin_thread.join(timeout=1.0)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
