#!/usr/bin/env python3
"""Map robot state hints to LED strip modes."""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class StateLedNode(Node):
    def __init__(self):
        super().__init__("state_led_node")
        self.state_pub = self.create_publisher(String, "/led_state", 10)
        self.create_subscription(String, "/robot_state_hint", self._state_cb, 10)
        self.get_logger().info("State LED node started.")

    def _state_cb(self, msg: String):
        try:
            payload = json.loads(msg.data)
            state = payload.get("state", "UNKNOWN")
        except json.JSONDecodeError:
            state = msg.data

        mode = {
            "NAV_IDLE": {"color": "green", "pattern": "steady"},
            "NAV_READY": {"color": "cyan", "pattern": "steady"},
            "NAV_TO_CHECKPOINT": {"color": "blue", "pattern": "chase"},
            "NAV_TO_STATION": {"color": "blue", "pattern": "chase"},
            "NAV_RETURNING_HOME": {"color": "teal", "pattern": "chase"},
            "NAV_WAITING_DYNAMIC_CLEAR": {"color": "amber", "pattern": "pulse"},
            "NAV_DYNAMIC_CLEAR_BUFFER": {"color": "amber", "pattern": "slow-pulse"},
            "NAV_STATIC_AVOID_RIGHT": {"color": "orange", "pattern": "sweep-right"},
            "NAV_STATIC_AVOID_LEFT": {"color": "orange", "pattern": "sweep-left"},
            "NAV_COURSE_CORRECTING": {"color": "white", "pattern": "pulse"},
            "NAV_ALIGNING_YAW": {"color": "white", "pattern": "rotate"},
            "NAV_COMPLETE": {"color": "green", "pattern": "blink"},
            "NAV_FAULT": {"color": "red", "pattern": "blink-fast"},
            "NAV_ESTOP_PAUSED": {"color": "red", "pattern": "steady"},
            "VERIFYING_MANAGER_FACE": {"color": "white", "pattern": "pulse"},
            "VERIFYING_USER_FACE": {"color": "white", "pattern": "pulse"},
        }.get(state, {"color": "purple", "pattern": "steady"})

        out = String()
        out.data = json.dumps({"state": state, **mode})
        self.state_pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = StateLedNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()

