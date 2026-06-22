#!/usr/bin/env python3

import math
from typing import Dict, Iterable, Optional, Tuple

import rclpy
from motivon_base.kinematics import (
    classify_sample_period,
    data_is_stale,
    mecanum_body_displacement,
    mecanum_forward_kinematics,
)
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_srvs.srv import Trigger


WHEEL_NAMES = (
    "front_left_wheel_joint",
    "front_right_wheel_joint",
    "rear_left_wheel_joint",
    "rear_right_wheel_joint",
)


def diagonal_covariance(values: Iterable[float]) -> list:
    covariance = [0.0] * 36
    for index, value in enumerate(values):
        covariance[index * 6 + index] = float(value)
    return covariance


class WheelOdometryNode(Node):
    def __init__(self) -> None:
        super().__init__("wheel_odometry_node")

        self.declare_parameter("wheel_radius_m", 0.0485)
        self.declare_parameter("half_wheelbase_m", 0.395 / 2.0)
        self.declare_parameter("half_track_width_m", 0.4545 / 2.0)
        self.declare_parameter("odom_x_scale", 1.0)
        self.declare_parameter("odom_y_scale", 0.948)
        self.declare_parameter("odom_yaw_scale", 1.0)
        self.declare_parameter("odom_frame", "odom")
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("maximum_sample_period_s", 0.25)
        self.declare_parameter("stale_timeout_s", 1.20)
        self.declare_parameter("stale_publish_period_s", 0.05)
        self.declare_parameter("maximum_wheel_speed_rad_s", 20.0)
        self.declare_parameter("wheel_delta_tolerance_rad", 0.50)
        self.declare_parameter(
            "pose_covariance_diagonal",
            [0.05, 0.05, 1.0e6, 1.0e6, 1.0e6, 0.20],
        )
        self.declare_parameter(
            "twist_covariance_diagonal",
            [0.02, 0.02, 1.0e6, 1.0e6, 1.0e6, 0.10],
        )

        self.wheel_radius = float(
            self.get_parameter("wheel_radius_m").value
        )
        self.lx_plus_ly = float(
            self.get_parameter("half_wheelbase_m").value
        ) + float(self.get_parameter("half_track_width_m").value)
        self.x_scale = float(self.get_parameter("odom_x_scale").value)
        self.y_scale = float(self.get_parameter("odom_y_scale").value)
        self.yaw_scale = float(
            self.get_parameter("odom_yaw_scale").value
        )
        self.odom_frame = str(self.get_parameter("odom_frame").value)
        self.base_frame = str(self.get_parameter("base_frame").value)
        self.maximum_sample_period = float(
            self.get_parameter("maximum_sample_period_s").value
        )
        self.stale_timeout_ns = int(
            float(self.get_parameter("stale_timeout_s").value) * 1.0e9
        )
        stale_publish_period = float(
            self.get_parameter("stale_publish_period_s").value
        )
        self.maximum_wheel_speed = float(
            self.get_parameter("maximum_wheel_speed_rad_s").value
        )
        self.wheel_delta_tolerance = float(
            self.get_parameter("wheel_delta_tolerance_rad").value
        )
        self.pose_covariance = diagonal_covariance(
            self.get_parameter("pose_covariance_diagonal").value
        )
        self.twist_covariance = diagonal_covariance(
            self.get_parameter("twist_covariance_diagonal").value
        )

        if (
            self.wheel_radius <= 0.0
            or self.lx_plus_ly <= 0.0
            or self.maximum_sample_period <= 0.0
            or self.stale_timeout_ns <= 0
            or stale_publish_period <= 0.0
            or self.maximum_wheel_speed <= 0.0
            or self.wheel_delta_tolerance < 0.0
        ):
            raise ValueError("Robot geometry parameters must be positive.")

        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0
        self.last_stamp_ns: Optional[int] = None
        self.last_receive_time_ns: Optional[int] = None
        self.last_wheel_positions: Optional[
            Tuple[float, float, float, float]
        ] = None
        self.last_missing_names_warning_ns = 0
        self.last_gap_warning_ns = 0
        self.stale_output_active = False

        self.odom_publisher = self.create_publisher(
            Odometry, "/wheel/odometry", qos_profile_sensor_data
        )
        self.create_subscription(
            JointState,
            "/base/wheel_states",
            self.wheel_states_callback,
            qos_profile_sensor_data,
        )
        self.create_service(
            Trigger, "/wheel_odometry/reset", self.reset_callback
        )
        self.create_timer(stale_publish_period, self.stale_watchdog_callback)

        self.get_logger().info(
            "Wheel odometry ready: "
            f"radius={self.wheel_radius:.4f} m, "
            f"lx+ly={self.lx_plus_ly:.4f} m."
        )

    @staticmethod
    def message_stamp_ns(message: JointState) -> int:
        stamp_ns = (
            int(message.header.stamp.sec) * 1_000_000_000
            + int(message.header.stamp.nanosec)
        )
        return stamp_ns

    def ordered_values(
        self, message: JointState, values
    ) -> Optional[Tuple[float, float, float, float]]:
        if len(message.name) != len(values):
            return None

        value_by_name: Dict[str, float] = dict(zip(message.name, values))
        if not all(name in value_by_name for name in WHEEL_NAMES):
            return None

        return tuple(float(value_by_name[name]) for name in WHEEL_NAMES)

    def warn_missing_wheels(self) -> None:
        now_ns = self.get_clock().now().nanoseconds
        if now_ns - self.last_missing_names_warning_ns >= 2_000_000_000:
            self.get_logger().warning(
                "Ignoring /base/wheel_states: expected position and velocity "
                "entries for "
                + ", ".join(WHEEL_NAMES)
            )
            self.last_missing_names_warning_ns = now_ns

    def warn_sample_timing(self, message: str) -> None:
        now_ns = self.get_clock().now().nanoseconds
        if now_ns - self.last_gap_warning_ns >= 2_000_000_000:
            self.get_logger().warning(message)
            self.last_gap_warning_ns = now_ns

    def wheel_states_callback(self, message: JointState) -> None:
        velocities = self.ordered_values(message, message.velocity)
        positions = self.ordered_values(message, message.position)
        if velocities is None or positions is None:
            self.warn_missing_wheels()
            return

        receive_time_ns = self.get_clock().now().nanoseconds
        stamp_ns = self.message_stamp_ns(message)
        if stamp_ns <= 0:
            stamp_ns = receive_time_ns

        sample_action = "integrate"
        if self.last_stamp_ns is not None:
            dt = (stamp_ns - self.last_stamp_ns) / 1_000_000_000.0
            sample_action = classify_sample_period(
                dt, self.maximum_sample_period
            )
            if sample_action == "reset":
                self.warn_sample_timing(
                    "Out-of-order or repeated wheel-state timestamp ignored."
                )
                return

        previous_receive_time_ns = self.last_receive_time_ns
        if self.stale_output_active:
            self.get_logger().info(
                "Wheel-state stream recovered; restoring displacement from "
                "encoder positions."
            )
            self.stale_output_active = False
        self.last_receive_time_ns = receive_time_ns

        vx, vy, wz = mecanum_forward_kinematics(
            velocities,
            self.wheel_radius,
            self.lx_plus_ly,
            self.x_scale,
            self.y_scale,
            self.yaw_scale,
        )

        if sample_action == "skip":
            dt = (stamp_ns - self.last_stamp_ns) / 1_000_000_000.0
            self.warn_sample_timing(
                f"Wheel-state gap was {dt:.3f} s; recovering movement "
                "from encoder positions."
            )

        if (
            self.last_wheel_positions is not None
            and previous_receive_time_ns is not None
        ):
            receive_dt = max(
                (receive_time_ns - previous_receive_time_ns)
                / 1_000_000_000.0,
                0.0,
            )
            wheel_deltas = tuple(
                current - previous
                for current, previous in zip(
                    positions, self.last_wheel_positions
                )
            )
            maximum_delta = (
                self.maximum_wheel_speed * receive_dt
                + self.wheel_delta_tolerance
            )
            if all(abs(delta) <= maximum_delta for delta in wheel_deltas):
                dx_body, dy_body, delta_yaw = mecanum_body_displacement(
                    wheel_deltas,
                    self.wheel_radius,
                    self.lx_plus_ly,
                    self.x_scale,
                    self.y_scale,
                    self.yaw_scale,
                )
                midpoint_yaw = self.yaw + 0.5 * delta_yaw
                self.x += (
                    dx_body * math.cos(midpoint_yaw)
                    - dy_body * math.sin(midpoint_yaw)
                )
                self.y += (
                    dx_body * math.sin(midpoint_yaw)
                    + dy_body * math.cos(midpoint_yaw)
                )
                self.yaw = math.atan2(
                    math.sin(self.yaw + delta_yaw),
                    math.cos(self.yaw + delta_yaw),
                )
            else:
                self.warn_sample_timing(
                    "Implausible wheel-position jump detected; encoder "
                    "integration baseline reset."
                )

        self.last_stamp_ns = stamp_ns
        self.last_wheel_positions = positions
        self.publish_odometry(message.header.stamp, vx, vy, wz)

    def publish_odometry(
        self, stamp, vx: float, vy: float, wz: float
    ) -> None:
        odometry = Odometry()
        odometry.header.stamp = stamp
        if (
            odometry.header.stamp.sec == 0
            and odometry.header.stamp.nanosec == 0
        ):
            odometry.header.stamp = self.get_clock().now().to_msg()
        odometry.header.frame_id = self.odom_frame
        odometry.child_frame_id = self.base_frame

        odometry.pose.pose.position.x = self.x
        odometry.pose.pose.position.y = self.y
        odometry.pose.pose.orientation.z = math.sin(self.yaw / 2.0)
        odometry.pose.pose.orientation.w = math.cos(self.yaw / 2.0)
        odometry.pose.covariance = self.pose_covariance

        odometry.twist.twist.linear.x = vx
        odometry.twist.twist.linear.y = vy
        odometry.twist.twist.angular.z = wz
        odometry.twist.covariance = self.twist_covariance
        self.odom_publisher.publish(odometry)

    def stale_watchdog_callback(self) -> None:
        if self.last_receive_time_ns is None:
            return

        now = self.get_clock().now()
        if not data_is_stale(
            now.nanoseconds,
            self.last_receive_time_ns,
            self.stale_timeout_ns,
        ):
            return

        if not self.stale_output_active:
            self.get_logger().warning(
                "Wheel-state stream is stale; publishing zero velocity."
            )
            self.stale_output_active = True
        self.publish_odometry(now.to_msg(), 0.0, 0.0, 0.0)

    def reset_callback(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0
        self.last_stamp_ns = None
        self.last_receive_time_ns = None
        self.last_wheel_positions = None
        self.stale_output_active = False
        response.success = True
        response.message = "Wheel odometry reset to HOME origin."
        self.get_logger().info(response.message)
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = WheelOdometryNode()
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
