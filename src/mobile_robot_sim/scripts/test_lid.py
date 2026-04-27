#!/usr/bin/env python3
"""
Testing node: exercises the lid control.
Opens and closes the lid in a cycle using both the service and topic interfaces.
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
from std_srvs.srv import SetBool
import time


class TestLid(Node):
    def __init__(self):
        super().__init__('test_lid')

        # Direct topic publisher
        self.pub = self.create_publisher(
            Float64MultiArray, '/lid_controller/commands', 10)

        # Service client
        self.client = self.create_client(SetBool, '/lid_control')

        self.test_phase = 0
        self.phase_start = self.get_clock().now()

        self.timer = self.create_timer(0.5, self.test_loop)
        self.get_logger().info('TestLid node started. Cycling lid open/close...')

    def test_loop(self):
        elapsed = (self.get_clock().now() - self.phase_start).nanoseconds / 1e9

        if self.test_phase == 0:
            # Open lid via topic
            self.get_logger().info('Opening lid via topic (0.18m)')
            cmd = Float64MultiArray()
            cmd.data = [0.18]
            self.pub.publish(cmd)
            if elapsed > 3.0:
                self.test_phase = 1
                self.phase_start = self.get_clock().now()

        elif self.test_phase == 1:
            # Close lid via topic
            self.get_logger().info('Closing lid via topic (0.0m)')
            cmd = Float64MultiArray()
            cmd.data = [0.0]
            self.pub.publish(cmd)
            if elapsed > 3.0:
                self.test_phase = 2
                self.phase_start = self.get_clock().now()

        elif self.test_phase == 2:
            # Open lid via service
            if self.client.service_is_ready():
                req = SetBool.Request()
                req.data = True
                future = self.client.call_async(req)
                self.get_logger().info('Opening lid via service')
                self.test_phase = 3
                self.phase_start = self.get_clock().now()
            else:
                self.get_logger().info('Waiting for /lid_control service...')

        elif self.test_phase == 3:
            if elapsed > 3.0:
                # Close lid via service
                if self.client.service_is_ready():
                    req = SetBool.Request()
                    req.data = False
                    future = self.client.call_async(req)
                    self.get_logger().info('Closing lid via service')
                    self.test_phase = 4
                    self.phase_start = self.get_clock().now()

        elif self.test_phase == 4:
            if elapsed > 3.0:
                # Partial open via topic
                self.get_logger().info('Setting lid to half-open (0.09m)')
                cmd = Float64MultiArray()
                cmd.data = [0.09]
                self.pub.publish(cmd)
                if elapsed > 5.0:
                    self.get_logger().info('Lid test complete!')
                    self.timer.cancel()


def main(args=None):
    rclpy.init(args=args)
    node = TestLid()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
