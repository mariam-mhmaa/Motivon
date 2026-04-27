#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import Twist
import numpy as np
import time


class ObstacleAvoidance(Node):
    def __init__(self):
        super().__init__('obstacle_avoidance')

        # Safe distance threshold (in meters)
        self.safe_distance = 0.5
        self.critical_distance = 0.25

        # Store the latest distances (Initialize safely at 10 meters)
        self.dist_front = 10.0
        self.dist_back = 10.0
        self.dist_left = 10.0
        self.dist_right = 10.0

        # Dynamic obstacle tracking
        self.prev_dist_front = 10.0
        self.obstacle_moving = False
        self.stopped_for_dynamic = False
        self.dynamic_wait_start = None
        self.dynamic_clear_threshold = 0.8  # Resume if obstacle moves away beyond this

        # 1. Subscribe to all 4 Ultrasonic Sensors
        self.sub_front = self.create_subscription(LaserScan, '/ultrasonic/front', self.front_callback, 10)
        self.sub_back = self.create_subscription(LaserScan, '/ultrasonic/back', self.back_callback, 10)
        self.sub_left = self.create_subscription(LaserScan, '/ultrasonic/left', self.left_callback, 10)
        self.sub_right = self.create_subscription(LaserScan, '/ultrasonic/right', self.right_callback, 10)

        # 2. Subscribe to incoming velocity commands
        self.cmd_input_sub = self.create_subscription(
            Twist, '/cmd_vel_nav', self.nav_cmd_callback, 10)
        self.nav_cmd = None

        # 3. Publish velocity commands (mecanum_drive_node subscribes to /cmd_vel)
        self.publisher = self.create_publisher(Twist, '/cmd_vel', 10)

        # 4. Create a timer to run the control loop 10 times a second (10 Hz)
        self.timer = self.create_timer(0.1, self.control_loop)

        self.get_logger().info("Mecanum Obstacle Avoidance Node Started! Ready to strafe.")

    # --- Sensor Callbacks ---
    def get_min_range(self, msg):
        """Helper function to extract the closest object from the sensor array."""
        ranges = np.array(msg.ranges)
        # Clean up the data (replace NaNs or Infs with max distance)
        ranges = np.nan_to_num(ranges, nan=10.0, posinf=10.0, neginf=10.0)
        if len(ranges) == 0:
            return 10.0
        return float(np.min(ranges))

    def front_callback(self, msg):
        self.prev_dist_front = self.dist_front
        self.dist_front = self.get_min_range(msg)
        # Detect if the obstacle is moving (distance changing rapidly)
        delta = abs(self.dist_front - self.prev_dist_front)
        self.obstacle_moving = delta > 0.03  # Moving if distance changes > 3cm per reading

    def back_callback(self, msg):  self.dist_back = self.get_min_range(msg)
    def left_callback(self, msg):  self.dist_left = self.get_min_range(msg)
    def right_callback(self, msg): self.dist_right = self.get_min_range(msg)

    def nav_cmd_callback(self, msg: Twist):
        self.nav_cmd = msg

    # --- The Brain (Control Logic) ---
    def control_loop(self):
        cmd = Twist()

        # Base speeds
        linear_x = 0.0
        linear_y = 0.0
        angular_z = 0.0

        # --- DYNAMIC OBSTACLE HANDLING ---
        # If we detected a dynamic obstacle in front, STOP and wait for it to clear
        if self.stopped_for_dynamic:
            if self.dist_front > self.dynamic_clear_threshold:
                self.get_logger().info(
                    f"Dynamic obstacle cleared (dist={self.dist_front:.2f}m). Resuming.")
                self.stopped_for_dynamic = False
                self.dynamic_wait_start = None
            else:
                self.get_logger().info(
                    f"Waiting for dynamic obstacle to clear... (dist={self.dist_front:.2f}m)")
                # Publish zero velocity (stay stopped)
                self.publisher.publish(cmd)
                return

        # --- STATIC + DYNAMIC OBSTACLE DETECTION ---
        if self.dist_front < self.safe_distance:
            if self.obstacle_moving and self.dist_front < self.critical_distance:
                # Dynamic obstacle detected very close - STOP and wait
                self.get_logger().info(
                    f"DYNAMIC obstacle detected FRONT ({self.dist_front:.2f}m)! Stopping to wait.")
                self.stopped_for_dynamic = True
                self.dynamic_wait_start = self.get_clock().now()
                self.publisher.publish(cmd)
                return

            # Static obstacle handling - strafe around it
            self.get_logger().info(
                f"Obstacle in FRONT ({self.dist_front:.2f}m)! Deciding where to strafe...")

            if self.dist_left > self.dist_right:
                self.get_logger().info("-> Strafing LEFT!")
                linear_y = 0.4
            elif self.dist_right > self.dist_left:
                self.get_logger().info("-> Strafing RIGHT!")
                linear_y = -0.4
            else:
                self.get_logger().info("-> Trapped! Backing up!")
                linear_x = -0.3

        elif self.dist_back < self.critical_distance:
            self.get_logger().info(f"Obstacle BEHIND ({self.dist_back:.2f}m)! Moving forward.")
            linear_x = 0.3

        else:
            # Path clear - use navigation command if available, else move forward
            if self.nav_cmd is not None:
                linear_x = self.nav_cmd.linear.x
                linear_y = self.nav_cmd.linear.y
                angular_z = self.nav_cmd.angular.z
            else:
                linear_x = 0.3

            # Micro-corrections: Keep the robot centered if driving down a hallway
            if self.dist_left < 0.3:
                linear_y = -0.2
            elif self.dist_right < 0.3:
                linear_y = 0.2

        # Package the commands and send them to the wheels
        cmd.twist.linear.x = linear_x
        cmd.twist.linear.y = linear_y
        cmd.twist.angular.z = angular_z

        self.publisher.publish(cmd)

def main(args=None):
    rclpy.init(args=args)
    node = ObstacleAvoidance()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()