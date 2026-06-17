#!/usr/bin/env python3

from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data


class ManualControlNode(Node):
    """Scale GUI joystick input into manual velocity commands."""

    def __init__(self):
        super().__init__("manual_control_node")
        self.declare_parameter("publish_rate_hz", 25.0)
        self.declare_parameter("input_timeout_s", 0.35)
        self.declare_parameter("deadband", 0.08)
        self.declare_parameter("max_linear_x_mps", 0.10)
        self.declare_parameter("max_linear_y_mps", 0.08)
        self.declare_parameter("max_angular_z_rad_s", 0.35)

        self.input_timeout_s = float(self.get_parameter("input_timeout_s").value)
        self.deadband = float(self.get_parameter("deadband").value)
        self.max_linear_x = float(self.get_parameter("max_linear_x_mps").value)
        self.max_linear_y = float(self.get_parameter("max_linear_y_mps").value)
        self.max_angular_z = float(
            self.get_parameter("max_angular_z_rad_s").value
        )

        self.latest_input = Twist()
        self.latest_input_time_s: Optional[float] = None

        self.cmd_pub = self.create_publisher(
            Twist, "/manual/cmd_vel", qos_profile_sensor_data
        )
        self.create_subscription(
            Twist,
            "/manual/input",
            self.on_manual_input,
            qos_profile_sensor_data,
        )

        rate = max(1.0, float(self.get_parameter("publish_rate_hz").value))
        self.create_timer(1.0 / rate, self.publish_manual_command)
        self.get_logger().info("Manual control node ready.")

    def now_s(self) -> float:
        return self.get_clock().now().nanoseconds / 1_000_000_000.0

    def on_manual_input(self, msg: Twist) -> None:
        self.latest_input = msg
        self.latest_input_time_s = self.now_s()

    def apply_deadband(self, value: float) -> float:
        value = max(-1.0, min(1.0, float(value)))
        if abs(value) < self.deadband:
            return 0.0
        return value

    def publish_manual_command(self) -> None:
        command = Twist()
        if (
            self.latest_input_time_s is not None
            and self.now_s() - self.latest_input_time_s <= self.input_timeout_s
        ):
            command.linear.x = (
                self.apply_deadband(self.latest_input.linear.x) * self.max_linear_x
            )
            command.linear.y = (
                self.apply_deadband(self.latest_input.linear.y) * self.max_linear_y
            )
            command.angular.z = (
                self.apply_deadband(self.latest_input.angular.z)
                * self.max_angular_z
            )
        self.cmd_pub.publish(command)


def main(args=None):
    rclpy.init(args=args)
    node = ManualControlNode()
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
