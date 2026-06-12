#!/usr/bin/env python3
"""
goal_sender_node.py

Publishes navigation goals to the robot navigator via /navigation_goals topic.
Goals are sent as a JSON-encoded String message with target positions, names,
and index sets that define the mission. The navigator subscribes to this topic
and uses the received goals instead of internal defaults.
"""

import json
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from std_msgs.msg import String


class GoalSenderNode(Node):

    def __init__(self):
        super().__init__('goal_sender_node')

        # ── Mission definition (all coords in Gazebo WORLD frame) ──
        self.mission = {
            'targets': [
                [2.5,   0.5],     # 0  T1
                [0.04,  1.01],    # 1  T2
                [-0.86, 1.60],    # 2  WP0
                [-1.75, 1.45],    # 3  T3
                [-2.76, 0.65],    # 4  T4
                [-2.76, 0.22],    # 5  WP1
                [-1.45, 0.22],    # 6  WP2
                [-0.55, -0.39],   # 7  T5
                [0.17,  -1.17],   # 8  WP3
                [1.50,  -1.20],   # 9  WP4
            ],
            'names': [
                'T1', 'T2', 'WP0', 'T3', 'T4',
                'WP1', 'WP2', 'T5', 'WP3', 'WP4',
            ],
            'lid_indices': [0, 1, 3, 4, 7],
            'forced_indices': [2, 5, 6, 8, 9],
            'rotate_indices': [0, 3, 5],
            'home': [2.5, -1.46],
        }

        # Transient-local so late-joining subscribers still receive the message.
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self._pub = self.create_publisher(String, '/navigation_goals', qos)

        # Publish once at startup, then keep re-publishing at 1 Hz.
        self._publish_goals()
        self._timer = self.create_timer(1.0, self._publish_goals)

        self.get_logger().info(
            f'Goal Sender started — publishing {len(self.mission["targets"])} '
            f'targets on /navigation_goals')

    def _publish_goals(self):
        msg = String()
        msg.data = json.dumps(self.mission)
        self._pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = GoalSenderNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
