#!/usr/bin/env python3

import argparse
import math
import time

from motivon_interfaces.action import NavigateToTarget
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Bool


TARGETS = ("WP1", "WP2", "WP3", "HOME")


class FullPathTest(Node):
    def __init__(self) -> None:
        super().__init__("full_path_navigation_test")
        self.action_client = ActionClient(
            self,
            NavigateToTarget,
            "/navigation/navigate_to_target",
        )
        self.enable_publisher = self.create_publisher(
            Bool, "/base/enable", 10
        )
        self.enable_requested = False
        self.create_timer(0.50, self._publish_enable_state)
        self.last_feedback_time = 0.0

    def _publish_enable_state(self) -> None:
        message = Bool()
        message.data = self.enable_requested
        self.enable_publisher.publish(message)

    def wait_for_enable_subscription(self, timeout_s: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self.enable_publisher.get_subscription_count() >= 1:
                return True
        return False

    def wait_for_navigation_command_path(
        self, timeout_s: float = 10.0
    ) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            publishers = self.get_publishers_info_by_topic("/cmd_vel")
            subscriptions = self.get_subscriptions_info_by_topic("/cmd_vel")
            navigation_connected = any(
                endpoint.node_name == "navigation_node"
                for endpoint in publishers
            )
            base_connected = any(
                endpoint.node_name == "esp32_base_node"
                for endpoint in subscriptions
            )
            if navigation_connected and base_connected:
                return True
        return False

    def enable_base(self) -> None:
        self.enable_requested = True
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            self._publish_enable_state()
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.03)

    def disable_base(self) -> None:
        self.enable_requested = False
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            self._publish_enable_state()
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.03)

    def feedback_callback(self, feedback_message) -> None:
        now = time.monotonic()
        if now - self.last_feedback_time < 0.5:
            return
        self.last_feedback_time = now
        feedback = feedback_message.feedback
        print(
            f"{feedback.state}: waypoint={feedback.active_waypoint}, "
            f"remaining={feedback.distance_remaining_m:.3f} m, "
            f"cross_track={feedback.cross_track_error_m:.3f} m, "
            f"yaw_error={math.degrees(feedback.yaw_error_rad):.2f} deg"
        )

    def run_target(
        self,
        target_name: str,
        hold_time_s: float,
        timeout_s: float,
    ) -> bool:
        goal = NavigateToTarget.Goal()
        goal.target_name = target_name
        goal.hold_time_s = hold_time_s

        print(f"Requesting {target_name}.")
        send_future = self.action_client.send_goal_async(
            goal,
            feedback_callback=self.feedback_callback,
        )
        rclpy.spin_until_future_complete(self, send_future, timeout_sec=10.0)
        if not send_future.done() or send_future.result() is None:
            print(f"{target_name}: FAIL (goal request timed out)")
            return False

        goal_handle = send_future.result()
        if not goal_handle.accepted:
            print(f"{target_name}: FAIL (goal rejected)")
            return False

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(
            self, result_future, timeout_sec=timeout_s
        )
        if not result_future.done() or result_future.result() is None:
            goal_handle.cancel_goal_async()
            print(f"{target_name}: FAIL (navigation timed out)")
            return False

        result = result_future.result().result
        print(
            f"{target_name}: status={result.status}, "
            f"x_error={result.final_x_error_m:.3f} m, "
            f"y_error={result.final_y_error_m:.3f} m, "
            f"yaw_error={math.degrees(result.final_yaw_error_rad):.2f} deg, "
            f"message={result.message}"
        )
        return result.status == NavigateToTarget.Result.STATUS_SUCCEEDED


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run the supervised HOME -> WP1 -> WP2 -> WP3 -> HOME test. "
            "The return path uses WP3b_ret and WP3a_ret, then finishes at "
            "HOME aligned to 180 degrees."
        )
    )
    parser.add_argument("--hold-time", type=float, default=10.0)
    parser.add_argument("--target-timeout", type=float, default=160.0)
    parser.add_argument(
        "--area-clear",
        action="store_true",
        help="Required confirmation that the complete route is clear.",
    )
    return parser.parse_args()


def main(args=None) -> int:
    parsed = parse_args()
    if not parsed.area_clear:
        raise SystemExit(
            "REFUSED: clear HOME -> WP1 -> WP2 -> WP3 -> HOME and "
            "add --area-clear"
        )
    if (
        not math.isfinite(parsed.hold_time)
        or parsed.hold_time < 0.0
        or not math.isfinite(parsed.target_timeout)
        or parsed.target_timeout <= 0.0
    ):
        raise SystemExit("Hold time and target timeout must be valid.")

    rclpy.init(args=args)
    node = FullPathTest()
    passed = False
    try:
        print("Waiting for the navigation action server.")
        if not node.action_client.wait_for_server(timeout_sec=10.0):
            print("FULL-PATH TEST: FAIL (action server unavailable)")
            return 1
        print("Checking navigation-to-ESP command routing.")
        if not node.wait_for_navigation_command_path():
            print(
                "FULL-PATH TEST: REFUSED "
                "(launch navigation with command_topic:=/cmd_vel)"
            )
            return 2
        print("Waiting for the ESP enable subscription.")
        if not node.wait_for_enable_subscription():
            print("FULL-PATH TEST: FAIL (ESP enable unavailable)")
            return 1
        node.enable_base()
        print("Base enable heartbeat active.")

        for target in TARGETS:
            if not node.run_target(
                target,
                parsed.hold_time,
                parsed.target_timeout,
            ):
                print(
                    f"FULL-PATH TEST: FAIL at {target}; "
                    "later targets were not requested."
                )
                return 1

        passed = True
        print("FULL-PATH TEST: PASS")
        return 0
    finally:
        node.disable_base()
        print("Base disabled.")
        node.destroy_node()
        rclpy.shutdown()
        if not passed:
            print("Physically verify the robot position before another test.")


if __name__ == "__main__":
    raise SystemExit(main())
