#!/usr/bin/env python3
"""
arena_navigator_node.py

Sequential delivery navigation for the 4.5x4.5m arena.

Route:
  Spawn (1.30, -1.50) facing North
    → WP1 (0.99, -0.94)  lid open 5 s → close → rotate West  (world yaw = 180°)
    → WP2 (-1.02, -0.01) lid open 5 s → close → rotate North (world yaw = 90°)
    → WP3 (-0.19, 1.64)  lid open 5 s → close → return home
    → HOME (1.30, -1.50) → IDLE

Enable navigation:
  ros2 service call /robot_enable std_srvs/srv/SetBool "{data: true}"
"""

import math

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool
from std_srvs.srv import SetBool


class ArenNavigatorNode(Node):

    # ── States ─────────────────────────────────────────────
    STATE_INIT        = 'INIT'
    STATE_NAVIGATING  = 'NAVIGATING'
    STATE_LID_OPENING = 'LID_OPENING'
    STATE_WAITING     = 'WAITING'
    STATE_LID_CLOSING = 'LID_CLOSING'
    STATE_ROTATING    = 'ROTATING'
    STATE_RETURNING   = 'RETURNING'
    STATE_IDLE        = 'IDLE'

    # ── Spawn pose (world frame) ───────────────────────────
    SPAWN_X   = 1.30
    SPAWN_Y   = -1.50
    SPAWN_YAW = math.pi / 2.0   # robot spawns facing North (+Y)

    # ── Delivery targets (world frame) ─────────────────────
    WORLD_TARGETS = [
        ( 1.30, -0.40),   # 0  WP1   (delivery)
        (-0.07, -0.38),   # 1  WP1b  (waypoint only)
        (-1.48,  0.45),   # 2  WP2   (delivery)
        (-0.07,  1.74),   # 3  WP3   (delivery)
        (-0.07, -0.38),   # 4  WP3b  (waypoint only)
    ]
    TARGET_NAMES  = ['WP1', 'WP1b', 'WP2', 'WP3', 'WP3b']
    WORLD_HOME    = (1.30, -1.50)

    # Indices that are delivery stops (lid opens)
    LID_INDICES = frozenset({0, 2, 3})

    # World-frame yaw to rotate to after lid cycle
    WORLD_FACING = {
        0: math.pi,         # WP1  → face West  (180°)
        2: math.pi / 2.0,   # WP2  → face North  (90°)
        3: -math.pi / 2.0,  # WP3  → face South  (-90° / 270°)
    }
    FACING_NAMES = {0: 'West', 2: 'North', 3: 'South'}

    # ── Tuning ─────────────────────────────────────────────
    LID_WAIT_SEC      = 5.0
    GOAL_TOLERANCE    = 0.15
    ESCAPE_SUPPRESS   = 0.50   # suppress escape when this close to target
    ODOM_SETTLE_COUNT = 100

    SAFE_DISTANCE     = 0.80
    WARN_DISTANCE     = 0.55
    CRITICAL_DISTANCE = 0.40
    BACKUP_DISTANCE   = 0.30

    KP_DRIVE     = 0.5
    MAX_SPEED    = 0.3
    FORCED_SPEED = 0.25
    BYPASS_SPEED = 0.20

    KP_ROT        = 0.5
    MAX_TURN      = 0.3
    YAW_TOLERANCE = 0.03

    # ───────────────────────────────────────────────────────

    def __init__(self):
        super().__init__('arena_navigator_node')

        # Robot pose (from odom)
        self.robot_x   = 0.0
        self.robot_y   = 0.0
        self.robot_yaw = 0.0
        self.odom_count = 0
        self.odom_ready = False

        # Sensor distances
        self.dist_front = 10.0
        self.dist_back  = 10.0
        self.dist_left  = 10.0
        self.dist_right = 10.0

        # State machine
        self.state      = self.STATE_INIT
        self.target_idx = 0
        self.wait_start = None
        self.log_tick   = 0

        # Calibrated targets in odom frame
        self.targets     = []
        self.home_pos    = None
        self.facing_yaws = {}   # target index → local-frame yaw to face

        # Active rotation goal
        self.rotate_target_yaw = 0.0

        # Control flags
        self.robot_enabled   = False
        self.obstacle_active = False

        # Escape hold: commit to one escape direction for N ticks
        self._escape_ticks_remaining = 0
        self._escape_vx = 0.0
        self._escape_vy = 0.0

        # Subscribers
        self.create_subscription(Odometry,  '/odom',              self._odom_cb,  10)
        self.create_subscription(LaserScan, '/ultrasonic/front',  self._front_cb, 10)
        self.create_subscription(LaserScan, '/ultrasonic/back',   self._back_cb,  10)
        # URDF left/right sensors are physically swapped – swap callbacks:
        self.create_subscription(LaserScan, '/ultrasonic/left',   self._right_cb, 10)
        self.create_subscription(LaserScan, '/ultrasonic/right',  self._left_cb,  10)
        self.create_subscription(Bool, '/robot_enabled_state', self._enabled_cb,  1)
        self.create_subscription(Bool, '/dynamic_obstacle',    self._obstacle_cb, 10)

        # Publisher → start_stop gate → /cmd_vel
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel_input', 10)

        # Lid service
        self.lid_client = self.create_client(SetBool, '/lid_control')

        # 10 Hz control loop
        self.create_timer(0.1, self._control_loop)

        self.get_logger().info(
            'Arena Navigator started.\n'
            '  Route: WP1(0.99,-0.94) → WP2(-1.02,-0.01) → WP3(-0.19,1.64) → HOME(1.30,-1.50)\n'
            '  Enable: ros2 service call /robot_enable std_srvs/srv/SetBool "{data: true}"')

    # ═══════════════════════════════════════════════════
    #  Callbacks
    # ═══════════════════════════════════════════════════

    def _odom_cb(self, msg: Odometry):
        self.robot_x = msg.pose.pose.position.x
        self.robot_y = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        siny = 2.0 * (q.w * q.z + q.x * q.y)
        cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        self.robot_yaw = math.atan2(siny, cosy)
        self.odom_count += 1

    def _enabled_cb(self, msg: Bool):
        self.robot_enabled = msg.data

    def _obstacle_cb(self, msg: Bool):
        self.obstacle_active = msg.data

    @staticmethod
    def _min_range(msg: LaserScan) -> float:
        valid = [r for r in msg.ranges if math.isfinite(r) and r > 0.0]
        return min(valid) if valid else 10.0

    def _front_cb(self, msg): self.dist_front = self._min_range(msg)
    def _back_cb(self,  msg): self.dist_back  = self._min_range(msg)
    def _left_cb(self,  msg): self.dist_left  = self._min_range(msg)
    def _right_cb(self, msg): self.dist_right = self._min_range(msg)

    # ═══════════════════════════════════════════════════
    #  Calibration – convert world targets to odom frame
    # ═══════════════════════════════════════════════════

    def _calibrate(self):
        ox   = self.robot_x
        oy   = self.robot_y
        oyaw = self.robot_yaw

        if abs(ox - self.SPAWN_X) < 0.5 and abs(oy - self.SPAWN_Y) < 0.5:
            # Odometry is already in world frame
            self.get_logger().info('Odom is in WORLD frame.')
            self.targets  = list(self.WORLD_TARGETS)
            self.home_pos = self.WORLD_HOME
            for i, wyaw in self.WORLD_FACING.items():
                self.facing_yaws[i] = wyaw
        else:
            # Odometry is in local frame → transform
            self.get_logger().info(
                f'Odom in LOCAL frame (ox={ox:.2f}, oy={oy:.2f}) → transforming targets.')
            dyaw = oyaw - self.SPAWN_YAW
            c, s = math.cos(dyaw), math.sin(dyaw)

            self.targets = []
            for wx, wy in self.WORLD_TARGETS:
                dwx = wx - self.SPAWN_X
                dwy = wy - self.SPAWN_Y
                self.targets.append((ox + c * dwx - s * dwy,
                                     oy + s * dwx + c * dwy))

            hwx = self.WORLD_HOME[0] - self.SPAWN_X
            hwy = self.WORLD_HOME[1] - self.SPAWN_Y
            self.home_pos = (ox + c * hwx - s * hwy,
                             oy + s * hwx + c * hwy)

            for i, wyaw in self.WORLD_FACING.items():
                self.facing_yaws[i] = self._normalize(wyaw - self.SPAWN_YAW + oyaw)

        for i, (tx, ty) in enumerate(self.targets):
            self.get_logger().info(f'  {self.TARGET_NAMES[i]}: ({tx:.2f}, {ty:.2f})')
        self.get_logger().info(
            f'  Home: ({self.home_pos[0]:.2f}, {self.home_pos[1]:.2f})')
        self.odom_ready = True

    # ═══════════════════════════════════════════════════
    #  Obstacle / sensor gate
    # ═══════════════════════════════════════════════════

    def _obs_scale(self, d):
        if d >= self.SAFE_DISTANCE:     return 1.0
        if d >= self.WARN_DISTANCE:
            return (d - self.WARN_DISTANCE) / (self.SAFE_DISTANCE - self.WARN_DISTANCE)
        if d >= self.CRITICAL_DISTANCE: return 0.0
        return -1.0

    def _gate(self, vx_raw, vy_raw):
        sf = self._obs_scale(self.dist_front)
        sb = self._obs_scale(self.dist_back)
        sl = self._obs_scale(self.dist_left)
        sr = self._obs_scale(self.dist_right)

        if vx_raw > 0.01:
            vx = (-0.15 if self.dist_back > self.BACKUP_DISTANCE else 0.0) if sf < 0 else max(0.0, sf) * vx_raw
        elif vx_raw < -0.01:
            vx = ( 0.15 if self.dist_front > self.BACKUP_DISTANCE else 0.0) if sb < 0 else max(0.0, sb) * vx_raw
        else:
            vx = 0.0

        if vy_raw > 0.01:
            vy = (-0.15 if self.dist_right > self.BACKUP_DISTANCE else 0.0) if sl < 0 else max(0.0, sl) * vy_raw
        elif vy_raw < -0.01:
            vy = ( 0.15 if self.dist_left > self.BACKUP_DISTANCE else 0.0)  if sr < 0 else max(0.0, sr) * vy_raw
        else:
            vy = 0.0

        return vx, vy

    # ═══════════════════════════════════════════════════
    #  Control loop
    # ═══════════════════════════════════════════════════

    def _control_loop(self):
        if self.state == self.STATE_IDLE:
            return
        if self.state == self.STATE_INIT:
            self._do_init()
            return
        self.log_tick += 1
        if   self.state == self.STATE_LID_OPENING: self._do_lid_open()
        elif self.state == self.STATE_WAITING:      self._do_wait()
        elif self.state == self.STATE_LID_CLOSING:  self._do_lid_close()
        elif self.state == self.STATE_ROTATING:     self._do_rotate()
        else:                                        self._do_navigate()

    # ── INIT ────────────────────────────────────────────

    def _do_init(self):
        if self.odom_count < self.ODOM_SETTLE_COUNT:
            if self.odom_count % 20 == 1:
                self.get_logger().info(
                    f'Waiting for odom to settle '
                    f'({self.odom_count}/{self.ODOM_SETTLE_COUNT})...',
                    throttle_duration_sec=2.0)
            return
        if not self.robot_enabled:
            if self.odom_count % 50 == 0:
                self.get_logger().info(
                    'Odom ready. Waiting for /robot_enabled_state=True...',
                    throttle_duration_sec=2.0)
            return
        self._calibrate()
        self.state = self.STATE_NAVIGATING
        tx, ty = self.targets[0]
        self.get_logger().info(
            f'Robot enabled. Navigating → {self.TARGET_NAMES[0]} ({tx:.2f}, {ty:.2f})')

    # ── LID CYCLE ───────────────────────────────────────

    def _do_lid_open(self):
        self._stop()
        if self._call_lid(True):
            self.wait_start = self.get_clock().now()
            self.state = self.STATE_WAITING
            self.get_logger().info(
                f'{self.TARGET_NAMES[self.target_idx]} reached '
                f'({self.robot_x:.2f}, {self.robot_y:.2f}). '
                f'Lid open – waiting {self.LID_WAIT_SEC:.0f}s.')

    def _do_wait(self):
        self._stop()
        elapsed = (self.get_clock().now() - self.wait_start).nanoseconds / 1e9
        if elapsed >= self.LID_WAIT_SEC:
            self.state = self.STATE_LID_CLOSING

    def _do_lid_close(self):
        self._stop()
        if self._call_lid(False):
            self.get_logger().info('Lid closed.')
            if self.target_idx in self.facing_yaws:
                self.rotate_target_yaw = self.facing_yaws[self.target_idx]
                facing = self.FACING_NAMES.get(self.target_idx, '?')
                self.state = self.STATE_ROTATING
                self.get_logger().info(
                    f'Rotating to face {facing} '
                    f'(target yaw={math.degrees(self.rotate_target_yaw):.0f}°)')
            else:
                self._advance_target()

    # ── ROTATION ────────────────────────────────────────

    def _do_rotate(self):
        yaw_err = self._normalize(self.rotate_target_yaw - self.robot_yaw)
        if abs(yaw_err) < self.YAW_TOLERANCE:
            self._stop()
            self.get_logger().info(
                f'Rotation done (yaw={math.degrees(self.robot_yaw):.1f}°). Continuing.')
            self._advance_target()
            return
        cmd = Twist()
        cmd.angular.z = -self._clamp(self.KP_ROT * yaw_err, -self.MAX_TURN, self.MAX_TURN)
        if self.log_tick % 20 == 0:
            self.get_logger().info(
                f'[ROTATING] yaw={math.degrees(self.robot_yaw):.1f}°  '
                f'target={math.degrees(self.rotate_target_yaw):.1f}°  '
                f'err={math.degrees(yaw_err):.1f}°  w={cmd.angular.z:.2f}')
        self.cmd_pub.publish(cmd)

    # ── ADVANCE TARGET ──────────────────────────────────

    def _advance_target(self):
        self.target_idx += 1
        if self.target_idx >= len(self.targets):
            self.state = self.STATE_RETURNING
            self.get_logger().info(
                f'All targets done → returning home '
                f'({self.home_pos[0]:.2f}, {self.home_pos[1]:.2f})')
        else:
            self.state = self.STATE_NAVIGATING
            tx, ty = self.targets[self.target_idx]
            self.get_logger().info(
                f'→ Navigating to {self.TARGET_NAMES[self.target_idx]} ({tx:.2f}, {ty:.2f})')

    # ── NAVIGATE / RETURN ───────────────────────────────

    def _do_navigate(self):
        if self.state == self.STATE_RETURNING:
            tx, ty = self.home_pos
        else:
            tx, ty = self.targets[self.target_idx]

        dx   = tx - self.robot_x
        dy   = ty - self.robot_y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < self.GOAL_TOLERANCE:
            self._stop()
            if self.state == self.STATE_RETURNING:
                self.state = self.STATE_IDLE
                self.get_logger().info(
                    f'Home reached ({self.robot_x:.2f}, {self.robot_y:.2f}). IDLE.')
            elif self.target_idx in self.LID_INDICES:
                self.state = self.STATE_LID_OPENING
            else:
                # Waypoint: pass through without opening lid
                self.get_logger().info(
                    f'{self.TARGET_NAMES[self.target_idx]} waypoint reached '
                    f'({self.robot_x:.2f}, {self.robot_y:.2f}). Continuing.')
                self._advance_target()
            return

        # Transform error to robot body frame
        cy = math.cos(self.robot_yaw)
        sy = math.sin(self.robot_yaw)
        body_x =  dx * cy + dy * sy
        body_y = -dx * sy + dy * cy

        vx_raw = self._clamp(self.KP_DRIVE * body_x, -self.MAX_SPEED, self.MAX_SPEED)
        vy_raw = self._clamp(self.KP_DRIVE * body_y, -self.MAX_SPEED, self.MAX_SPEED)

        # Slow down near goal
        if dist < self.GOAL_TOLERANCE * 3:
            vx_raw *= 0.5
            vy_raw *= 0.5

        if self.obstacle_active:
            vx, vy, phase = 0.0, 0.0, 'OBS'
        elif self.state == self.STATE_RETURNING:
            # Forced speed for homing (no sensor gate)
            mag = math.sqrt(body_x ** 2 + body_y ** 2)
            if mag > 0.01:
                vx = self.FORCED_SPEED * body_x / mag
                vy = self.FORCED_SPEED * body_y / mag
            else:
                vx, vy = 0.0, 0.0
            phase = 'HOME'
        else:
            vx, vy = self._gate(vx_raw, vy_raw)
            desired = math.sqrt(vx_raw ** 2 + vy_raw ** 2)
            actual  = math.sqrt(vx ** 2 + vy ** 2)
            near_goal = dist < self.ESCAPE_SUPPRESS
            if near_goal:
                # Close to target – bypass sensor gate, trust navigation
                vx, vy = vx_raw, vy_raw
                self._escape_ticks_remaining = 0
                phase = 'NAV'
            elif self._escape_ticks_remaining > 0:
                vx = self._escape_vx
                vy = self._escape_vy
                self._escape_ticks_remaining -= 1
                phase = 'ESCAPE'
            elif desired > 0.05 and actual < 0.03:
                # Target-guided escape: prefer direction toward target;
                # only fall back to most-open if target direction is blocked.
                if body_y > 0 and self.dist_left > self.CRITICAL_DISTANCE:
                    esc_vx, esc_vy = 0.0,  self.BYPASS_SPEED
                elif body_y <= 0 and self.dist_right > self.CRITICAL_DISTANCE:
                    esc_vx, esc_vy = 0.0, -self.BYPASS_SPEED
                elif body_x > 0 and self.dist_front > self.CRITICAL_DISTANCE:
                    esc_vx, esc_vy = self.BYPASS_SPEED, 0.0
                elif self.dist_back > self.CRITICAL_DISTANCE:
                    esc_vx, esc_vy = -self.BYPASS_SPEED, 0.0
                else:
                    opts = [
                        ( self.BYPASS_SPEED, 0.0, self.dist_front),
                        (-self.BYPASS_SPEED, 0.0, self.dist_back),
                        (0.0,  self.BYPASS_SPEED, self.dist_left),
                        (0.0, -self.BYPASS_SPEED, self.dist_right),
                    ]
                    esc_vx, esc_vy, _ = max(opts, key=lambda o: o[2])
                vx, vy = esc_vx, esc_vy
                self._escape_vx = vx
                self._escape_vy = vy
                self._escape_ticks_remaining = 60   # hold for 6 s at 10 Hz
                phase = 'ESCAPE'
            else:
                phase = 'NAV'

        cmd = Twist()
        cmd.linear.x = self._clamp(vx, -self.MAX_SPEED, self.MAX_SPEED)
        cmd.linear.y = self._clamp(vy, -self.MAX_SPEED, self.MAX_SPEED)

        if self.log_tick % 20 == 0:
            label = ('HOME' if self.state == self.STATE_RETURNING
                     else self.TARGET_NAMES[self.target_idx])
            self.get_logger().info(
                f'[{self.state}] → {label}  dist={dist:.2f}  '
                f'F={self.dist_front:.2f} B={self.dist_back:.2f} '
                f'L={self.dist_left:.2f} R={self.dist_right:.2f}  '
                f'{phase} cmd=({cmd.linear.x:.2f},{cmd.linear.y:.2f})  '
                f'pos=({self.robot_x:.2f},{self.robot_y:.2f})')

        self.cmd_pub.publish(cmd)

    # ═══════════════════════════════════════════════════
    #  Helpers
    # ═══════════════════════════════════════════════════

    def _stop(self):
        self.cmd_pub.publish(Twist())

    def _call_lid(self, open_lid: bool) -> bool:
        if not self.lid_client.service_is_ready():
            self.get_logger().warn('/lid_control not ready – retrying next tick...')
            return False
        req = SetBool.Request()
        req.data = open_lid
        self.lid_client.call_async(req)
        return True

    @staticmethod
    def _normalize(a: float) -> float:
        while a >  math.pi: a -= 2.0 * math.pi
        while a < -math.pi: a += 2.0 * math.pi
        return a

    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))


def main(args=None):
    rclpy.init(args=args)
    node = ArenNavigatorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
