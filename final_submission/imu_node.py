#!/usr/bin/env python3
"""Expose a stable IMU topic shape for navigation and real-robot integration."""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import Bool


class ImuNode(Node):
    def __init__(self):
        super().__init__("imu_node")
        self.imu_pub = self.create_publisher(Imu, "/imu/data", 10)
        self.ok_pub = self.create_publisher(Bool, "/imu/status", 10)
        self.create_subscription(Imu, "/imu", self._imu_cb, 10)
        self.get_logger().info("IMU node started.")

    def _imu_cb(self, msg: Imu):
        self.imu_pub.publish(msg)
        status = Bool()
        status.data = True
        self.ok_pub.publish(status)


def main(args=None):
    rclpy.init(args=args)
    node = ImuNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()

