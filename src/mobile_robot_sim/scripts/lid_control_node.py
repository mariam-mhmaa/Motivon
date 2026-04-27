#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64, Bool
from sensor_msgs.msg import JointState
from std_srvs.srv import SetBool


class LidControlNode(Node):
    """
    Controls the prismatic lid joint via Gazebo's native JointPositionController.
    Publishes desired position as Float64 to /lid_position (bridged to Gazebo).
    Provides /lid_control service (SetBool: true=open, false=close).
    """

    LID_OPEN = 0.14      # metres – must match URDF upper limit exactly
    LID_CLOSED = 0.0     # metres – URDF lower limit

    LID_OPEN_DURATION = 10.0  # seconds before auto-close

    def __init__(self):
        super().__init__('lid_control_node')

        # Publisher to Gazebo JointPositionController via bridge
        self.pub = self.create_publisher(Float64, '/lid_position', 10)

        # Service: SetBool (true = open, false = close)
        self.srv = self.create_service(
            SetBool, '/lid_control', self.lid_service_cb)

        # Publish closed position at 2 Hz
        self.target = self.LID_CLOSED
        self.timer = self.create_timer(0.5, self.publish_position)

        # One-shot timer for auto-close (created on demand)
        self._auto_close_timer = None

        # Publish lid closed state for navigator
        self._closed_pub = self.create_publisher(Bool, '/lid_closed', 1)
        self._lid_pos = 0.0
        self.create_subscription(JointState, '/joint_states', self._js_cb, 10)

        self.get_logger().info('Lid Control Node started. Service: /lid_control')

    def lid_service_cb(self, request, response):
        if request.data:
            self.target = self.LID_OPEN
            response.message = 'Lid opened (will auto-close in 10 s)'
            self.get_logger().info('Lid OPENED via service – auto-close in 10 s')
            # Cancel any existing auto-close timer, then start a new one
            if self._auto_close_timer is not None:
                self._auto_close_timer.cancel()
            self._auto_close_timer = self.create_timer(
                self.LID_OPEN_DURATION, self._auto_close_cb)
        else:
            self._cancel_auto_close()
            self.target = self.LID_CLOSED
            response.message = 'Lid closed'
            self.get_logger().info('Lid CLOSED via service')
        response.success = True
        return response

    def _auto_close_cb(self):
        self.target = self.LID_CLOSED
        self.get_logger().info('Lid AUTO-CLOSED after 10 s')
        self._cancel_auto_close()

    def _cancel_auto_close(self):
        if self._auto_close_timer is not None:
            self._auto_close_timer.cancel()
            self._auto_close_timer = None

    def _js_cb(self, msg):
        try:
            idx = msg.name.index('Lid_Joint')
            self._lid_pos = msg.position[idx]
        except ValueError:
            pass
        closed = Bool()
        closed.data = (self._lid_pos <= 0.005)
        self._closed_pub.publish(closed)

    def publish_position(self):
        msg = Float64()
        msg.data = self.target
        self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = LidControlNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
