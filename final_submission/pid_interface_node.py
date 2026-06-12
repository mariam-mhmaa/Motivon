#!/usr/bin/env python3
"""Publish wheel PID targets and optional ESP32 status polling hooks."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray, String


class PidInterfaceNode(Node):
    def __init__(self):
        super().__init__("pid_interface_node")
        self.declare_parameter("wheel_radius", 0.06)
        self.declare_parameter("lx_plus_ly", 0.4335)
        self.declare_parameter("transport_mode", "simulation")
        self.declare_parameter("esp32_status_url", "")
        self.declare_parameter("status_period_sec", 1.0)

        self.wheel_radius = float(self.get_parameter("wheel_radius").value)
        self.lx_plus_ly = float(self.get_parameter("lx_plus_ly").value)
        self.transport_mode = str(self.get_parameter("transport_mode").value)
        self.status_url = str(self.get_parameter("esp32_status_url").value)

        self.target_pub = self.create_publisher(Float32MultiArray, "/pid/wheel_targets", 10)
        self.state_pub = self.create_publisher(String, "/pid/state", 10)
        self.telemetry_pub = self.create_publisher(String, "/pid/telemetry", 10)
        self.create_subscription(Twist, "/cmd_vel", self._cmd_cb, 10)

        period = float(self.get_parameter("status_period_sec").value)
        if self.status_url:
            self.create_timer(period, self._poll_status)
        self.get_logger().info(f"PID interface node started in {self.transport_mode} mode.")

    def _cmd_cb(self, msg: Twist):
        r = self.wheel_radius
        k = self.lx_plus_ly
        wheel_rads = [
            (msg.linear.x - msg.linear.y - k * msg.angular.z) / r,
            -(msg.linear.x + msg.linear.y + k * msg.angular.z) / r,
            (msg.linear.x + msg.linear.y - k * msg.angular.z) / r,
            -(msg.linear.x - msg.linear.y + k * msg.angular.z) / r,
        ]

        out = Float32MultiArray()
        out.data = [float(value) for value in wheel_rads]
        self.target_pub.publish(out)

        state = String()
        state.data = json.dumps(
            {
                "transport_mode": self.transport_mode,
                "cmd_vel": {"vx": msg.linear.x, "vy": msg.linear.y, "wz": msg.angular.z},
                "wheel_targets": wheel_rads,
            }
        )
        self.state_pub.publish(state)

    def _poll_status(self):
        try:
            with urllib.request.urlopen(self.status_url, timeout=0.5) as response:
                payload = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            payload = json.dumps({"ok": False, "error": str(exc)})
        msg = String()
        msg.data = payload
        self.telemetry_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = PidInterfaceNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()

