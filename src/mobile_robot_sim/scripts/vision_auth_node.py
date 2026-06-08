#!/usr/bin/env python3
"""Manual vision event bridge for manager/user verification."""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import SetBool


class VisionAuthNode(Node):
    def __init__(self):
        super().__init__("vision_auth_node")
        self.pending_result = {"status": "verified", "identity": "expected"}
        self.result_pub = self.create_publisher(String, "/vision/result", 10)
        self.state_hint_pub = self.create_publisher(String, "/robot_state_hint", 10)
        self.create_subscription(String, "/vision/manual_result", self._manual_result_cb, 10)
        self.create_service(SetBool, "/vision/verify_manager", self._verify_manager_cb)
        self.create_service(SetBool, "/vision/verify_user", self._verify_user_cb)
        self.get_logger().info("Vision auth node started.")

    def _manual_result_cb(self, msg: String):
        try:
            self.pending_result = json.loads(msg.data)
        except json.JSONDecodeError:
            self.pending_result = {"status": msg.data}

    def _publish_result(self, role: str, requested: bool):
        state = String()
        state.data = json.dumps({"state": f"VERIFYING_{role.upper()}_FACE", "role": role})
        self.state_hint_pub.publish(state)

        payload = {
            "role": role,
            "requested": requested,
            "status": self.pending_result.get("status", "verified" if requested else "denied"),
            "identity": self.pending_result.get("identity", "expected"),
        }
        msg = String()
        msg.data = json.dumps(payload)
        self.result_pub.publish(msg)
        return payload

    def _verify_manager_cb(self, request: SetBool.Request, response: SetBool.Response):
        payload = self._publish_result("manager", request.data)
        response.success = payload["status"] == "verified"
        response.message = json.dumps(payload)
        return response

    def _verify_user_cb(self, request: SetBool.Request, response: SetBool.Response):
        payload = self._publish_result("user", request.data)
        response.success = payload["status"] == "verified"
        response.message = json.dumps(payload)
        return response


def main(args=None):
    rclpy.init(args=args)
    node = VisionAuthNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
