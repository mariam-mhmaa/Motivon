#!/usr/bin/env python3
"""Simulated encoder odometry and PID feedback publisher for navigation."""

from __future__ import annotations

import json
import math

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray, Int32MultiArray, String


class EncoderOdometryNode(Node):
    def __init__(self):
        super().__init__("encoder_odometry_node")
        self.declare_parameter("wheel_radius", 0.06)
        self.declare_parameter("lx_plus_ly", 0.4335)
        self.declare_parameter("ticks_per_revolution", 1024)

        self.wheel_radius = float(self.get_parameter("wheel_radius").value)
        self.lx_plus_ly = float(self.get_parameter("lx_plus_ly").value)
        self.ticks_per_revolution = int(self.get_parameter("ticks_per_revolution").value)
        self.tick_counts = [0, 0, 0, 0]

        self.create_subscription(Odometry, "/odom", self._odom_cb, 10)
        self.odom_pub = self.create_publisher(Odometry, "/wheel_odom", 10)
        self.tick_pub = self.create_publisher(Int32MultiArray, "/encoder_ticks", 10)
        self.pid_feedback_pub = self.create_publisher(Float32MultiArray, "/pid_feedback", 10)
        self.status_pub = self.create_publisher(String, "/encoder_odometry/status", 10)
        self.get_logger().info("Encoder odometry node started.")

    def _odom_cb(self, msg: Odometry):
        self.odom_pub.publish(msg)

        vx = msg.twist.twist.linear.x
        vy = msg.twist.twist.linear.y
        wz = msg.twist.twist.angular.z
        r = self.wheel_radius
        k = self.lx_plus_ly

        wheel_rads = [
            (vx - vy - k * wz) / r,
            -(vx + vy + k * wz) / r,
            (vx + vy - k * wz) / r,
            -(vx - vy + k * wz) / r,
        ]

        dt = 0.1
        ticks_per_rad = self.ticks_per_revolution / (2.0 * math.pi)
        self.tick_counts = [
            self.tick_counts[idx] + int(wheel_rads[idx] * dt * ticks_per_rad) for idx in range(4)
        ]

        ticks = Int32MultiArray()
        ticks.data = list(self.tick_counts)
        self.tick_pub.publish(ticks)

        feedback = Float32MultiArray()
        feedback.data = [float(value) for value in wheel_rads]
        self.pid_feedback_pub.publish(feedback)

        status = String()
        status.data = json.dumps({"ticks": self.tick_counts, "wheel_rads": wheel_rads})
        self.status_pub.publish(status)


def main(args=None):
    rclpy.init(args=args)
    node = EncoderOdometryNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()

