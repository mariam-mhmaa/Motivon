#!/usr/bin/env python3
"""Shared navigation test runner with segment coverage and obstacle states."""

from __future__ import annotations

import json
import math
from typing import List, Optional, Tuple

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, String

from navigation_routes import SPAWN_X, SPAWN_Y, SPAWN_YAW, RouteDefinition, RouteStep, get_route


class NavigationRouteRunner(Node):
    NAV_IDLE = "NAV_IDLE"
    NAV_READY = "NAV_READY"
    NAV_TO_CHECKPOINT = "NAV_TO_CHECKPOINT"
    NAV_TO_STATION = "NAV_TO_STATION"
    NAV_RETURNING_HOME = "NAV_RETURNING_HOME"
    NAV_WAITING_DYNAMIC_CLEAR = "NAV_WAITING_DYNAMIC_CLEAR"
    NAV_DYNAMIC_CLEAR_BUFFER = "NAV_DYNAMIC_CLEAR_BUFFER"
    NAV_STATIC_AVOID_RIGHT = "NAV_STATIC_AVOID_RIGHT"
    NAV_STATIC_AVOID_LEFT = "NAV_STATIC_AVOID_LEFT"
    NAV_COURSE_CORRECTING = "NAV_COURSE_CORRECTING"
    NAV_ALIGNING_YAW = "NAV_ALIGNING_YAW"
    NAV_COMPLETE = "NAV_COMPLETE"
    NAV_FAULT = "NAV_FAULT"
    NAV_ESTOP_PAUSED = "NAV_ESTOP_PAUSED"

    def __init__(self, node_name: str, route_id: str):
        super().__init__(node_name)
        self.route_def: RouteDefinition = get_route(route_id)

        self.declare_parameter("goal_tolerance", 0.08)
        self.declare_parameter("waypoint_tolerance", 0.20)
        self.declare_parameter("safe_distance", 0.80)
        self.declare_parameter("warn_distance", 0.55)
        self.declare_parameter("critical_distance", 0.40)
        self.declare_parameter("front_blocked_distance", 0.40)
        self.declare_parameter("front_clear_distance", 0.80)
        self.declare_parameter("side_too_close_distance", 0.28)
        self.declare_parameter("backup_distance", 0.30)
        self.declare_parameter("obstacle_suppress_distance", 0.50)
        self.declare_parameter("kp_drive", 0.5)
        self.declare_parameter("max_speed", 0.30)
        self.declare_parameter("static_strafe_speed", 0.18)
        self.declare_parameter("course_correct_seconds", 1.5)
        self.declare_parameter("dynamic_wait_timeout_sec", 30.0)
        self.declare_parameter("dynamic_clear_buffer_sec", 30.0)
        self.declare_parameter("static_avoid_fault_sec", 45.0)
        self.declare_parameter("odom_settle_count", 100)
        self.declare_parameter("kp_rotate", 3.0)
        self.declare_parameter("max_turn", 0.50)
        self.declare_parameter("yaw_tolerance", 0.08)
        self.declare_parameter("yaw_settle_ticks", 5)

        self.goal_tol = float(self.get_parameter("goal_tolerance").value)
        self.waypoint_tol = float(self.get_parameter("waypoint_tolerance").value)
        self.safe_dist = float(self.get_parameter("safe_distance").value)
        self.warn_dist = float(self.get_parameter("warn_distance").value)
        self.critical_dist = float(self.get_parameter("critical_distance").value)
        self.front_blocked_dist = float(self.get_parameter("front_blocked_distance").value)
        self.front_clear_dist = float(self.get_parameter("front_clear_distance").value)
        self.side_too_close = float(self.get_parameter("side_too_close_distance").value)
        self.backup_dist = float(self.get_parameter("backup_distance").value)
        self.obstacle_suppress = float(self.get_parameter("obstacle_suppress_distance").value)
        self.kp_drive = float(self.get_parameter("kp_drive").value)
        self.max_speed = float(self.get_parameter("max_speed").value)
        self.static_strafe_speed = float(self.get_parameter("static_strafe_speed").value)
        self.course_correct_seconds = float(self.get_parameter("course_correct_seconds").value)
        self.dynamic_wait_timeout_sec = float(self.get_parameter("dynamic_wait_timeout_sec").value)
        self.dynamic_clear_buffer_sec = float(self.get_parameter("dynamic_clear_buffer_sec").value)
        self.static_avoid_fault_sec = float(self.get_parameter("static_avoid_fault_sec").value)
        self.odom_settle_count = int(self.get_parameter("odom_settle_count").value)
        self.kp_rotate = float(self.get_parameter("kp_rotate").value)
        self.max_turn = float(self.get_parameter("max_turn").value)
        self.yaw_tol = float(self.get_parameter("yaw_tolerance").value)
        self.yaw_settle_ticks = int(self.get_parameter("yaw_settle_ticks").value)

        self.robot_x = 0.0
        self.robot_y = 0.0
        self.robot_yaw = 0.0
        self.odom_count = 0

        self.dist_front = 10.0
        self.dist_back = 10.0
        self.dist_left = 10.0
        self.dist_right = 10.0
        self.dynamic_obstacle = False
        self.robot_enabled = False

        self.route_local: Optional[List[RouteStep]] = None
        self.step_index = 0
        self.completed = False
        self.completed_segments: List[Tuple[str, str]] = []
        self.state = self.NAV_IDLE
        self.resume_state: Optional[str] = None
        self.resume_after_obstacle: Optional[str] = None
        self.state_since = self.get_clock().now()
        self._tick = 0
        self._rot_settle = 0
        self._target_yaw: Optional[float] = None

        self.cmd_pub = self.create_publisher(Twist, "/cmd_vel_input", 10)
        self.nav_state_pub = self.create_publisher(String, "/nav_state", 10)
        self.nav_progress_pub = self.create_publisher(String, "/nav_progress", 10)
        self.nav_segment_pub = self.create_publisher(String, "/nav_segment_event", 10)
        self.nav_summary_pub = self.create_publisher(String, "/nav_summary", 10)
        self.state_hint_pub = self.create_publisher(String, "/robot_state_hint", 10)

        self.create_subscription(Odometry, "/odom", self._odom_cb, 10)
        self.create_subscription(LaserScan, "/ultrasonic/front", self._front_cb, 10)
        self.create_subscription(LaserScan, "/ultrasonic/back", self._back_cb, 10)
        self.create_subscription(LaserScan, "/ultrasonic/left", self._right_cb, 10)
        self.create_subscription(LaserScan, "/ultrasonic/right", self._left_cb, 10)
        self.create_subscription(Bool, "/robot_enabled_state", self._enabled_cb, 1)
        self.create_subscription(Bool, "/dynamic_obstacle", self._dynamic_cb, 10)

        self.create_timer(0.1, self._loop)
        self.get_logger().info(f"Route locked: {self.route_def.display_name}")

    def _odom_cb(self, msg: Odometry):
        self.robot_x = msg.pose.pose.position.x
        self.robot_y = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        self.robot_yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        self.odom_count += 1

    def _enabled_cb(self, msg: Bool):
        self.robot_enabled = msg.data

    def _dynamic_cb(self, msg: Bool):
        self.dynamic_obstacle = msg.data

    @staticmethod
    def _min_range(msg: LaserScan) -> float:
        valid = [r for r in msg.ranges if math.isfinite(r) and r > 0.0]
        return min(valid) if valid else 10.0

    def _front_cb(self, msg: LaserScan):
        self.dist_front = self._min_range(msg)

    def _back_cb(self, msg: LaserScan):
        self.dist_back = self._min_range(msg)

    def _left_cb(self, msg: LaserScan):
        self.dist_left = self._min_range(msg)

    def _right_cb(self, msg: LaserScan):
        self.dist_right = self._min_range(msg)

    def _loop(self):
        if self.completed:
            return

        if self.odom_count < self.odom_settle_count:
            if self.odom_count % 20 == 1:
                self.get_logger().info(f"Waiting odom ({self.odom_count}/{self.odom_settle_count})...")
            return

        if self.route_local is None:
            self._calibrate_route()
            self._set_state(self.NAV_READY, "route calibrated")
            if self.robot_enabled:
                self._enter_motion_state()
            return

        if not self.robot_enabled and self.state not in (self.NAV_READY, self.NAV_IDLE, self.NAV_COMPLETE, self.NAV_FAULT):
            if self.state != self.NAV_ESTOP_PAUSED:
                self.resume_state = self.state
                self._set_state(self.NAV_ESTOP_PAUSED, "robot disabled")
                self._stop()
            return

        if self.robot_enabled and self.state == self.NAV_READY:
            self._enter_motion_state()
            return

        if self.robot_enabled and self.state == self.NAV_ESTOP_PAUSED:
            self._set_state(self.resume_state or self._route_state_for_step(), "robot re-enabled")
            self.resume_state = None
            return

        self._tick += 1
        if self.state in (self.NAV_TO_CHECKPOINT, self.NAV_TO_STATION, self.NAV_RETURNING_HOME):
            self._run_motion_state()
        elif self.state == self.NAV_WAITING_DYNAMIC_CLEAR:
            self._run_dynamic_wait()
        elif self.state == self.NAV_DYNAMIC_CLEAR_BUFFER:
            self._run_clear_buffer()
        elif self.state == self.NAV_STATIC_AVOID_RIGHT:
            self._run_static_avoid(right_first=True)
        elif self.state == self.NAV_STATIC_AVOID_LEFT:
            self._run_static_avoid(right_first=False)
        elif self.state == self.NAV_COURSE_CORRECTING:
            self._run_course_correcting()
        elif self.state == self.NAV_ALIGNING_YAW:
            self._run_aligning_yaw()

    def _calibrate_route(self):
        ox, oy, oyaw = self.robot_x, self.robot_y, self.robot_yaw
        dyaw = oyaw - SPAWN_YAW
        c, s = math.cos(dyaw), math.sin(dyaw)
        route_local: List[RouteStep] = []
        for step in self.route_def.steps:
            wx, wy = step.pose
            dwx = wx - SPAWN_X
            dwy = wy - SPAWN_Y
            local_pose = (ox + c * dwx - s * dwy, oy + s * dwx + c * dwy)
            local_yaw = None if step.target_yaw is None else self._normalize(step.target_yaw + dyaw)
            route_local.append(RouteStep(step.name, local_pose, step.is_station, local_yaw))
        self.route_local = route_local
        self.get_logger().info("Targets transformed to odom frame.")

    def _route_state_for_step(self) -> str:
        step = self.route_local[self.step_index]
        if step.name == "HOME":
            return self.NAV_RETURNING_HOME
        if step.is_station:
            return self.NAV_TO_STATION
        return self.NAV_TO_CHECKPOINT

    def _current_step(self) -> RouteStep:
        return self.route_local[self.step_index]

    def _enter_motion_state(self):
        self._set_state(self._route_state_for_step(), f"entering step {self._current_step().name}")

    def _set_state(self, new_state: str, reason: str):
        if self.state == new_state:
            return
        self.state = new_state
        self.state_since = self.get_clock().now()
        self._publish_state(reason)
        self.get_logger().info(f"[STATE] {new_state}: {reason}")

    def _publish_state(self, reason: str):
        msg = String()
        msg.data = json.dumps(
            {
                "route_id": self.route_def.route_id,
                "state": self.state,
                "reason": reason,
                "step_index": self.step_index,
                "target": self._current_step().name if self.route_local else None,
            }
        )
        self.nav_state_pub.publish(msg)
        self.state_hint_pub.publish(msg)

    def _publish_progress(self, extra: Optional[dict] = None):
        step = self._current_step()
        payload = {
            "route_id": self.route_def.route_id,
            "state": self.state,
            "step_index": self.step_index,
            "target": step.name,
            "target_pose": [step.pose[0], step.pose[1]],
            "position": [self.robot_x, self.robot_y],
            "yaw": self.robot_yaw,
            "completed_segments": [[a, b] for a, b in self.completed_segments],
            "front": self.dist_front,
            "back": self.dist_back,
            "left": self.dist_left,
            "right": self.dist_right,
            "dynamic_obstacle": self.dynamic_obstacle,
        }
        if extra:
            payload.update(extra)
        msg = String()
        msg.data = json.dumps(payload)
        self.nav_progress_pub.publish(msg)

    def _publish_segment(self, frm: str, to: str):
        self.completed_segments.append((frm, to))
        msg = String()
        msg.data = json.dumps(
            {
                "route_id": self.route_def.route_id,
                "segment": [frm, to],
                "segment_index": len(self.completed_segments) - 1,
                "all_segments": [[a, b] for a, b in self.completed_segments],
            }
        )
        self.nav_segment_pub.publish(msg)

    def _stop(self):
        self.cmd_pub.publish(Twist())

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    @staticmethod
    def _normalize(angle: float) -> float:
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle

    def _obs_scale(self, distance: float) -> float:
        if distance >= self.safe_dist:
            return 1.0
        if distance >= self.warn_dist:
            return (distance - self.warn_dist) / (self.safe_dist - self.warn_dist)
        if distance >= self.critical_dist:
            return 0.0
        return -1.0

    def _gate(self, vx_raw: float, vy_raw: float) -> Tuple[float, float]:
        sf = self._obs_scale(self.dist_front)
        sb = self._obs_scale(self.dist_back)
        sl = self._obs_scale(self.dist_left)
        sr = self._obs_scale(self.dist_right)

        def apply_axis(value: float, positive_scale: float, negative_scale: float, positive_dist: float, negative_dist: float) -> float:
            if value > 0.01:
                return (-0.15 if negative_dist > self.backup_dist else 0.0) if positive_scale < 0.0 else max(0.0, positive_scale) * value
            if value < -0.01:
                return (0.15 if positive_dist > self.backup_dist else 0.0) if negative_scale < 0.0 else max(0.0, negative_scale) * value
            return 0.0

        return (
            apply_axis(vx_raw, sf, sb, self.dist_front, self.dist_back),
            apply_axis(vy_raw, sl, sr, self.dist_left, self.dist_right),
        )

    def _path_blocked(self) -> bool:
        return self.dynamic_obstacle or self.dist_front <= self.front_blocked_dist

    def _front_clear(self) -> bool:
        return self.dist_front >= self.front_clear_dist and not self.dynamic_obstacle

    def _state_elapsed(self) -> float:
        return (self.get_clock().now() - self.state_since).nanoseconds / 1e9

    def _compute_tracking_command(self, step: RouteStep) -> Tuple[Twist, float]:
        dx = step.pose[0] - self.robot_x
        dy = step.pose[1] - self.robot_y
        dist = math.sqrt(dx * dx + dy * dy)
        tol = self.goal_tol if (step.is_station or step.name == "HOME") else self.waypoint_tol

        cmd = Twist()
        if dist < tol:
            return cmd, dist

        cy = math.cos(self.robot_yaw)
        sy = math.sin(self.robot_yaw)
        body_x = dx * cy + dy * sy
        body_y = -dx * sy + dy * cy

        vx_raw = self._clamp(self.kp_drive * body_x, -self.max_speed, self.max_speed)
        vy_raw = self._clamp(self.kp_drive * body_y, -self.max_speed, self.max_speed)
        if dist < tol * 3.0:
            vx_raw *= 0.5
            vy_raw *= 0.5
        if dist < self.obstacle_suppress:
            cmd.linear.x = vx_raw
            cmd.linear.y = vy_raw
        else:
            gated_x, gated_y = self._gate(vx_raw, vy_raw)
            cmd.linear.x = self._clamp(gated_x, -self.max_speed, self.max_speed)
            cmd.linear.y = self._clamp(gated_y, -self.max_speed, self.max_speed)
        return cmd, dist

    def _run_motion_state(self):
        step = self._current_step()
        cmd, dist = self._compute_tracking_command(step)
        tol = self.goal_tol if (step.is_station or step.name == "HOME") else self.waypoint_tol

        if dist < tol:
            self._stop()
            if step.target_yaw is not None:
                self._target_yaw = step.target_yaw
                self._rot_settle = 0
                self._set_state(self.NAV_ALIGNING_YAW, f"aligning at {step.name}")
                return
            self._finish_current_step()
            return

        if self._path_blocked() and dist > self.obstacle_suppress:
            self.resume_after_obstacle = self.state
            self._set_state(self.NAV_WAITING_DYNAMIC_CLEAR, f"path blocked before {step.name}")
            self._stop()
            return

        if self._tick % 20 == 0:
            self.get_logger().info(
                f"[{self.state}] -> {step.name} dist={dist:.2f} "
                f"F={self.dist_front:.2f} B={self.dist_back:.2f} "
                f"L={self.dist_left:.2f} R={self.dist_right:.2f} "
                f"cmd=({cmd.linear.x:.2f},{cmd.linear.y:.2f})"
            )
        self._publish_progress({"distance_to_target": dist})
        self.cmd_pub.publish(cmd)

    def _run_dynamic_wait(self):
        self._stop()
        elapsed = self._state_elapsed()
        if not self._path_blocked():
            self._set_state(self.NAV_DYNAMIC_CLEAR_BUFFER, "path clear, buffering before resume")
            return
        if elapsed >= self.dynamic_wait_timeout_sec:
            self._set_state(self.NAV_STATIC_AVOID_RIGHT, "blockage persisted, classify static")
            return
        self._publish_progress({"wait_elapsed_sec": elapsed})

    def _run_clear_buffer(self):
        self._stop()
        elapsed = self._state_elapsed()
        if self._path_blocked():
            self._set_state(self.NAV_WAITING_DYNAMIC_CLEAR, "obstacle returned during clear buffer")
            return
        if elapsed >= self.dynamic_clear_buffer_sec:
            self._set_state(self.resume_after_obstacle or self._route_state_for_step(), "clear buffer elapsed, resume navigation")
            self.resume_after_obstacle = None
            return
        self._publish_progress({"clear_buffer_elapsed_sec": elapsed})

    def _run_static_avoid(self, right_first: bool):
        elapsed = self._state_elapsed()
        if elapsed >= self.static_avoid_fault_sec and self.dist_left <= self.side_too_close and self.dist_right <= self.side_too_close:
            self._set_state(self.NAV_FAULT, "both lateral escape directions blocked")
            self._stop()
            return
        if self._front_clear():
            self._set_state(self.NAV_COURSE_CORRECTING, "front path clear, reacquiring route")
            return

        cmd = Twist()
        if right_first:
            if self.dist_right <= self.side_too_close:
                self._set_state(self.NAV_STATIC_AVOID_LEFT, "right side too close, switching left")
                return
            cmd.linear.y = -self.static_strafe_speed
        else:
            if self.dist_left <= self.side_too_close and self.dist_right <= self.side_too_close:
                self._set_state(self.NAV_FAULT, "left recovery blocked and right still unsafe")
                self._stop()
                return
            if self.dist_left <= self.side_too_close and self.dist_right > self.side_too_close:
                self._set_state(self.NAV_STATIC_AVOID_RIGHT, "left side too close, switching right")
                return
            cmd.linear.y = self.static_strafe_speed

        if self._tick % 10 == 0:
            self.get_logger().info(
                f"[{self.state}] strafing {'right' if right_first else 'left'} "
                f"F={self.dist_front:.2f} L={self.dist_left:.2f} R={self.dist_right:.2f}"
            )
        self._publish_progress({"avoid_elapsed_sec": elapsed})
        self.cmd_pub.publish(cmd)

    def _run_course_correcting(self):
        step = self._current_step()
        if self._path_blocked():
            self._set_state(self.NAV_WAITING_DYNAMIC_CLEAR, "obstacle returned during course correction")
            return

        cmd, dist = self._compute_tracking_command(step)
        self.cmd_pub.publish(cmd)
        self._publish_progress({"distance_to_target": dist, "course_correct_elapsed_sec": self._state_elapsed()})
        if self._state_elapsed() >= self.course_correct_seconds:
            self._set_state(self.resume_after_obstacle or self._route_state_for_step(), "course correction done")
            self.resume_after_obstacle = None

    def _run_aligning_yaw(self):
        if self._target_yaw is None:
            self._set_state(self.NAV_FAULT, "missing target yaw")
            self._stop()
            return

        err = self._normalize(self._target_yaw - self.robot_yaw)
        if abs(err) < self.yaw_tol:
            self._rot_settle += 1
            self._stop()
            if self._rot_settle >= self.yaw_settle_ticks:
                self._target_yaw = None
                self._rot_settle = 0
                self._finish_current_step()
            return

        self._rot_settle = 0
        cmd = Twist()
        cmd.angular.z = self._clamp(-self.kp_rotate * err, -self.max_turn, self.max_turn)
        if self._tick % 5 == 0:
            self.get_logger().info(
                f"[NAV_ALIGNING_YAW] yaw={math.degrees(self.robot_yaw):.1f} "
                f"target={math.degrees(self._target_yaw):.1f} err={math.degrees(err):.1f}"
            )
        self.cmd_pub.publish(cmd)

    def _finish_current_step(self):
        step = self._current_step()
        previous_name = "HOME" if self.step_index == 0 else self.route_local[self.step_index - 1].name
        self._publish_segment(previous_name, step.name)

        if step.name == "HOME" and self.step_index == len(self.route_local) - 1:
            self.completed = True
            self._set_state(self.NAV_COMPLETE, f"route complete at HOME ({self.robot_x:.2f}, {self.robot_y:.2f})")
            summary = String()
            summary.data = json.dumps(
                {
                    "route_id": self.route_def.route_id,
                    "route_name": self.route_def.display_name,
                    "completed_segments": [[a, b] for a, b in self.completed_segments],
                    "position": [self.robot_x, self.robot_y],
                }
            )
            self.nav_summary_pub.publish(summary)
            self.get_logger().info(f"[DONE] {self.route_def.display_name}")
            return

        self.step_index += 1
        self._enter_motion_state()


def main_for_route(route_id: str, node_name: str):
    rclpy.init()
    node = NavigationRouteRunner(node_name=node_name, route_id=route_id)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
