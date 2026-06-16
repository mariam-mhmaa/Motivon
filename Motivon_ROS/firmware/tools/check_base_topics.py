#!/usr/bin/env python3

import argparse
from dataclasses import dataclass, field
import math
import time
from typing import Dict, List, Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, JointState
from std_msgs.msg import Bool, UInt32


EXPECTED_WHEEL_NAMES = {
    "front_left_wheel_joint",
    "front_right_wheel_joint",
    "rear_left_wheel_joint",
    "rear_right_wheel_joint",
}


@dataclass
class TopicStats:
    arrivals: List[float] = field(default_factory=list)
    stamp_gaps_s: List[float] = field(default_factory=list)
    invalid_messages: int = 0
    last_stamp_ns: Optional[int] = None
    timestamp_regressions: int = 0

    def record(
        self, stamp_ns: Optional[int] = None, valid: bool = True
    ) -> None:
        self.arrivals.append(time.monotonic())
        if not valid:
            self.invalid_messages += 1
        if stamp_ns is not None:
            if stamp_ns <= 0:
                self.invalid_messages += 1
            elif (
                self.last_stamp_ns is not None
                and stamp_ns <= self.last_stamp_ns
            ):
                self.timestamp_regressions += 1
            elif self.last_stamp_ns is not None:
                self.stamp_gaps_s.append(
                    (stamp_ns - self.last_stamp_ns) / 1.0e9
                )
            self.last_stamp_ns = stamp_ns

    @property
    def count(self) -> int:
        return len(self.arrivals)

    @property
    def rate_hz(self) -> float:
        if self.count < 2:
            return 0.0
        duration = self.arrivals[-1] - self.arrivals[0]
        return (self.count - 1) / duration if duration > 0.0 else 0.0

    @property
    def maximum_gap_s(self) -> float:
        if self.count < 2:
            return float("inf")
        return max(
            current - previous
            for previous, current in zip(self.arrivals, self.arrivals[1:])
        )

    @property
    def maximum_stamp_gap_s(self) -> float:
        if not self.stamp_gaps_s:
            return float("nan")
        return max(self.stamp_gaps_s)

    def excessive_arrival_gaps(
        self, measurement_start: float, limit_s: float
    ) -> List[tuple]:
        return [
            (current - measurement_start, current - previous)
            for previous, current in zip(
                self.arrivals, self.arrivals[1:]
            )
            if current - previous > limit_s
        ]

    def observed_coverage_s(
        self, measurement_start: float, measurement_end: float
    ) -> float:
        if not self.arrivals:
            return 0.0
        initial_silence = self.arrivals[0] - measurement_start
        final_silence = measurement_end - self.arrivals[-1]
        return max(
            0.0,
            measurement_end
            - measurement_start
            - initial_silence
            - final_silence,
        )

    def boundary_gap_s(
        self, measurement_start: float, measurement_end: float
    ) -> float:
        if not self.arrivals:
            return float("inf")
        return max(
            self.arrivals[0] - measurement_start,
            measurement_end - self.arrivals[-1],
        )


