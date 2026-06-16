#!/usr/bin/env python3

import argparse
import time
from typing import Dict, Optional

from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, UInt32


WHEEL_NAMES = (
    "front_left_wheel_joint",
    "front_right_wheel_joint",
    "rear_left_wheel_joint",
    "rear_right_wheel_joint",
)


class MotionContinuityMonitor(Node):
    def __init__(self) -> None:
        super().__init__("motivon_motion_continuity_monitor")
        self.latest_velocities: Optional[Dict[str, float]] = None
        self.last_wheel_time: Optional[float] = None
        self.last_wheel_stamp_ns: Optional[int] = None
        self.maximum_wheel_gap_s = 0.0
        self.maximum_wheel_stamp_gap_s = 0.0
        self.wheel_timestamp_regressions = 0
        self.wheel_gap_events = []
        self.last_heartbeat: Optional[int] = None
        self.last_heartbeat_time: Optional[float] = None
        self.maximum_heartbeat_gap_s = 0.0
        self.heartbeat_discontinuities = 0
        self.minimum_forward_speed = float("inf")
        self.cmd_publisher = self.create_publisher(
            Twist, "/cmd_vel", qos_profile_sensor_data
        )
        self.enable_publisher = self.create_publisher(
            Bool, "/base/enable", 10
        )
        self.create_subscription(
            JointState,
            "/base/wheel_states",
            self.wheel_callback,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            UInt32,
            "/base/heartbeat",
            self.heartbeat_callback,
            qos_profile_sensor_data,
        )

    def wheel_callback(self, message: JointState) -> None:
        if len(message.name) != len(message.velocity):
            return
        values = dict(zip(message.name, message.velocity))
        if not all(name in values for name in WHEEL_NAMES):
            return
        now = time.monotonic()
        if self.last_wheel_time is not None:
            gap_s = now - self.last_wheel_time
            self.maximum_wheel_gap_s = max(
                self.maximum_wheel_gap_s, gap_s
            )
            if gap_s > 0.25:
                self.wheel_gap_events.append(gap_s)
        self.last_wheel_time = now

        stamp_ns = (
            int(message.header.stamp.sec) * 1_000_000_000
            + int(message.header.stamp.nanosec)
        )
        if stamp_ns <= 0:
            self.wheel_timestamp_regressions += 1
        elif self.last_wheel_stamp_ns is not None:
            if stamp_ns <= self.last_wheel_stamp_ns:
                self.wheel_timestamp_regressions += 1
            else:
                stamp_gap_s = (
                    stamp_ns - self.last_wheel_stamp_ns
                ) / 1.0e9
                self.maximum_wheel_stamp_gap_s = max(
                    self.maximum_wheel_stamp_gap_s,
                    stamp_gap_s,
                )
        self.last_wheel_stamp_ns = stamp_ns

        self.latest_velocities = {
            name: float(values[name]) for name in WHEEL_NAMES
        }

    def heartbeat_callback(self, message: UInt32) -> None:
        now = time.monotonic()
        if self.last_heartbeat_time is not None:
            self.maximum_heartbeat_gap_s = max(
                self.maximum_heartbeat_gap_s,
                now - self.last_heartbeat_time,
            )
        self.last_heartbeat_time = now
        value = int(message.data)
        if self.last_heartbeat is not None:
            expected = (self.last_heartbeat + 1) % (2**32)
            if value != expected:
                self.heartbeat_discontinuities += 1
        self.last_heartbeat = value

    def endpoints_ready(self) -> bool:
        return (
            self.cmd_publisher.get_subscription_count() >= 1
            and self.enable_publisher.get_subscription_count() >= 1
            and self.last_wheel_time is not None
        )

    def publish_enable(self, enabled: bool) -> None:
        message = Bool()
        message.data = enabled
        self.enable_publisher.publish(message)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Hold a low forward wheel command and detect command, "
            "telemetry, or ESP-session interruptions."
        )
    )
    parser.add_argument(
        "--wheels-lifted",
        action="store_true",
        help="Required confirmation that every drive wheel is off the floor.",
    )
    parser.add_argument("--duration", type=float, default=45.0)
    parser.add_argument("--speed", type=float, default=0.05)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.wheels_lifted:
        print("REFUSED: lift every drive wheel and add --wheels-lifted")
        return 2
    if args.duration < 15.0:
        raise ValueError("--duration must be at least 15 seconds")
    if not 0.02 <= args.speed <= 0.08:
        raise ValueError("--speed must be between 0.02 and 0.08 m/s")

    rclpy.init()
    node = MotionContinuityMonitor()
    command = Twist()
    command.linear.x = args.speed
    stopped_since: Optional[float] = None
    longest_stop_s = 0.0
    stop_events = 0

    try:
        print("Waiting for ESP command endpoints and wheel telemetry...")
        ready_deadline = time.monotonic() + 15.0
        while time.monotonic() < ready_deadline and not node.endpoints_ready():
            node.publish_enable(False)
            rclpy.spin_once(node, timeout_sec=0.05)
        if not node.endpoints_ready():
            print("MOTION CONTINUITY TEST: FAIL (endpoints unavailable)")
            return 1

        node.maximum_wheel_gap_s = 0.0
        node.maximum_wheel_stamp_gap_s = 0.0
        node.wheel_timestamp_regressions = 0
        node.wheel_gap_events = []
        node.last_heartbeat_time = None
        node.maximum_heartbeat_gap_s = 0.0
        node.heartbeat_discontinuities = 0
        start = time.monotonic()
        warmup_end = start + 3.0
        end = start + args.duration
        next_command = 0.0
        next_enable = 0.0
        previous_command_publish = None
        maximum_command_publish_gap_s = 0.0
        last_evaluated_wheel_time = None
        print(
            f"Running {args.duration:.0f} s at {args.speed:.3f} m/s "
            "with all wheels lifted."
        )
        while time.monotonic() < end:
            now = time.monotonic()
            if now >= next_command:
                node.cmd_publisher.publish(command)
                if previous_command_publish is not None:
                    maximum_command_publish_gap_s = max(
                        maximum_command_publish_gap_s,
                        now - previous_command_publish,
                    )
                previous_command_publish = now
                next_command = now + 0.05
            if now >= next_enable:
                node.publish_enable(True)
                next_enable = now + 0.50
            rclpy.spin_once(node, timeout_sec=0.01)

            if (
                now < warmup_end
                or node.latest_velocities is None
                or node.last_wheel_time == last_evaluated_wheel_time
            ):
                continue
            last_evaluated_wheel_time = node.last_wheel_time
            forward_speed = sum(
                node.latest_velocities.values()
            ) / len(WHEEL_NAMES)
            node.minimum_forward_speed = min(
                node.minimum_forward_speed, forward_speed
            )
            moving = forward_speed > 0.25
            if not moving and stopped_since is None:
                stopped_since = node.last_wheel_time
                stop_events += 1
            elif moving and stopped_since is not None:
                longest_stop_s = max(
                    longest_stop_s,
                    node.last_wheel_time - stopped_since,
                )
                stopped_since = None

        if stopped_since is not None and node.last_wheel_time is not None:
            longest_stop_s = max(
                longest_stop_s,
                node.last_wheel_time - stopped_since,
            )

        stop = Twist()
        stop_deadline = time.monotonic() + 1.2
        while time.monotonic() < stop_deadline:
            node.cmd_publisher.publish(stop)
            node.publish_enable(False)
            rclpy.spin_once(node, timeout_sec=0.02)

        stopped = (
            node.latest_velocities is not None
            and all(
                abs(velocity) < 0.20
                for velocity in node.latest_velocities.values()
            )
        )
        passed = (
            longest_stop_s < 0.25
            and node.maximum_wheel_gap_s < 0.60
            and node.maximum_wheel_stamp_gap_s < 0.60
            and node.wheel_timestamp_regressions == 0
            and node.maximum_heartbeat_gap_s < 1.60
            and node.heartbeat_discontinuities == 0
            and maximum_command_publish_gap_s < 0.15
            and stopped
        )
        print(f"observed_low_speed_events: {stop_events}")
        print(f"longest_observed_low_speed_s: {longest_stop_s:.3f}")
        print(
            f"minimum_observed_forward_speed_rad_s: "
            f"{node.minimum_forward_speed:.3f}"
        )
        print(f"telemetry_gap_events: {len(node.wheel_gap_events)}")
        print(
            "maximum_wheel_telemetry_gap_s: "
            f"{node.maximum_wheel_gap_s:.3f}"
        )
        print(
            "maximum_wheel_timestamp_gap_s: "
            f"{node.maximum_wheel_stamp_gap_s:.3f}"
        )
        print(
            "wheel_timestamp_regressions: "
            f"{node.wheel_timestamp_regressions}"
        )
        print(
            "maximum_heartbeat_gap_s: "
            f"{node.maximum_heartbeat_gap_s:.3f}"
        )
        print(
            "heartbeat_discontinuities: "
            f"{node.heartbeat_discontinuities}"
        )
        print(
            "maximum_local_command_publish_gap_s: "
            f"{maximum_command_publish_gap_s:.3f}"
        )
        print(f"final_stop: {'PASS' if stopped else 'FAIL'}")
        print(
            "MOTION CONTINUITY TEST: "
            + ("PASS" if passed else "FAIL")
        )
        return 0 if passed else 1
    finally:
        node.publish_enable(False)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
