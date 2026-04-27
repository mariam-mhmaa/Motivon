#!/usr/bin/env python3
"""
Testing node: sends various cmd_vel commands to exercise mecanum motion.
Cycles through: forward, strafe left, strafe right, rotate, diagonal, stop.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import time


class TestCmdVel(Node):
    def __init__(self):
        super().__init__('test_cmd_vel')

        self.pub = self.create_publisher(
            Twist, '/cmd_vel', 10)

        # Test sequence: (vx, vy, wz, duration_sec, description)
        self.tests = [
            (0.3, 0.0, 0.0, 3.0, 'Forward'),
            (0.0, 0.3, 0.0, 3.0, 'Strafe Left'),
            (0.0, -0.3, 0.0, 3.0, 'Strafe Right'),
            (0.0, 0.0, 0.5, 3.0, 'Rotate CW'),
            (0.2, 0.2, 0.0, 3.0, 'Diagonal Forward-Left'),
            (-0.3, 0.0, 0.0, 3.0, 'Backward'),
            (0.0, 0.0, 0.0, 2.0, 'Stop'),
        ]
        self.test_idx = 0
        self.test_start_time = self.get_clock().now()

        self.timer = self.create_timer(0.1, self.test_loop)
        self.get_logger().info('TestCmdVel node started. Running motion tests...')

    def test_loop(self):
        if self.test_idx >= len(self.tests):
            self.get_logger().info('All tests completed!')
            self._send(0.0, 0.0, 0.0)
            self.timer.cancel()
            return

        vx, vy, wz, duration, desc = self.tests[self.test_idx]
        elapsed = (self.get_clock().now() - self.test_start_time).nanoseconds / 1e9

        if elapsed > duration:
            self.get_logger().info(f'Test "{desc}" complete.')
            self.test_idx += 1
            self.test_start_time = self.get_clock().now()
            return

        if elapsed < 0.2:
            self.get_logger().info(f'Running test: {desc} (vx={vx}, vy={vy}, wz={wz})')

        self._send(vx, vy, wz)

    def _send(self, vx, vy, wz):
        cmd = Twist()
        cmd.linear.x = vx
        cmd.linear.y = vy
        cmd.angular.z = wz
        self.pub.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    node = TestCmdVel()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
