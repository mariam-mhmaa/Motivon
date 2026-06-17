#!/usr/bin/env python3

import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


class BaseRecoveryNode(Node):
    """Request a safe ESP32 software reset through the firmware topic."""

    def __init__(self) -> None:
        super().__init__("base_recovery_node")
        self.reset_pub = self.create_publisher(
            Bool, "/base/software_reset", 10
        )
        self.create_service(Trigger, "/base/recover", self.recover_callback)
        self.get_logger().info(
            "Base recovery ready: call /base/recover to request ESP32 reset."
        )

    def recover_callback(self, _request, response):
        msg = Bool()
        msg.data = True
        for _ in range(10):
            self.reset_pub.publish(msg)
            time.sleep(0.05)
        response.success = True
        response.message = (
            "Published /base/software_reset. If the ESP32 is not visible, "
            "restart the micro-ROS agent; launch respawn will bring it back."
        )
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = BaseRecoveryNode()
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
