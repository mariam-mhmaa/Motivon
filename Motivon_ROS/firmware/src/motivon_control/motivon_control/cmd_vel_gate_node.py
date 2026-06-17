#!/usr/bin/env python3

from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from motivon_interfaces.msg import NavigationStatus, ObstacleState
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String

from motivon_control.gate_logic import choose_gate_state, normalize_mode


class CmdVelGateNode(Node):
    """Select the one velocity command stream allowed to reach the ESP32."""

    def __init__(self):
        super().__init__("cmd_vel_gate_node")

        self.declare_parameter("mode", "AUTO")
        self.declare_parameter("publish_rate_hz", 25.0)
        self.declare_parameter("command_stale_timeout_s", 0.50)
        self.declare_parameter("require_obstacle_fresh_in_auto", True)

        self.mode = normalize_mode(str(self.get_parameter("mode").value))
        self.command_stale_timeout_s = float(
            self.get_parameter("command_stale_timeout_s").value
        )
        self.require_obstacle_fresh_in_auto = bool(
            self.get_parameter("require_obstacle_fresh_in_auto").value
        )

        self.navigation_command = Twist()
        self.manual_command = Twist()
        self.navigation_time_s: Optional[float] = None
        self.manual_time_s: Optional[float] = None
        self.obstacle_blocks_auto = False
        self.obstacle_state = "UNKNOWN"
        self.obstacle_static = False
        self.navigation_state = "UNKNOWN"
        self.safety_stop = False
        self.last_reason = ""

        self.cmd_pub = self.create_publisher(
            Twist, "/cmd_vel", qos_profile_sensor_data
        )
        self.status_pub = self.create_publisher(
            String, "/cmd_vel_gate/status", 10
        )
        self.create_subscription(
            Twist,
            "/navigation/cmd_vel_raw",
            self.on_navigation_command,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            Twist,
            "/manual/cmd_vel",
            self.on_manual_command,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            ObstacleState,
            "/obstacle/state",
            self.on_obstacle_state,
            10,
        )
        self.create_subscription(
            NavigationStatus,
            "/navigation/status",
            self.on_navigation_status,
            10,
        )
        self.create_subscription(String, "/system/mode", self.on_mode, 10)
        self.create_subscription(String, "/safety/state", self.on_safety, 10)

        rate = float(self.get_parameter("publish_rate_hz").value)
        self.create_timer(1.0 / rate, self.publish_selected_command)
        self.get_logger().info("cmd_vel gate ready: AUTO obeys obstacle state; MANUAL bypasses obstacles.")

    def now_s(self) -> float:
        return self.get_clock().now().nanoseconds / 1_000_000_000.0

    def on_navigation_command(self, msg: Twist):
        self.navigation_command = msg
        self.navigation_time_s = self.now_s()

    def on_manual_command(self, msg: Twist):
        self.manual_command = msg
        self.manual_time_s = self.now_s()

    def on_obstacle_state(self, msg: ObstacleState):
        self.obstacle_state = msg.state
        self.obstacle_static = msg.static_obstacle
        self.obstacle_blocks_auto = (
            msg.blocked
            or (
                self.require_obstacle_fresh_in_auto
                and not msg.data_valid
            )
        )

    def on_navigation_status(self, msg: NavigationStatus):
        self.navigation_state = msg.state

    def on_mode(self, msg: String):
        self.mode = normalize_mode(msg.data)

    def on_safety(self, msg: String):
        self.safety_stop = msg.data.strip().upper() not in (
            "",
            "OK",
            "CLEAR",
            "READY",
        )

    def command_fresh(self, stamp_s: Optional[float], now_s: float) -> bool:
        return (
            stamp_s is not None
            and now_s - stamp_s <= self.command_stale_timeout_s
        )

    def publish_selected_command(self):
        now_s = self.now_s()
        decision = choose_gate_state(
            mode=self.mode,
            safety_stop=self.safety_stop,
            obstacle_blocks_auto=(
                self.obstacle_blocks_auto
                and not (
                    self.obstacle_static
                    and self.navigation_state == "DETOURING"
                )
            ),
            navigation_fresh=self.command_fresh(
                self.navigation_time_s, now_s
            ),
            manual_fresh=self.command_fresh(self.manual_time_s, now_s),
        )

        if decision.source == "navigation":
            command = self.navigation_command
        elif decision.source == "manual":
            command = self.manual_command
        else:
            command = Twist()
        self.cmd_pub.publish(command)

        if decision.reason != self.last_reason:
            self.get_logger().warning(
                f"cmd_vel gate: source={decision.source}, "
                f"mode={self.mode}, reason={decision.reason}, "
                f"obstacle={self.obstacle_state}, "
                f"navigation={self.navigation_state}"
            )
            self.last_reason = decision.reason

        status = String()
        status.data = (
            f"source={decision.source};mode={self.mode};"
            f"reason={decision.reason};obstacle={self.obstacle_state};"
            f"navigation={self.navigation_state}"
        )
        self.status_pub.publish(status)


def main(args=None):
    rclpy.init(args=args)
    node = CmdVelGateNode()
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
