#!/usr/bin/env python3
"""
dynamic_obstacle_node.py

Spawns two dynamic obstacles that suddenly block the robot's path.

Behaviour:
  - Monitors robot position via /odom (LOCAL odom frame: origin = spawn point).
  - Obstacle 1: triggers during T1->T2 leg.  Spawns at world (0.87, 0.53).
  - Obstacle 2: triggers during RETURN leg.  Spawns at world (0.83, -1.26).
  - On trigger: spawns red box, publishes True on /dynamic_obstacle.
  - After 6 s: removes box, publishes False on /dynamic_obstacle.
  - Robot navigator subscribes to /dynamic_obstacle and stops while True.

Coordinate notes:
  - trigger_pos is in LOCAL odom frame (origin = robot spawn point).
  - spawn_pos is in WORLD frame (used by gz service).
  - Obstacle 1: local(1.99, 1.63) [world(0.87,  0.53)] - triggers on T1->T2 leg
  - Obstacle 2: local(0.20, 1.67) [world(0.83, -1.26)] - triggers on return leg
"""

import math
import subprocess

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from std_msgs.msg import Bool


class DynamicObstacleNode(Node):

    WORLD_NAME = 'my_world'

    TRIGGERS = [
        {
            'name': 'dynamic_obs_1',
            'trigger_pos': (1.99, 1.63),  # LOCAL odom frame
            'trigger_radius': 1.0,
            'spawn_pos': (0.87, 0.53, 0.25),
            'duration': 6.0,
            'spawned': False,
            'removed': False,
            'spawn_time': None,
            'removal_started': False,
            'removal_time': None,
        },
        {
            'name': 'dynamic_obs_2',
            'trigger_pos': (0.20, 1.67),  # LOCAL odom frame
            'trigger_radius': 1.0,
            'spawn_pos': (0.83, -1.26, 0.25),
            'duration': 6.0,
            'spawned': False,
            'removed': False,
            'spawn_time': None,
            'removal_started': False,
            'removal_time': None,
        },
    ]

    def __init__(self):
        super().__init__('dynamic_obstacle_node')

        self.robot_x = 0.0
        self.robot_y = 0.0
        self.odom_received = False
        self._active_count = 0

        self.create_subscription(Odometry, '/odom', self.odom_cb, 10)
        self.create_subscription(
            Odometry, '/odometry/filtered', self.odom_cb, 10)

        self._obstacle_pub = self.create_publisher(Bool, '/dynamic_obstacle', 10)

        self.timer = self.create_timer(0.25, self.check_triggers)

        self.get_logger().info(
            'Dynamic Obstacle Node started - monitoring robot position.')

    def odom_cb(self, msg: Odometry):
        self.robot_x = msg.pose.pose.position.x
        self.robot_y = msg.pose.pose.position.y
        self.odom_received = True


    def check_triggers(self):
        if not self.odom_received:
            return

        now = self.get_clock().now()

        for obs in self.TRIGGERS:
            if obs['removed']:
                continue

            tx, ty = obs['trigger_pos']
            dist = math.sqrt(
                (self.robot_x - tx) ** 2 + (self.robot_y - ty) ** 2)

            if not obs['spawned'] and dist < obs['trigger_radius']:
                self._spawn(obs)
                obs['spawned'] = True
                obs['spawn_time'] = now
                self._active_count += 1
                self._publish_state()
                self.get_logger().info(
                    f"Spawned {obs['name']} at world{obs['spawn_pos']} "
                    f"(robot dist={dist:.2f} m) - blocking for "
                    f"{obs['duration']:.0f} s")

            elif obs['spawned'] and not obs['removed']:
                elapsed = (now - obs['spawn_time']).nanoseconds / 1e9
                if elapsed >= obs['duration']:
                    if not obs['removal_started']:
                        # Phase 1: fire the gz service call (Popen, non-blocking)
                        self._remove(obs)
                        obs['removal_started'] = True
                        obs['removal_time'] = now
                        self.get_logger().info(
                            f"Removing {obs['name']} (elapsed {elapsed:.1f} s) "
                            f"- waiting for Gazebo to delete model...")
                    else:
                        # Phase 2: 0.5 s after the removal call, publish False
                        # so the navigator only resumes once the model is gone
                        removal_elapsed = (now - obs['removal_time']).nanoseconds / 1e9
                        if removal_elapsed >= 0.5:
                            obs['removed'] = True
                            self._active_count = max(0, self._active_count - 1)
                            self._publish_state()
                            self.get_logger().info(
                                f"Removed {obs['name']} - robot may resume")

    def _publish_state(self):
        msg = Bool()
        msg.data = (self._active_count > 0)
        self._obstacle_pub.publish(msg)

    def _spawn(self, obs):
        x, y, z = obs['spawn_pos']
        name = obs['name']
        sdf = (
            "<sdf version='1.6'>"
            f"<model name='{name}'>"
            "<static>true</static>"
            "<link name='link'>"
            "<visual name='visual'>"
            "<geometry><box><size>0.4 0.4 0.5</size></box></geometry>"
            "<material>"
            "<ambient>0.616 0.027 0.349 1</ambient>"
            "<diffuse>0.616 0.027 0.349 1</diffuse>"
            "</material>"
            "</visual>"
            "<collision name='collision'>"
            "<geometry><box><size>0.4 0.4 0.5</size></box></geometry>"
            "</collision>"
            "</link>"
            "</model>"
            "</sdf>"
        )
        req = (
            f'sdf: "{sdf}", '
            f'pose: {{position: {{x: {x}, y: {y}, z: {z}}}}}'
        )
        self._gz_service(
            f'/world/{self.WORLD_NAME}/create',
            'gz.msgs.EntityFactory',
            'gz.msgs.Boolean',
            req,
        )


    def _remove(self, obs):
        req = f'name: "{obs["name"]}", type: 2'
        self._gz_service(
            f'/world/{self.WORLD_NAME}/remove',
            'gz.msgs.Entity',
            'gz.msgs.Boolean',
            req,
        )

    def _gz_service(self, service, reqtype, reptype, req):
        cmd = [
            'gz', 'service',
            '-s', service,
            '--reqtype', reqtype,
            '--reptype', reptype,
            '--timeout', '2000',
            '--req', req,
        ]
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            self.get_logger().error(f'gz service call failed: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = DynamicObstacleNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
