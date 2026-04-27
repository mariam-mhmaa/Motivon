#!/usr/bin/env python3
"""
Testing node: monitors ultrasonic sensor data and logs obstacle detection.
Useful for verifying that the 4 ultrasonic sensors are working and
that the obstacle avoidance node is responding correctly.
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import Twist
import numpy as np


class TestObstacle(Node):
    def __init__(self):
        super().__init__('test_obstacle')

        self.distances = {
            'front': 10.0,
            'back': 10.0,
            'left': 10.0,
            'right': 10.0,
        }

        # Subscribe to all ultrasonic sensors
        self.sub_front = self.create_subscription(
            LaserScan, '/ultrasonic/front', lambda m: self._cb(m, 'front'), 10)
        self.sub_back = self.create_subscription(
            LaserScan, '/ultrasonic/back', lambda m: self._cb(m, 'back'), 10)
        self.sub_left = self.create_subscription(
            LaserScan, '/ultrasonic/left', lambda m: self._cb(m, 'left'), 10)
        self.sub_right = self.create_subscription(
            LaserScan, '/ultrasonic/right', lambda m: self._cb(m, 'right'), 10)

        # Drive forward to test obstacle detection
        self.cmd_pub = self.create_publisher(
            Twist, '/cmd_vel', 10)

        self.timer = self.create_timer(0.5, self.monitor_loop)
        self.drive_timer = self.create_timer(0.1, self.drive_loop)

        self.test_active = True
        self.get_logger().info('TestObstacle node started. Driving forward and monitoring sensors.')

    def _cb(self, msg: LaserScan, direction: str):
        ranges = np.array(msg.ranges)
        ranges = np.nan_to_num(ranges, nan=10.0, posinf=10.0, neginf=10.0)
        self.distances[direction] = float(np.min(ranges)) if len(ranges) > 0 else 10.0

    def monitor_loop(self):
        self.get_logger().info(
            f'Distances -> F: {self.distances["front"]:.2f}m '
            f'B: {self.distances["back"]:.2f}m '
            f'L: {self.distances["left"]:.2f}m '
            f'R: {self.distances["right"]:.2f}m')

        # Check for close obstacles
        for direction, dist in self.distances.items():
            if dist < 0.5:
                self.get_logger().warn(
                    f'OBSTACLE DETECTED {direction.upper()}: {dist:.2f}m')

    def drive_loop(self):
        if not self.test_active:
            return

        # Check if obstacle is very close in front
        if self.distances['front'] < 0.3:
            self.get_logger().info('Obstacle too close! Stopping.')
            self.test_active = False
            cmd = Twist()
            self.cmd_pub.publish(cmd)
            return

        cmd = Twist()
        cmd.linear.x = 0.2
        self.cmd_pub.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    node = TestObstacle()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
