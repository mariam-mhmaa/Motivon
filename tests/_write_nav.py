#!/usr/bin/env python3
"""Helper: writes robot_navigator_node.py v11b - updated T4 coordinates."""
import os, stat

TARGET = os.path.expanduser(
    '~/design_ws/src/mobile_robot_sim/scripts/robot_navigator_node.py')

CONTENT = '''\
#!/usr/bin/env python3
"""
robot_navigator_node.py  -  Phase 1

Diagonal target navigation with per-axis obstacle gating and lid control.
Uses mecanum omnidirectional drive - no rotation needed for navigation.

State machine:
  INIT -> NAVIGATING -> LID_OPENING -> WAITING (15 s) -> LID_CLOSING ->
    NAVIGATING (next target) -> ... -> RETURNING -> ALIGNING -> IDLE

Run:
  ros2 run mobile_robot_sim robot_navigator_node.py --ros-args -p use_sim_time:=true
"""

import math

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from std_srvs.srv import SetBool


class RobotNavigatorNode(Node):

    STATE_INIT = 'INIT'
    STATE_NAVIGATING = 'NAVIGATING'
    STATE_LID_OPENING = 'LID_OPENING'
    STATE_WAITING = 'WAITING'
    STATE_LID_CLOSING = 'LID_CLOSING'
    STATE_RETURNING = 'RETURNING'
    STATE_ALIGNING = 'ALIGNING'
    STATE_IDLE = 'IDLE'

    SPAWN_X = 2.5
    SPAWN_Y = -1.46
    SPAWN_YAW = math.pi / 2.0

    WORLD_TARGETS = [
        (2.5, 0.5),
        (0.04, 1.01),
        (-1.75, 1.38),
        (-2.76, 0.65),
    ]

    VERSION = 'v11b'
    GOAL_TOLERANCE = 0.10

    SAFE_DISTANCE = 0.80
    WARN_DISTANCE = 0.55
    CRITICAL_DISTANCE = 0.40
    BACKUP_DISTANCE = 0.30

    KP_DRIVE = 0.5
    MAX_SPEED = 0.3
    BYPASS_SPEED = 0.20
    LID_WAIT_SEC = 15.0
    ODOM_SETTLE_COUNT = 100
    KP_ROT = 0.5
    MAX_TURN = 0.3
    YAW_TOLERANCE = 0.08

    def __init__(self):
        super().__init__('robot_navigator_node')
        self.robot_x = 0.0
        self.robot_y = 0.0
        self.robot_yaw = 0.0
        self.odom_ready = False
        self.odom_count = 0
        self.targets = []
        self.home_pos = None
        self.dist_front = 10.0
        self.dist_back = 10.0
        self.dist_left = 10.0
        self.dist_right = 10.0
        self.state = self.STATE_INIT
        self.target_idx = 0
        self.wait_start = None
        self.log_tick = 0
        self.create_subscription(Odometry, '/odom', self._odom_cb, 10)
        self.create_subscription(LaserScan, '/ultrasonic/front', self._front_cb, 10)
        self.create_subscription(LaserScan, '/ultrasonic/back', self._back_cb, 10)
        # URDF left/right sensors physically swapped. Swap callbacks.
        self.create_subscription(LaserScan, '/ultrasonic/left', self._right_cb, 10)
        self.create_subscription(LaserScan, '/ultrasonic/right', self._left_cb, 10)
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.lid_client = self.create_client(SetBool, '/lid_control')
        self.enable_client = self.create_client(SetBool, '/robot_enable')
        self.create_timer(0.1, self._control_loop)
        self.get_logger().info(
            f'Navigator {self.VERSION} started - {len(self.WORLD_TARGETS)} targets + return.')

    def _calibrate(self):
        ox = self.robot_x
        oy = self.robot_y
        oyaw = self.robot_yaw
        self.get_logger().info(
            f'Settled odom after {self.odom_count} msgs: '
            f'x={ox:.3f}  y={oy:.3f}  yaw={math.degrees(oyaw):.1f} deg')
        if abs(ox - self.SPAWN_X) < 0.5 and abs(oy - self.SPAWN_Y) < 0.5:
            self.get_logger().info('Odom is in WORLD frame.')
            self.targets = list(self.WORLD_TARGETS)
            self.home_pos = (self.SPAWN_X, self.SPAWN_Y)
        else:
            self.get_logger().info('Odom is in LOCAL frame -> transforming targets.')
            dyaw = oyaw - self.SPAWN_YAW
            c, s = math.cos(dyaw), math.sin(dyaw)
            self.targets = []
            for wx, wy in self.WORLD_TARGETS:
                dwx = wx - self.SPAWN_X
                dwy = wy - self.SPAWN_Y
                self.targets.append((ox + c * dwx - s * dwy,
                                     oy + s * dwx + c * dwy))
            self.home_pos = (ox, oy)
        for i, (tx, ty) in enumerate(self.targets):
            self.get_logger().info(f'  T{i+1}: ({tx:.2f}, {ty:.2f})')
        self.get_logger().info(f'  Home: ({self.home_pos[0]:.2f}, {self.home_pos[1]:.2f})')
        self.odom_ready = True

    def _odom_cb(self, msg):
        self.robot_x = msg.pose.pose.position.x
        self.robot_y = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        siny = 2.0 * (q.w * q.z + q.x * q.y)
        cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        self.robot_yaw = math.atan2(siny, cosy)
        self.odom_count += 1

    @staticmethod
    def _min_range(msg):
        if not msg.ranges:
            return 10.0
        valid = [r for r in msg.ranges if math.isfinite(r) and r > 0.0]
        return min(valid) if valid else 10.0

    def _front_cb(self, msg): self.dist_front = self._min_range(msg)
    def _back_cb(self, msg):  self.dist_back = self._min_range(msg)
    def _left_cb(self, msg):  self.dist_left = self._min_range(msg)
    def _right_cb(self, msg): self.dist_right = self._min_range(msg)

    def _obs_scale(self, d):
        """Continuous obstacle scale: 1.0 (clear) -> 0.0 (close) -> -1.0 (backup)."""
        if d >= self.SAFE_DISTANCE:     return 1.0
        if d >= self.WARN_DISTANCE:     return (d - self.WARN_DISTANCE) / (self.SAFE_DISTANCE - self.WARN_DISTANCE)
        if d >= self.CRITICAL_DISTANCE: return 0.0
        return -1.0

    def _gate(self, vx_raw, vy_raw):
        """Apply per-axis obstacle gating. Returns (vx, vy)."""
        s_fwd = self._obs_scale(self.dist_front)
        s_bck = self._obs_scale(self.dist_back)
        s_lft = self._obs_scale(self.dist_left)
        s_rgt = self._obs_scale(self.dist_right)

        if vx_raw > 0.01:
            if s_fwd < 0:
                vx = -0.15 if self.dist_back > self.BACKUP_DISTANCE else 0.0
            else:
                vx = max(0.0, s_fwd) * vx_raw
        elif vx_raw < -0.01:
            if s_bck < 0:
                vx = 0.15 if self.dist_front > self.BACKUP_DISTANCE else 0.0
            else:
                vx = max(0.0, s_bck) * vx_raw
        else:
            vx = 0.0

        if vy_raw > 0.01:
            if s_lft < 0:
                vy = -0.15 if self.dist_right > self.BACKUP_DISTANCE else 0.0
            else:
                vy = max(0.0, s_lft) * vy_raw
        elif vy_raw < -0.01:
            if s_rgt < 0:
                vy = 0.15 if self.dist_left > self.BACKUP_DISTANCE else 0.0
            else:
                vy = max(0.0, s_rgt) * vy_raw
        else:
            vy = 0.0

        return vx, vy

    def _control_loop(self):
        if self.state == self.STATE_IDLE:
            return
        if self.state == self.STATE_INIT:
            self._do_init()
            return
        self.log_tick += 1
        if self.state == self.STATE_LID_OPENING:
            self._do_lid_open()
        elif self.state == self.STATE_WAITING:
            self._do_wait()
        elif self.state == self.STATE_LID_CLOSING:
            self._do_lid_close()
        elif self.state == self.STATE_ALIGNING:
            self._do_align()
        else:
            self._do_navigate()

    def _do_init(self):
        if self.odom_count < self.ODOM_SETTLE_COUNT:
            if self.odom_count % 10 == 1:
                self.get_logger().info(
                    f'Waiting for odom to settle '
                    f'({self.odom_count}/{self.ODOM_SETTLE_COUNT})...',
                    throttle_duration_sec=1.0)
            return
        if self.enable_client.service_is_ready():
            req = SetBool.Request()
            req.data = True
            self.enable_client.call_async(req)
            self.get_logger().info('Enabled /robot_enable.')
        else:
            self.get_logger().info('Waiting for /robot_enable...',
                                   throttle_duration_sec=2.0)
            return
        self._calibrate()
        self.state = self.STATE_NAVIGATING
        tx, ty = self.targets[0]
        self.get_logger().info(f'-> Navigating to T1 ({tx:.2f}, {ty:.2f})')

    def _do_lid_open(self):
        self._stop()
        if self._call_lid(True):
            self.wait_start = self.get_clock().now()
            self.state = self.STATE_WAITING
            self.get_logger().info(
                f'T{self.target_idx+1} reached at '
                f'({self.robot_x:.2f}, {self.robot_y:.2f}).  '
                f'Lid open - waiting {self.LID_WAIT_SEC:.0f}s.')

    def _do_wait(self):
        self._stop()
        elapsed = (self.get_clock().now() - self.wait_start).nanoseconds / 1e9
        if elapsed >= self.LID_WAIT_SEC:
            self.state = self.STATE_LID_CLOSING

    def _do_lid_close(self):
        self._stop()
        if self._call_lid(False):
            self.get_logger().info('Lid closed.')
            self.target_idx += 1
            if self.target_idx >= len(self.targets):
                self.state = self.STATE_RETURNING
                self.get_logger().info('All targets done -> returning home.')
            else:
                self.state = self.STATE_NAVIGATING
                tx, ty = self.targets[self.target_idx]
                self.get_logger().info(
                    f'-> Navigating to T{self.target_idx+1} ({tx:.2f}, {ty:.2f})')

    def _do_navigate(self):
        if self.state == self.STATE_RETURNING:
            tx, ty = self.home_pos
        else:
            tx, ty = self.targets[self.target_idx]

        dx = tx - self.robot_x
        dy = ty - self.robot_y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < self.GOAL_TOLERANCE:
            self._stop()
            if self.state == self.STATE_RETURNING:
                self.state = self.STATE_ALIGNING
                self.get_logger().info(
                    'Home reached. Aligning to initial orientation...')
            else:
                self.state = self.STATE_LID_OPENING
            return

        cy = math.cos(self.robot_yaw)
        sy = math.sin(self.robot_yaw)
        body_x =  dx * cy + dy * sy
        body_y = -dx * sy + dy * cy

        vx_raw = self._clamp(self.KP_DRIVE * body_x,
                             -self.MAX_SPEED, self.MAX_SPEED)
        vy_raw = self._clamp(self.KP_DRIVE * body_y,
                             -self.MAX_SPEED, self.MAX_SPEED)

        # Slow down near goal
        if dist < self.GOAL_TOLERANCE * 3:
            vx_raw *= 0.5
            vy_raw *= 0.5

        # Per-axis obstacle gating
        vx, vy = self._gate(vx_raw, vy_raw)

        # If fully stopped by gating, escape to direction with most room
        desired = math.sqrt(vx_raw ** 2 + vy_raw ** 2)
        actual  = math.sqrt(vx ** 2 + vy ** 2)
        if desired > 0.05 and actual < 0.03:
            options = [
                ( self.BYPASS_SPEED,  0.0,  self.dist_front),
                (-self.BYPASS_SPEED,  0.0,  self.dist_back),
                ( 0.0,  self.BYPASS_SPEED,  self.dist_left),
                ( 0.0, -self.BYPASS_SPEED,  self.dist_right),
            ]
            best = max(options, key=lambda o: o[2])
            vx, vy = best[0], best[1]
            phase = 'ESCAPE'
        else:
            bx_abs = abs(body_x)
            by_abs = abs(body_y)
            if bx_abs < 0.20 and by_abs < 0.20:
                phase = 'FINE'
            elif abs(vx) < 0.01 and abs(vy) > 0.01:
                phase = 'LAT'
            elif abs(vx) > 0.01 and abs(vy) < 0.01:
                phase = 'FWD'
            else:
                phase = 'DIAG'

        cmd = Twist()
        cmd.linear.x = self._clamp(vx, -self.MAX_SPEED, self.MAX_SPEED)
        cmd.linear.y = self._clamp(vy, -self.MAX_SPEED, self.MAX_SPEED)

        if self.log_tick % 20 == 0:
            label = 'HOME' if self.state == self.STATE_RETURNING else f'T{self.target_idx+1}'
            self.get_logger().info(
                f'[{self.state}] -> {label}  dist={dist:.2f}  '
                f'F={self.dist_front:.2f} B={self.dist_back:.2f} '
                f'L={self.dist_left:.2f} R={self.dist_right:.2f}  '
                f'body=({body_x:.2f},{body_y:.2f})  '
                f'{phase} cmd=({cmd.linear.x:.2f},{cmd.linear.y:.2f})  '
                f'pos=({self.robot_x:.2f},{self.robot_y:.2f})')

        self.cmd_pub.publish(cmd)

    def _do_align(self):
        yaw_error = self._normalize(self.SPAWN_YAW - self.robot_yaw)
        if abs(yaw_error) < self.YAW_TOLERANCE:
            self._stop()
            self.state = self.STATE_IDLE
            self.get_logger().info(
                f'Orientation aligned (yaw={math.degrees(self.robot_yaw):.1f} deg). IDLE.')
            return
        cmd = Twist()
        cmd.angular.z = -self._clamp(self.KP_ROT * yaw_error,
                                     -self.MAX_TURN, self.MAX_TURN)
        if self.log_tick % 20 == 0:
            self.get_logger().info(
                f'[ALIGNING] yaw={math.degrees(self.robot_yaw):.1f}  '
                f'target={math.degrees(self.SPAWN_YAW):.1f}  '
                f'err={math.degrees(yaw_error):.1f}  '
                f'w={cmd.angular.z:.2f}')
        self.cmd_pub.publish(cmd)

    def _stop(self):
        self.cmd_pub.publish(Twist())

    def _call_lid(self, open_lid):
        if not self.lid_client.service_is_ready():
            self.get_logger().warn('/lid_control not ready...')
            return False
        req = SetBool.Request()
        req.data = open_lid
        self.lid_client.call_async(req)
        return True

    @staticmethod
    def _normalize(a):
        while a > math.pi:  a -= 2 * math.pi
        while a < -math.pi: a += 2 * math.pi
        return a

    @staticmethod
    def _clamp(v, lo, hi):
        return max(lo, min(v, hi))


def main(args=None):
    rclpy.init(args=args)
    node = RobotNavigatorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
'''

with open(TARGET, 'w', newline='\n') as f:
    f.write(CONTENT)

st = os.stat(TARGET)
os.chmod(TARGET, st.st_mode | stat.S_IEXEC)
print(f'Written {len(CONTENT)} bytes to {TARGET}')
