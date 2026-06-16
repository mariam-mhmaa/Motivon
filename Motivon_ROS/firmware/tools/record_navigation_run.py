#!/usr/bin/env python3

import argparse
import csv
import math
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple

from geometry_msgs.msg import Twist
from motivon_interfaces.msg import NavigationStatus
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState


WHEEL_NAMES = (
    "front_left_wheel_joint",
    "front_right_wheel_joint",
    "rear_left_wheel_joint",
    "rear_right_wheel_joint",
)
WHEEL_RADIUS_M = 0.0485
KINEMATIC_RADIUS_M = 0.1975 + 0.22725


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


class NavigationRunRecorder(Node):
    def __init__(self) -> None:
        super().__init__("motivon_navigation_run_recorder")
        self.started = False
        self.finished = False
        self.start_monotonic = 0.0
        self.last_status = ""
        self.last_detail = ""
        self.latest_command = (0.0, 0.0, 0.0)
        self.command_samples: List[Tuple[float, float, float]] = []
        self.wheel_samples: List[Dict[str, float]] = []
        self.wheel_errors: List[Dict[str, float]] = []
        self.wheel_poses: List[Tuple[float, float, float]] = []
        self.filtered_poses: List[Tuple[float, float, float]] = []
        self.rows: List[List[object]] = []
        self.create_subscription(
            NavigationStatus,
            "/navigation/status",
            self._status_callback,
            10,
        )
        self.create_subscription(
            Twist,
            "/cmd_vel",
            self._command_callback,
            qos_profile_sensor_data,
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
            self._wheel_odom_callback,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            Odometry,
            "/odometry/filtered",
            self._filtered_odom_callback,
            qos_profile_sensor_data,
        )

    def elapsed(self) -> float:
        if not self.started:
            return 0.0
        return time.monotonic() - self.start_monotonic

    def _record_row(self, kind: str, values: List[object]) -> None:
        if self.started:
            self.rows.append([self.elapsed(), kind] + values)

    def _status_callback(self, message: NavigationStatus) -> None:
        self.last_status = message.state
        self.last_detail = message.detail
        if not self.started and message.target_name:
            self.started = True
            self.start_monotonic = time.monotonic()
            print(
                f"Recording target {message.target_name}; "
                f"initial state={message.state}"
            )
        self._record_row(
            "status",
            [
                message.state,
                message.target_name,
                message.active_waypoint,
                message.distance_remaining_m,
                message.cross_track_error_m,
                message.yaw_error_rad,
            ],
        )
        if self.started and not message.target_name and message.state in {
            "IDLE",
            "FAILED",
            "REHOME_REQUIRED",
        }:
            self.finished = True

    def _command_callback(self, message: Twist) -> None:
        sample = (
            float(message.linear.x),
            float(message.linear.y),
            float(message.angular.z),
        )
        self.latest_command = sample
        if self.started:
            self.command_samples.append(sample)
        self._record_row("command", list(sample))

    def _wheel_callback(self, message: JointState) -> None:
        values = dict(zip(message.name, message.velocity))
        if not all(name in values for name in WHEEL_NAMES):
            return
        sample = {
            name: float(values[name]) for name in WHEEL_NAMES
        }
        if self.started:
            self.wheel_samples.append(sample)
            targets = wheel_targets(*self.latest_command)
            self.wheel_errors.append(
                {
                    name: sample[name] - targets[name]
                    for name in WHEEL_NAMES
                }
            )
        self._record_row(
            "wheels", [sample[name] for name in WHEEL_NAMES]
        )

    def _record_odometry(
        self, kind: str, message: Odometry
    ) -> Tuple[float, float, float]:
        pose = (
            float(message.pose.pose.position.x),
            float(message.pose.pose.position.y),
            yaw_from_odometry(message),
        )
        self._record_row(kind, list(pose))
        return pose

    def _wheel_odom_callback(self, message: Odometry) -> None:
        pose = self._record_odometry("wheel_odom", message)
        if self.started:
            self.wheel_poses.append(pose)

    def _filtered_odom_callback(self, message: Odometry) -> None:
        pose = self._record_odometry("filtered_odom", message)
        if self.started:
            self.filtered_poses.append(pose)


