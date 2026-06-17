#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from motivon_control.gate_logic import normalize_mode


class ModeManagerNode(Node):
    """Own and continuously publish the robot control mode."""

    def __init__(self):
        super().__init__("mode_manager_node")
        self.declare_parameter("initial_mode", "AUTO")
        self.declare_parameter("publish_rate_hz", 5.0)

        self.mode = normalize_mode(str(self.get_parameter("initial_mode").value))
        self.mode_pub = self.create_publisher(String, "/system/mode", 10)
        self.status_pub = self.create_publisher(String, "/system/mode/status", 10)
        self.create_subscription(
            String,
            "/system/mode/request",
            self.on_mode_request,
            10,
        )

        rate = max(1.0, float(self.get_parameter("publish_rate_hz").value))
        self.create_timer(1.0 / rate, self.publish_mode)
        self.publish_mode()
        self.get_logger().info(f"Mode manager ready: mode={self.mode}.")

    def on_mode_request(self, msg: String) -> None:
        requested = normalize_mode(msg.data)
        if requested not in ("AUTO", "MANUAL"):
            self.get_logger().warning(
                f"Ignoring unsupported mode request: {msg.data!r}"
            )
            return
        if requested != self.mode:
            self.mode = requested
            self.get_logger().warning(f"Control mode changed to {self.mode}.")
        self.publish_mode()

    def publish_mode(self) -> None:
        msg = String()
        msg.data = self.mode
        self.mode_pub.publish(msg)
        self.status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = ModeManagerNode()
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
