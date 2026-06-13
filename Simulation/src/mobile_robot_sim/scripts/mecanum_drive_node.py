#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Float64MultiArray


class MecanumDriveNode(Node):
    """
    Subscribes to /cmd_vel (Twist).
    Converts (vx, vy, wz) to 4 individual wheel velocities using mecanum kinematics.
    Publishes as Float64MultiArray to /wheel_velocity_controller/commands.
    """

    def __init__(self):
        super().__init__('mecanum_drive_node')

        # Robot parameters
        self.wheel_radius = 0.06  # meters
        # lx + ly = half-wheelbase-x + half-wheelbase-y = 0.1975 + 0.236 = 0.4335
        self.lx_plus_ly = 0.4335

        # Subscribe to plain Twist on /cmd_vel
        self.sub_twist = self.create_subscription(
            Twist, '/cmd_vel', self.cmd_vel_callback, 10)

        # Publish wheel velocities to JointGroupVelocityController
        # Order must match joints list in controllers.yaml: FL, FR, RL, RR
        self.pub_wheels = self.create_publisher(
            Float64MultiArray, '/wheel_velocity_controller/commands', 10)

        self.get_logger().info('Mecanum Drive Node started.')

    def cmd_vel_callback(self, msg: Twist):
        self._compute_and_publish(msg.linear.x, msg.linear.y, msg.angular.z)

    def _compute_and_publish(self, vx: float, vy: float, wz: float):
        """
        Mecanum inverse kinematics:
          w_fl = (1/r) * (vx - vy - (lx+ly)*wz)
          w_fr = (1/r) * (vx + vy + (lx+ly)*wz)
          w_rl = (1/r) * (vx + vy - (lx+ly)*wz)
          w_rr = (1/r) * (vx - vy + (lx+ly)*wz)
        """
        r = self.wheel_radius
        k = self.lx_plus_ly

        # NOTE: FR and RR are negated because in the URDF the right-side
        # wheel joints have axis [0,0,1] (maps to -Y in parent frame),
        # opposite to the left-side [0,0,-1] (maps to +Y).  A positive
        # velocity command on the right side therefore spins the wheel
        # backward; negating corrects for this.
        w_fl = (1.0 / r) * (vx - vy - k * wz)
        w_fr = -(1.0 / r) * (vx + vy + k * wz)
        w_rl = (1.0 / r) * (vx + vy - k * wz)
        w_rr = -(1.0 / r) * (vx - vy + k * wz)

        cmd = Float64MultiArray()
        cmd.data = [w_fl, w_fr, w_rl, w_rr]
        self.pub_wheels.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    node = MecanumDriveNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
