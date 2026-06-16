#!/usr/bin/env python3

import argparse
import time

from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


class BaseSessionReset(Node):
    def __init__(self) -> None:
        super().__init__("motivon_base_session_reset")
        self.cmd_vel_publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        self.enable_publisher = self.create_publisher(Bool, "/base/enable", 10)
        self.esp_reset_publisher = self.create_publisher(
            Bool, "/base/software_reset", 10
        )
        self.wheel_reset_client = self.create_client(
            Trigger, "/wheel_odometry/reset"
        )
        self.home_client = self.create_client(Trigger, "/navigation/set_home")

    def stop_base(self, duration_s: float = 0.5) -> None:
        disabled = Bool()
        disabled.data = False
        stop = Twist()
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            self.cmd_vel_publisher.publish(stop)
            self.enable_publisher.publish(disabled)
            rclpy.spin_once(self, timeout_sec=0.05)

    def wait_for_esp_subscription(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.esp_reset_publisher.get_subscription_count() > 0:
                return True
            rclpy.spin_once(self, timeout_sec=0.1)
        return False

    def esp_node_present(self) -> bool:
        return "esp32_base_node" in set(self.get_node_names())

    def request_esp_reset(self, timeout_s: float) -> bool:
        if not self.wait_for_esp_subscription(5.0):
            print(
                "ESP software reset unavailable "
                "(/base/software_reset has no subscriber)."
            )
            return False

        message = Bool()
        message.data = True
        print("Requesting ESP32 software reset...")
        for _ in range(10):
            self.esp_reset_publisher.publish(message)
            rclpy.spin_once(self, timeout_sec=0.05)

        missing_deadline = time.monotonic() + min(10.0, timeout_s)
        while time.monotonic() < missing_deadline and self.esp_node_present():
            rclpy.spin_once(self, timeout_sec=0.1)

        ready_deadline = time.monotonic() + timeout_s
        while time.monotonic() < ready_deadline:
            if self.esp_node_present():
                print("ESP32 node is back.")
                return True
            rclpy.spin_once(self, timeout_sec=0.2)

        print("Timed out waiting for esp32_base_node after software reset.")
        return False

    def call_trigger_service(
        self, client, name: str, timeout_s: float, required: bool
    ) -> bool:
        if not client.wait_for_service(timeout_sec=timeout_s):
            print(f"{name}: unavailable")
            return not required
        future = client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout_s)
        if not future.done() or future.result() is None:
            print(f"{name}: no response")
            return False
        response = future.result()
        print(
            f"{name}: {'OK' if response.success else 'FAIL'} "
            f"({response.message})"
        )
        return bool(response.success)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Reset ESP/base software state before a Motivon test."
    )
    parser.add_argument(
        "--skip-esp-reset",
        action="store_true",
        help="Do not request an ESP32 software reset.",
    )
    parser.add_argument(
        "--esp-timeout",
        type=float,
        default=45.0,
        help="Seconds to wait for esp32_base_node after reset.",
    )
    parser.add_argument(
        "--service-timeout",
        type=float,
        default=5.0,
        help="Seconds to wait for ROS reset services.",
    )
    parser.add_argument(
        "--set-home",
        action="store_true",
        help="Also call /navigation/set_home after resetting odometry.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.esp_timeout <= 0.0 or args.service_timeout <= 0.0:
        raise ValueError("Timeouts must be positive")

    rclpy.init()
    node = BaseSessionReset()
    try:
        node.stop_base()
        if not args.skip_esp_reset and not node.request_esp_reset(
            args.esp_timeout
        ):
            return 1

        node.stop_base()
        ok = node.call_trigger_service(
            node.wheel_reset_client,
            "/wheel_odometry/reset",
            args.service_timeout,
            required=False,
        )
        if args.set_home:
            ok = (
                node.call_trigger_service(
                    node.home_client,
                    "/navigation/set_home",
                    args.service_timeout,
                    required=True,
                )
                and ok
            )
        print("BASE SESSION RESET: " + ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