class BaseTopicMonitor(Node):
    def __init__(self) -> None:
        super().__init__("motivon_base_topic_monitor")
        self.stats: Dict[str, TopicStats] = {
            "/base/wheel_states": TopicStats(),
            "/imu/data_raw": TopicStats(),
            "/base/imu_ok": TopicStats(),
            "/base/heartbeat": TopicStats(),
        }
        self.last_heartbeat: Optional[int] = None
        self.heartbeat_discontinuities = 0
        self.imu_ok_true_count = 0
        self.imu_ok_false_count = 0
        self.create_subscription(
            JointState,
            "/base/wheel_states",
            self.wheel_callback,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            Imu,
            "/imu/data_raw",
            self.imu_callback,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            Bool,
            "/base/imu_ok",
            self.imu_ok_callback,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            UInt32,
            "/base/heartbeat",
            self.heartbeat_callback,
            qos_profile_sensor_data,
        )

    @staticmethod
    def stamp_ns(message) -> int:
        return (
            int(message.header.stamp.sec) * 1_000_000_000
            + int(message.header.stamp.nanosec)
        )

    def wheel_callback(self, message: JointState) -> None:
        valid = (
            set(message.name) == EXPECTED_WHEEL_NAMES
            and len(message.position) == 4
            and len(message.velocity) == 4
            and all(math.isfinite(value) for value in message.position)
            and all(math.isfinite(value) for value in message.velocity)
        )
        self.stats["/base/wheel_states"].record(
            self.stamp_ns(message), valid
        )

    def imu_callback(self, message: Imu) -> None:
        angular_velocity = message.angular_velocity
        valid = (
            message.header.frame_id == "base_link"
            and all(
                math.isfinite(value)
                for value in (
                    angular_velocity.x,
                    angular_velocity.y,
                    angular_velocity.z,
                )
            )
        )
        self.stats["/imu/data_raw"].record(self.stamp_ns(message), valid)

    def heartbeat_callback(self, message: UInt32) -> None:
        value = int(message.data)
        if self.last_heartbeat is not None:
            expected = (self.last_heartbeat + 1) % (2**32)
            if value != expected:
                self.heartbeat_discontinuities += 1
        self.last_heartbeat = value
        self.stats["/base/heartbeat"].record()

    def imu_ok_callback(self, message: Bool) -> None:
        if message.data:
            self.imu_ok_true_count += 1
        else:
            self.imu_ok_false_count += 1
        self.stats["/base/imu_ok"].record()

    def ready(self) -> bool:
        discovered_nodes = set(self.get_node_names())
        return (
            "esp32_base_node" in discovered_nodes
            and self.stats["/base/wheel_states"].count >= 10
            and self.stats["/base/imu_ok"].count >= 2
            and self.stats["/base/heartbeat"].count >= 2
        )

    def reset_measurement(self) -> None:
        self.stats = {
            "/base/wheel_states": TopicStats(),
            "/imu/data_raw": TopicStats(),
            "/base/imu_ok": TopicStats(),
            "/base/heartbeat": TopicStats(),
        }
        self.last_heartbeat = None
        self.heartbeat_discontinuities = 0
        self.imu_ok_true_count = 0
        self.imu_ok_false_count = 0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate Motivon ESP32 telemetry simultaneously."
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=70.0,
        help="Measurement duration in seconds. Default: 70.",
    )
    parser.add_argument(
        "--ready-timeout",
        type=float,
        default=20.0,
        help="Seconds allowed for a complete ESP session. Default: 20.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.duration <= 0.0:
        raise ValueError("--duration must be positive")
    if args.ready_timeout <= 0.0:
        raise ValueError("--ready-timeout must be positive")

    limits = {
        "/base/wheel_states": (20.0, 0.15),
        "/imu/data_raw": (20.0, 0.15),
        "/base/imu_ok": (0.80, 1.50),
        "/base/heartbeat": (0.80, 1.50),
    }

    rclpy.init()
    node = BaseTopicMonitor()
    try:
        print(
            "Waiting for ESP node, wheel telemetry, and status streams before "
            "starting the timed measurement..."
        )
        ready_deadline = time.monotonic() + args.ready_timeout
        while time.monotonic() < ready_deadline and not node.ready():
            rclpy.spin_once(node, timeout_sec=0.1)
        if not node.ready():
            print("BASE TELEMETRY TEST: FAIL (session not ready)")
            return 1

        node.reset_measurement()
        measurement_start = time.monotonic()
        deadline = measurement_start + args.duration
        print(f"Session ready. Measuring for {args.duration:.1f} seconds.")
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        measurement_end = time.monotonic()

        discovered_nodes = set(node.get_node_names())
        all_passed = "esp32_base_node" in discovered_nodes
        print(
            "esp32_base_node: "
            + ("FOUND" if all_passed else "MISSING")
        )

        for topic, stats in node.stats.items():
            minimum_rate, maximum_gap = limits[topic]
            minimum_coverage = args.duration * 0.95
            coverage = stats.observed_coverage_s(
                measurement_start, measurement_end
            )
            boundary_gap = stats.boundary_gap_s(
                measurement_start, measurement_end
            )
            passed = (
                stats.rate_hz >= minimum_rate
                and stats.maximum_gap_s <= maximum_gap
                and coverage >= minimum_coverage
                and boundary_gap <= maximum_gap
                and stats.invalid_messages == 0
                and stats.timestamp_regressions == 0
            )
            if topic == "/base/heartbeat":
                passed = passed and node.heartbeat_discontinuities == 0
            if topic == "/base/imu_ok":
                passed = (
                    passed
                    and node.imu_ok_true_count > 0
                    and node.imu_ok_false_count == 0
                )
            all_passed = all_passed and passed
            stamp_gap_text = (
                f"{stats.maximum_stamp_gap_s:.3f} s"
                if math.isfinite(stats.maximum_stamp_gap_s)
                else "n/a"
            )
            print(
                f"{topic}: count={stats.count}, "
                f"rate={stats.rate_hz:.2f} Hz, "
                f"max_gap={stats.maximum_gap_s:.3f} s, "
                f"max_stamp_gap={stamp_gap_text}, "
                f"coverage={coverage:.1f}/{args.duration:.1f} s, "
                f"boundary_gap={boundary_gap:.3f} s, "
                f"invalid={stats.invalid_messages}, "
                f"time_regressions={stats.timestamp_regressions}, "
                f"{'PASS' if passed else 'FAIL'}"
            )
            if topic == "/base/imu_ok":
                print(
                    "  imu_ok_values: "
                    f"true={node.imu_ok_true_count}, "
                    f"false={node.imu_ok_false_count}"
                )
            excessive_gaps = stats.excessive_arrival_gaps(
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

        print(
            "heartbeat_discontinuities: "
            f"{node.heartbeat_discontinuities}"
        )
        print(
            "BASE TELEMETRY TEST: "
            + ("PASS" if all_passed else "FAIL")
        )
        print(
            "Scope: telemetry transport and message validity only; "
            "motor command behavior is tested separately."
        )
        return 0 if all_passed else 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
