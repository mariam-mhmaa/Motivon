#!/usr/bin/env python3
"""
Movement test script for the DeliveryRobot mecanum drive.
Sequentially tests all directions with a 2-second move and 1-second stop between each.
Run AFTER the simulation is fully launched and nodes are ready.

Usage:
  ros2 run mobile_robot_sim test_movements.py
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_srvs.srv import SetBool
import time


class MovementTester(Node):
    def __init__(self):
        super().__init__('movement_tester')
        self.pub = self.create_publisher(Twist, '/cmd_vel_input', 10)
        self.enable_client = self.create_client(SetBool, '/robot_enable')

    def enable_robot(self, enabled: bool):
        while not self.enable_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().warn('Waiting for /robot_enable service...')
        req = SetBool.Request()
        req.data = enabled
        future = self.enable_client.call_async(req)
        rclpy.spin_until_future_complete(self, future)
        result = future.result()
        state = 'ENABLED' if enabled else 'DISABLED'
        self.get_logger().info(f'Robot {state}: {result.message}')

    def send_vel(self, vx=0.0, vy=0.0, wz=0.0):
        msg = Twist()
        msg.linear.x = vx
        msg.linear.y = vy
        msg.angular.z = wz
        self.pub.publish(msg)

    def move(self, label: str, vx=0.0, vy=0.0, wz=0.0, duration=2.0):
        self.get_logger().info(f'--- {label} ---')
        end = time.time() + duration
        while time.time() < end:
            self.send_vel(vx, vy, wz)
            time.sleep(0.1)
        # Stop
        self.send_vel()
        time.sleep(1.0)


def main():
    rclpy.init()
    node = MovementTester()

    # Enable robot first
    node.enable_robot(True)
    time.sleep(0.5)

    tests = [
        ('FORWARD         (linear.x = +0.3)',  0.3,  0.0,  0.0),
        ('BACKWARD        (linear.x = -0.3)', -0.3,  0.0,  0.0),
        ('STRAFE LEFT     (linear.y = -0.3)',  0.0, -0.3,  0.0),
        ('STRAFE RIGHT    (linear.y = +0.3)',  0.0,  0.3,  0.0),
        ('DIAGONAL FWD-L  (x=+0.3, y=-0.3)',  0.3, -0.3,  0.0),
        ('DIAGONAL FWD-R  (x=+0.3, y=+0.3)',  0.3,  0.3,  0.0),
        ('DIAGONAL BWD-L  (x=-0.3, y=-0.3)', -0.3, -0.3,  0.0),
        ('DIAGONAL BWD-R  (x=-0.3, y=+0.3)', -0.3,  0.3,  0.0),
        ('ROTATE CCW      (angular.z = +0.5)', 0.0,  0.0,  0.5),
        ('ROTATE CW       (angular.z = -0.5)', 0.0,  0.0, -0.5),
    ]

    for label, vx, vy, wz in tests:
        node.move(label, vx, vy, wz, duration=10.0)

    node.get_logger().info('All tests done. Disabling robot.')
    node.send_vel()
    node.enable_robot(False)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