def pose_summary(
    name: str, poses: List[Tuple[float, float, float]]
) -> None:
    if len(poses) < 2:
        print(f"{name}: insufficient samples")
        return
    first = poses[0]
    last = poses[-1]
    delta_yaw = math.atan2(
        math.sin(last[2] - first[2]),
        math.cos(last[2] - first[2]),
    )
    peak_lateral = max(abs(pose[1] - first[1]) for pose in poses)
    peak_yaw = max(
        abs(
            math.atan2(
                math.sin(pose[2] - first[2]),
                math.cos(pose[2] - first[2]),
            )
        )
        for pose in poses
    )
    print(
        f"{name}: dx={last[0] - first[0]:.4f} m, "
        f"dy={last[1] - first[1]:.4f} m, "
        f"dyaw={math.degrees(delta_yaw):.2f} deg, "
        f"peak_abs_y={peak_lateral:.4f} m, "
        f"peak_abs_yaw={math.degrees(peak_yaw):.2f} deg"
    )


def wheel_targets(vx: float, vy: float, wz: float) -> Dict[str, float]:
    return {
        "front_left_wheel_joint": (
            vx - vy - KINEMATIC_RADIUS_M * wz
        )
        / WHEEL_RADIUS_M,
        "front_right_wheel_joint": (
            vx + vy + KINEMATIC_RADIUS_M * wz
        )
        / WHEEL_RADIUS_M,
        "rear_left_wheel_joint": (
            vx + vy - KINEMATIC_RADIUS_M * wz
        )
        / WHEEL_RADIUS_M,
        "rear_right_wheel_joint": (
            vx - vy + KINEMATIC_RADIUS_M * wz
        )
        / WHEEL_RADIUS_M,
    }


def wheel_error_summary(errors: List[Dict[str, float]]) -> None:
    if not errors:
        print("wheel_tracking: insufficient samples")
        return
    for name in WHEEL_NAMES:
        values = [sample[name] for sample in errors]
        mean_error = sum(values) / len(values)
        mean_absolute_error = sum(abs(value) for value in values) / len(values)
        print(
            f"wheel_tracking {name}: "
            f"mean_error={mean_error:.3f} rad/s, "
            f"mean_abs_error={mean_absolute_error:.3f} rad/s"
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Record commands and localization during one goal."
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--output",
        default=str(Path.home() / "wp1_navigation_run.csv"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.timeout <= 0.0:
        raise ValueError("--timeout must be positive")

    rclpy.init()
    node = NavigationRunRecorder()
    deadline = time.monotonic() + args.timeout
    try:
        print("Waiting for a navigation goal...")
        while time.monotonic() < deadline and not node.finished:
            rclpy.spin_once(node, timeout_sec=0.05)

        output_path = Path(args.output).expanduser()
        with output_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["elapsed_s", "kind", "value_1", "value_2",
                             "value_3", "value_4", "value_5", "value_6"])
            writer.writerows(node.rows)

        if not node.started:
            print("NAVIGATION RUN RECORD: FAIL (no goal observed)")
            return 1

        if node.command_samples:
            max_y = max(abs(sample[1]) for sample in node.command_samples)
            max_wz = max(abs(sample[2]) for sample in node.command_samples)
            print(
                f"commands: samples={len(node.command_samples)}, "
                f"max_abs_y={max_y:.4f} m/s, "
                f"max_abs_wz={max_wz:.4f} rad/s"
            )
        else:
            print("commands: no samples")

        wheel_error_summary(node.wheel_errors)
        pose_summary("wheel_odometry", node.wheel_poses)
        pose_summary("filtered_odometry", node.filtered_poses)
        print(
            f"final_status={node.last_status}; detail={node.last_detail}"
        )
        print(f"CSV written to {output_path}")
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
