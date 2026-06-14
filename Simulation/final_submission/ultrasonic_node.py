#!/usr/bin/env python3
"""Aggregate ultrasonic readings into navigation-friendly distance topics."""

from __future__ import annotations

import json
import math

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Float32, String


class UltrasonicNode(Node):
    def __init__(self):
        super().__init__("ultrasonic_node")
        self.distances = {"front": 10.0, "back": 10.0, "left": 10.0, "right": 10.0}
        self.front_pub = self.create_publisher(Float32, "/ultrasonic/front_distance", 10)
        self.back_pub = self.create_publisher(Float32, "/ultrasonic/back_distance", 10)
        self.left_pub = self.create_publisher(Float32, "/ultrasonic/left_distance", 10)
        self.right_pub = self.create_publisher(Float32, "/ultrasonic/right_distance", 10)
        self.summary_pub = self.create_publisher(String, "/ultrasonic/distances", 10)

        self.create_subscription(LaserScan, "/ultrasonic/front", lambda msg: self._update("front", msg), 10)
        self.create_subscription(LaserScan, "/ultrasonic/back", lambda msg: self._update("back", msg), 10)
        self.create_subscription(LaserScan, "/ultrasonic/left", lambda msg: self._update("left", msg), 10)
        self.create_subscription(LaserScan, "/ultrasonic/right", lambda msg: self._update("right", msg), 10)
        self.get_logger().info("Ultrasonic node started.")

    @staticmethod
    def _min_range(msg: LaserScan) -> float:
        valid = [r for r in msg.ranges if math.isfinite(r) and r > 0.0]
        return min(valid) if valid else 10.0

    def _update(self, label: str, msg: LaserScan):
        self.distances[label] = self._min_range(msg)
        out = Float32()
        out.data = float(self.distances[label])
        {
            "front": self.front_pub,
            "back": self.back_pub,
            "left": self.left_pub,
            "right": self.right_pub,
        }[label].publish(out)

        summary = String()
        summary.data = json.dumps(self.distances)
        self.summary_pub.publish(summary)


def main(args=None):
    rclpy.init(args=args)
    node = UltrasonicNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()

