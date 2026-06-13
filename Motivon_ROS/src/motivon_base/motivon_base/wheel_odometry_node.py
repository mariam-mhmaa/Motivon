#!/usr/bin/env python3

import math
from typing import Dict, Iterable, Optional, Tuple

import rclpy
from motivon_base.kinematics import mecanum_forward_kinematics
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
        self.pose_covariance = diagonal_covariance(
            self.get_parameter("pose_covariance_diagonal").value
        )
        self.twist_covariance = diagonal_covariance(
            self.get_parameter("twist_covariance_diagonal").value
        )

        if self.wheel_radius <= 0.0 or self.lx_plus_ly <= 0.0:
            raise ValueError("Robot geometry parameters must be positive.")

        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0
        self.last_stamp_ns: Optional[int] = None
        self.last_missing_names_warning_ns = 0

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

    def ordered_velocities(
        self, message: JointState
    ) -> Optional[Tuple[float, float, float, float]]:
        if len(message.name) != len(message.velocity):
            return None

        velocity_by_name: Dict[str, float] = dict(
            zip(message.name, message.velocity)
        )
        if not all(name in velocity_by_name for name in WHEEL_NAMES):
            return None

        return tuple(
            float(velocity_by_name[name]) for name in WHEEL_NAMES
        )

    def warn_missing_wheels(self) -> None:
        now_ns = self.get_clock().now().nanoseconds
        if now_ns - self.last_missing_names_warning_ns >= 2_000_000_000:
            self.get_logger().warning(
                "Ignoring /base/wheel_states: expected velocity entries for "
                + ", ".join(WHEEL_NAMES)
            )
            self.last_missing_names_warning_ns = now_ns

    def wheel_states_callback(self, message: JointState) -> None:
        velocities = self.ordered_velocities(message)
        if velocities is None:
            self.warn_missing_wheels()
            return

        stamp_ns = self.message_stamp_ns(message)
        if stamp_ns <= 0:
            stamp_ns = self.get_clock().now().nanoseconds

        vx, vy, wz = mecanum_forward_kinematics(
            velocities,
            self.wheel_radius,
            self.lx_plus_ly,
            self.x_scale,
            self.y_scale,
            self.yaw_scale,
        )

        if self.last_stamp_ns is not None:
            dt = (stamp_ns - self.last_stamp_ns) / 1_000_000_000.0
            if 0.0 < dt <= self.maximum_sample_period:
                midpoint_yaw = self.yaw + 0.5 * wz * dt
                self.x += (
                    vx * math.cos(midpoint_yaw)
                    - vy * math.sin(midpoint_yaw)
                ) * dt
                self.y += (
                    vx * math.sin(midpoint_yaw)
                    + vy * math.cos(midpoint_yaw)
                ) * dt
                self.yaw = math.atan2(
                    math.sin(self.yaw + wz * dt),
                    math.cos(self.yaw + wz * dt),
                )
            elif dt <= 0.0:
                return
            else:
                self.get_logger().warning(
                    f"Wheel-state gap was {dt:.3f} s; pose integration skipped."
                )

        self.last_stamp_ns = stamp_ns
        self.publish_odometry(message, vx, vy, wz)

    def publish_odometry(
        self, source: JointState, vx: float, vy: float, wz: float
    ) -> None:
        odometry = Odometry()
        odometry.header.stamp = source.header.stamp
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

    def reset_callback(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0
        self.last_stamp_ns = None
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
