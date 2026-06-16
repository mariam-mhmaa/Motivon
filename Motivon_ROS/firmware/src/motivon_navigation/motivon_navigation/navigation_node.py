#!/usr/bin/env python3

import math
import threading
import time
import traceback
from typing import Optional, Tuple

import rclpy
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import Twist
from motivon_interfaces.action import NavigateToTarget
from motivon_interfaces.msg import NavigationStatus
from nav_msgs.msg import Odometry
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from std_srvs.srv import Trigger

from motivon_navigation.controller import (
    ControllerSettings,
    clamp,
    limit_vector,
    tracking_command,
)
from motivon_navigation.geometry import (
    HomeTransform,
    Pose2D,
    normalize_angle,
)
from motivon_navigation.route_config import (
    RoutePath,
    Waypoint,
    load_route_map,
)

class NavigationNode(Node):
    def __init__(self) -> None:
        super().__init__("navigation_node")
        self.callback_group = ReentrantCallbackGroup()
        self.state_lock = threading.RLock()

        self._declare_parameters()
        self.route_map = load_route_map(self._route_file())
        self.control_period = 1.0 / float(
            self.get_parameter("control_rate_hz").value
        )
        self.settings = self._controller_settings()
        self._read_safety_parameters()

        odometry_topic = str(
            self.get_parameter("odometry_topic").value
        )
        self.expected_odometry_frame = str(
            self.get_parameter("expected_odometry_frame").value
        )
        self.expected_base_frame = str(
            self.get_parameter("expected_base_frame").value
        )
        command_topic = str(self.get_parameter("command_topic").value)
        self.command_publisher = self.create_publisher(
            Twist, command_topic, qos_profile_sensor_data
        )
        self.status_publisher = self.create_publisher(
            NavigationStatus, "/navigation/status", 10
        )
        self.create_subscription(
            Odometry,
            odometry_topic,
            self._odometry_callback,
            qos_profile_sensor_data,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/navigation/set_home",
            self._set_home_callback,
            callback_group=self.callback_group,
        )
        self.action_server = ActionServer(
            self,
            NavigateToTarget,
            "/navigation/navigate_to_target",
            execute_callback=self._execute_goal,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=self.callback_group,
        )
        self.create_timer(
            self.control_period,
            self._control_callback,
            callback_group=self.callback_group,
        )

        self.latest_odom: Optional[Pose2D] = None
        self.odom_receive_ns: Optional[int] = None
        self.home_transform: Optional[HomeTransform] = None
        self.current_location: Optional[str] = None

        self.goal_reserved = False
        self.active = False
        self.active_path: Optional[RoutePath] = None
        self.active_target = ""
        self.active_waypoint = ""
        self.active_travel_yaw = 0.0
        self.waypoint_index = 0
        self.segment_start = ""
        self.hold_time_s = 0.0
        self.stage = "WAITING_FOR_HOME"
        self.stage_before_odom_wait = ""
        self.detail = "Call /navigation/set_home while positioned at HOME."
        self.outcome: Optional[Tuple[str, int, str]] = None
        self.hold_started_ns: Optional[int] = None
        self.localization_pause_started_ns: Optional[int] = None
        self.localization_pause_count = 0
        self.localization_recovery_count = 0
        self.position_settle_count = 0
        self.yaw_settle_count = 0
        self.best_distance = math.inf
        self.last_progress_ns = 0
        self.last_tracking_distance = 0.0
        self.last_cross_track_error = 0.0
        self.last_yaw_error = 0.0
        self.last_command = Twist()
        self.frame_warning_printed = False

        self.get_logger().info(
            "Navigation ready but disarmed: "
            f"map={self.route_map.width_m:.1f}x"
            f"{self.route_map.height_m:.1f} m, "
            f"HOME=({self.route_map.home.x:.2f}, "
            f"{self.route_map.home.y:.2f}), "
            f"odometry stop threshold="
            f"{self.odom_stale_timeout_ns / 1.0e9:.2f} s."
        )

    def _declare_parameters(self) -> None:
        defaults = {
            "route_file": "",
            "odometry_topic": "/odometry/filtered",
            "expected_odometry_frame": "odom",
            "expected_base_frame": "base_link",
            "command_topic": "/navigation/cmd_vel_raw",
            "control_rate_hz": 20.0,
            "maximum_speed_mps": 0.08,
            "maximum_cross_track_speed_mps": 0.05,
            "maximum_turn_rate_rad_s": 0.30,
            "maximum_linear_acceleration_mps2": 0.20,
            "maximum_angular_acceleration_rad_s2": 0.60,
            "along_track_gain": 0.80,
            "cross_track_gain": 1.00,
            "final_position_gain": 0.80,
            "yaw_hold_gain": 1.50,
            "yaw_alignment_gain": 1.50,
            "final_approach_radius_m": 0.30,
            "connector_tolerance_m": 0.10,
            "station_tolerance_m": 0.05,
            "home_tolerance_m": 0.05,
            "yaw_tolerance_rad": 0.05,
            "arrival_settle_samples": 10,
            "yaw_settle_samples": 10,
            "odometry_stale_timeout_s": 0.30,
            "odometry_abort_timeout_s": 5.00,
            "localization_recovery_samples": 5,
            "maximum_pose_jump_m": 0.40,
            "maximum_yaw_jump_rad": 0.70,
            "progress_timeout_s": 5.0,
            "progress_epsilon_m": 0.015,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

    def _route_file(self) -> str:
        configured = str(self.get_parameter("route_file").value)
        if configured:
            return configured
        share = get_package_share_directory("motivon_navigation")
        return f"{share}/config/routes.yaml"

    def _controller_settings(self) -> ControllerSettings:
        return ControllerSettings(
            maximum_speed=float(
                self.get_parameter("maximum_speed_mps").value
            ),
            maximum_cross_track_speed=float(
                self.get_parameter("maximum_cross_track_speed_mps").value
            ),
            maximum_turn_rate=float(
                self.get_parameter("maximum_turn_rate_rad_s").value
            ),
            along_track_gain=float(
                self.get_parameter("along_track_gain").value
            ),
            cross_track_gain=float(
                self.get_parameter("cross_track_gain").value
            ),
            final_position_gain=float(
                self.get_parameter("final_position_gain").value
            ),
            yaw_hold_gain=float(
                self.get_parameter("yaw_hold_gain").value
            ),
            final_approach_radius=float(
                self.get_parameter("final_approach_radius_m").value
            ),
        )

    def _read_safety_parameters(self) -> None:
        self.maximum_linear_acceleration = float(
            self.get_parameter("maximum_linear_acceleration_mps2").value
        )
        self.maximum_angular_acceleration = float(
            self.get_parameter("maximum_angular_acceleration_rad_s2").value
        )
        self.yaw_alignment_gain = float(
            self.get_parameter("yaw_alignment_gain").value
        )
        self.connector_tolerance = float(
            self.get_parameter("connector_tolerance_m").value
        )
        self.station_tolerance = float(
            self.get_parameter("station_tolerance_m").value
        )
        self.home_tolerance = float(
            self.get_parameter("home_tolerance_m").value
        )
        self.yaw_tolerance = float(
            self.get_parameter("yaw_tolerance_rad").value
        )
        self.arrival_settle_samples = int(
            self.get_parameter("arrival_settle_samples").value
        )
        self.yaw_settle_samples = int(
            self.get_parameter("yaw_settle_samples").value
        )
        self.odom_stale_timeout_ns = int(
            float(self.get_parameter("odometry_stale_timeout_s").value)
            * 1.0e9
        )
        self.odom_abort_timeout_ns = int(
            float(self.get_parameter("odometry_abort_timeout_s").value)
            * 1.0e9
        )
        self.localization_recovery_samples = int(
            self.get_parameter("localization_recovery_samples").value
        )
        self.maximum_pose_jump = float(
            self.get_parameter("maximum_pose_jump_m").value
        )
        self.maximum_yaw_jump = float(
            self.get_parameter("maximum_yaw_jump_rad").value
        )
        self.progress_timeout_ns = int(
            float(self.get_parameter("progress_timeout_s").value) * 1.0e9
        )
        self.progress_epsilon = float(
            self.get_parameter("progress_epsilon_m").value
        )
        positive_values = (
            self.control_period,
            self.settings.maximum_speed,
            self.settings.maximum_cross_track_speed,
            self.settings.maximum_turn_rate,
            self.maximum_linear_acceleration,
            self.maximum_angular_acceleration,
            self.connector_tolerance,
            self.station_tolerance,
            self.home_tolerance,
            self.yaw_tolerance,
            self.odom_stale_timeout_ns,
            self.odom_abort_timeout_ns,
            self.progress_timeout_ns,
            self.maximum_pose_jump,
            self.maximum_yaw_jump,
            self.progress_epsilon,
        )
        if (
            any(value <= 0 for value in positive_values)
            or self.arrival_settle_samples <= 0
            or self.yaw_settle_samples <= 0
            or self.localization_recovery_samples <= 0
            or self.odom_abort_timeout_ns < self.odom_stale_timeout_ns
        ):
            raise ValueError("Navigation timing and limits must be positive.")

    @staticmethod
    def _yaw_from_odometry(message: Odometry) -> float:
        quaternion = message.pose.pose.orientation
        return math.atan2(
            2.0
            * (
                quaternion.w * quaternion.z
                + quaternion.x * quaternion.y
            ),
            1.0
            - 2.0
            * (
                quaternion.y * quaternion.y
                + quaternion.z * quaternion.z
            ),
        )

    def _odometry_callback(self, message: Odometry) -> None:
        if (
            message.header.frame_id != self.expected_odometry_frame
            or message.child_frame_id != self.expected_base_frame
        ):
            if not self.frame_warning_printed:
                self.get_logger().error(
                    "Ignoring odometry with unexpected frames: "
                    f"{message.header.frame_id} -> "
                    f"{message.child_frame_id}; expected "
                    f"{self.expected_odometry_frame} -> "
                    f"{self.expected_base_frame}."
                )
                self.frame_warning_printed = True
            return

        pose = Pose2D(
            float(message.pose.pose.position.x),
            float(message.pose.pose.position.y),
            self._yaw_from_odometry(message),
        )
        if not all(math.isfinite(value) for value in pose.__dict__.values()):
            return

        now_ns = self.get_clock().now().nanoseconds
        with self.state_lock:
            if self.latest_odom is not None and self.active:
                position_jump = math.hypot(
                    pose.x - self.latest_odom.x,
                    pose.y - self.latest_odom.y,
                )
                yaw_jump = abs(
                    normalize_angle(pose.yaw - self.latest_odom.yaw)
                )
                if (
                    position_jump > self.maximum_pose_jump
                    or yaw_jump > self.maximum_yaw_jump
                ):
                    self._fail(
                        NavigateToTarget.Result.STATUS_ODOMETRY_LOST,
                        "Implausible odometry jump detected.",
                    )
            self.latest_odom = pose
            self.odom_receive_ns = now_ns

    def _odom_is_fresh(self, now_ns: int) -> bool:
        return (
            self.latest_odom is not None
            and self.odom_receive_ns is not None
            and now_ns - self.odom_receive_ns
            <= self.odom_stale_timeout_ns
        )

    def _set_home_callback(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        now_ns = self.get_clock().now().nanoseconds
        with self.state_lock:
            if self.active or self.goal_reserved:
                response.success = False
                response.message = "Cannot set HOME while a goal is active."
                return response
            if not self._odom_is_fresh(now_ns):
                response.success = False
                response.message = "Fresh /odometry/filtered data is required."
                return response

            home = self.route_map.home
            self.home_transform = HomeTransform(
                map_home=Pose2D(home.x, home.y, 0.0),
                odom_home=self.latest_odom,
            )
            self.current_location = "HOME"
            self.stage = "IDLE"
            self.detail = (
                f"HOME set at map ({home.x:.2f}, {home.y:.2f}), yaw 0."
            )
            response.success = True
            response.message = self.detail
            self.get_logger().info(self.detail)
            return response

    def _goal_callback(self, request) -> GoalResponse:
        with self.state_lock:
            if self.goal_reserved or self.active:
                return GoalResponse.REJECT
            if self.home_transform is None or self.current_location is None:
                return GoalResponse.REJECT
            now_ns = self.get_clock().now().nanoseconds
            if (
                not self._odom_is_fresh(now_ns)
            ):
                return GoalResponse.REJECT
            if (
                not request.target_name
                or not math.isfinite(request.hold_time_s)
                or request.hold_time_s < 0.0
            ):
                return GoalResponse.REJECT
            try:
                self.route_map.path_between(
                    self.current_location, request.target_name
                )
            except KeyError:
                return GoalResponse.REJECT
            self.goal_reserved = True
            return GoalResponse.ACCEPT

    def _cancel_callback(self, _goal_handle) -> CancelResponse:
        return CancelResponse.ACCEPT

    def _execute_goal(self, goal_handle):
        request = goal_handle.request
        completed_successfully = False
        with self.state_lock:
            try:
                path = self.route_map.path_between(
                    self.current_location, request.target_name
                )
                self._start_path(path, float(request.hold_time_s))
            except Exception as error:
                self.goal_reserved = False
                result = NavigateToTarget.Result()
                result.status = (
                    NavigateToTarget.Result.STATUS_INVALID_ROUTE
                )
                result.target_name = request.target_name
                result.message = str(error)
                goal_handle.abort()
                return result

        try:
            while rclpy.ok():
                if goal_handle.is_cancel_requested:
                    with self.state_lock:
                        self._stop_immediately()
                        self.stage = "CANCELLED"
                        self.detail = "Navigation goal cancelled."
                        self.outcome = (
                            "cancelled",
                            NavigateToTarget.Result.STATUS_CANCELLED,
                            "Navigation goal cancelled.",
                        )
                with self.state_lock:
                    feedback = NavigateToTarget.Feedback()
                    feedback.state = self.stage
                    feedback.active_waypoint = self.active_waypoint
                    feedback.distance_remaining_m = (
                        self.last_tracking_distance
                    )
                    feedback.cross_track_error_m = (
                        self.last_cross_track_error
                    )
                    feedback.yaw_error_rad = self.last_yaw_error
                    outcome = self.outcome
                goal_handle.publish_feedback(feedback)
                if outcome is not None:
                    break
                time.sleep(0.10)

            with self.state_lock:
                outcome = self.outcome or (
                    "failed",
                    NavigateToTarget.Result.STATUS_INTERNAL_ERROR,
                    "ROS shutdown interrupted navigation.",
                )
                result = self._build_result(outcome[1], outcome[2])
                if outcome[0] == "succeeded":
                    self.current_location = self.active_target
                    completed_successfully = True
                    goal_handle.succeed()
                elif outcome[0] == "cancelled":
                    goal_handle.canceled()
                else:
                    goal_handle.abort()
                return result
        except Exception as error:
            error_message = (
                "Unexpected navigation action error: "
                f"{type(error).__name__}: {error}"
            )
            self.get_logger().error(
                error_message + "\n" + traceback.format_exc()
            )
            with self.state_lock:
                self._fail(
                    NavigateToTarget.Result.STATUS_INTERNAL_ERROR,
                    error_message,
                )
                result = self._build_result(
                    NavigateToTarget.Result.STATUS_INTERNAL_ERROR,
                    error_message,
                )
            if goal_handle.is_active:
                goal_handle.abort()
            return result
        finally:
            with self.state_lock:
                self._stop_immediately()
                self.active = False
                self.goal_reserved = False
                if not completed_successfully:
                    self.current_location = None
                self.active_path = None
                self.active_target = ""
                self.active_waypoint = ""
                self.active_travel_yaw = 0.0
                self.last_tracking_distance = 0.0
                self.last_cross_track_error = 0.0
                self.last_yaw_error = 0.0
                if completed_successfully:
                    self.stage = "IDLE"
                elif self.home_transform is not None:
                    self.stage = "REHOME_REQUIRED"
                    self.detail = (
                        "Goal ended away from a verified named point; "
                        "physically rehome and call /navigation/set_home."
                    )
                else:
                    self.stage = "WAITING_FOR_HOME"

    def _start_path(self, path: RoutePath, hold_time_s: float) -> None:
        map_pose = self._map_pose()
        if map_pose is None:
            raise RuntimeError(
                "A mapped pose is required to start navigation."
            )

        self.active = True
        self.goal_reserved = False
        self.active_path = path
        self.active_target = path.target
        self.waypoint_index = 0
        self.active_waypoint = path.waypoint_names[0]
        self.segment_start = path.start
        self.active_travel_yaw = path.travel_yaw
        self.hold_time_s = hold_time_s
        self.outcome = None
        self.hold_started_ns = None
        self.localization_pause_started_ns = None
        self.localization_pause_count = 0
        self.localization_recovery_count = 0
        self.position_settle_count = 0
        self.yaw_settle_count = 0
        self.best_distance = math.inf
        self.last_progress_ns = self.get_clock().now().nanoseconds
        self.stage = (
            "ALIGNING_FOR_TRAVEL"
            if path.align_before_travel
            else "NAVIGATING"
        )
        self.detail = f"Navigating {path.start} -> {path.target}."
        self.get_logger().info(
            self.detail
            + f" Start pose=({map_pose.x:.3f}, {map_pose.y:.3f}, "
            + f"{math.degrees(map_pose.yaw):.2f} deg), "
            + f"travel yaw={math.degrees(self.active_travel_yaw):.2f} deg."
        )

    def _map_pose(self) -> Optional[Pose2D]:
        if self.home_transform is None or self.latest_odom is None:
            return None
        return self.home_transform.odom_to_map(self.latest_odom)

    def _target_waypoint(self) -> Waypoint:
        return self.route_map.waypoints[self.active_waypoint]

    def _segment_start_waypoint(self) -> Waypoint:
        return self.route_map.waypoints[self.segment_start]

    def _target_tolerance(self, target: Waypoint) -> float:
        if target.role == "home":
            return self.home_tolerance
        if target.role == "station":
            return self.station_tolerance
        return self.connector_tolerance

    def _control_callback(self) -> None:
        now_ns = self.get_clock().now().nanoseconds
        with self.state_lock:
            if not self.active:
                self._publish_status(now_ns)
                return
            if self.outcome is not None:
                self._stop_immediately()
                self._publish_status(now_ns)
                return
            if not self._handle_odometry_health(now_ns):
                self._publish_status(now_ns)
                return

            pose = self._map_pose()
            if pose is None or self.active_path is None:
                self._fail(
                    NavigateToTarget.Result.STATUS_INTERNAL_ERROR,
                    "Navigation state is incomplete.",
                )
            elif self.stage == "ALIGNING_FOR_TRAVEL":
                self._run_yaw_alignment(
                    pose, self.active_travel_yaw, "NAVIGATING"
                )
            elif self.stage == "NAVIGATING":
                self._run_translation(pose, now_ns)
            elif self.stage == "ALIGNING_FINAL":
                self._run_yaw_alignment(
                    pose, self.active_path.final_yaw, "HOLDING"
                )
            elif self.stage == "HOLDING":
                self._run_hold(now_ns)
            self._publish_status(now_ns)

    def _handle_odometry_health(self, now_ns: int) -> bool:
        odometry_fresh = self._odom_is_fresh(now_ns)
        if odometry_fresh:
            if self.stage == "WAITING_FOR_ODOMETRY":
                self.localization_recovery_count += 1
                self._stop_immediately()
                if (
                    self.localization_recovery_count
                    < self.localization_recovery_samples
                ):
                    self.detail = (
                        "Localization data is recovering; holding stopped "
                        f"({self.localization_recovery_count}/"
                        f"{self.localization_recovery_samples})."
                    )
                    return False
                pause_started_ns = (
                    self.localization_pause_started_ns
                    if self.localization_pause_started_ns is not None
                    else now_ns
                )
                paused_s = (now_ns - pause_started_ns) / 1.0e9
                self.stage = self.stage_before_odom_wait
                self.detail = (
                    "Localization stable and recovered after "
                    f"{paused_s:.2f} s; continuing."
                )
                self.get_logger().warning(self.detail)
                self.localization_pause_started_ns = None
                self.localization_recovery_count = 0
                self.last_progress_ns = now_ns
            return True

        self.localization_recovery_count = 0
        self._stop_immediately()
        if self.localization_pause_started_ns is None:
            self.localization_pause_started_ns = now_ns
            self.localization_pause_count += 1
            self.stage_before_odom_wait = self.stage
            self.stage = "WAITING_FOR_ODOMETRY"
            self.detail = (
                "Filtered odometry stale; robot stopped "
                f"(pause {self.localization_pause_count})."
            )
            self.get_logger().warning(self.detail)

        odometry_age_ns = (
            math.inf
            if self.odom_receive_ns is None
            else now_ns - self.odom_receive_ns
        )
        if odometry_age_ns >= self.odom_abort_timeout_ns:
            self._fail(
                NavigateToTarget.Result.STATUS_ODOMETRY_LOST,
                "Filtered odometry did not recover before "
                "the abort timeout.",
            )
        return False

    def _run_yaw_alignment(
        self, pose: Pose2D, desired_yaw: float, next_stage: str
    ) -> None:
        yaw_error = normalize_angle(desired_yaw - pose.yaw)
        self.last_yaw_error = yaw_error
        self.last_tracking_distance = 0.0
        self.last_cross_track_error = 0.0
        if abs(yaw_error) <= self.yaw_tolerance:
            self.yaw_settle_count += 1
            self._stop_immediately()
            if self.yaw_settle_count >= self.yaw_settle_samples:
                self.yaw_settle_count = 0
                self.stage = next_stage
                if next_stage == "HOLDING":
                    self.hold_started_ns = None
                self.detail = f"Yaw aligned; entering {next_stage}."
            return

        self.yaw_settle_count = 0
        command = Twist()
        command.angular.z = clamp(
            self.yaw_alignment_gain * yaw_error,
            -self.settings.maximum_turn_rate,
            self.settings.maximum_turn_rate,
        )
        self._publish_limited(command)

    def _run_translation(self, pose: Pose2D, now_ns: int) -> None:
        target = self._target_waypoint()
        start = self._segment_start_waypoint()
        tracking = tracking_command(
            pose,
            start,
            target,
            self.active_travel_yaw,
            self.settings,
        )
        self.last_tracking_distance = tracking.distance
        self.last_cross_track_error = tracking.cross_track_error
        self.last_yaw_error = tracking.yaw_error

        if tracking.distance <= self._target_tolerance(target):
            self.position_settle_count += 1
            self._stop_immediately()
            if self.position_settle_count >= self.arrival_settle_samples:
                self._advance_waypoint(now_ns)
            return

        self.position_settle_count = 0
        if tracking.distance <= self.best_distance - self.progress_epsilon:
            self.best_distance = tracking.distance
            self.last_progress_ns = now_ns
        elif now_ns - self.last_progress_ns >= self.progress_timeout_ns:
            self._fail(
                NavigateToTarget.Result.STATUS_STALLED,
                f"No progress toward {target.name}.",
            )
            return

        command = Twist()
        command.linear.x = tracking.body_vx
        command.linear.y = tracking.body_vy
        command.angular.z = tracking.angular_z
        self._publish_limited(command)

    def _advance_waypoint(self, now_ns: int) -> None:
        reached_name = self.active_waypoint
        self.position_settle_count = 0
        if self.waypoint_index + 1 < len(
            self.active_path.waypoint_names
        ):
            self.waypoint_index += 1
            self.segment_start = reached_name
            self.active_waypoint = self.active_path.waypoint_names[
                self.waypoint_index
            ]
            self.best_distance = math.inf
            self.last_progress_ns = now_ns
            self.detail = (
                f"Reached {reached_name}; continuing to "
                f"{self.active_waypoint}."
            )
            return

        self.detail = f"Reached final target {reached_name}."
        if self.active_path.final_yaw is not None:
            self.stage = "ALIGNING_FINAL"
            self.yaw_settle_count = 0
        else:
            self.stage = "HOLDING"
            self.hold_started_ns = None

    def _run_hold(self, now_ns: int) -> None:
        self._stop_immediately()
        if self.hold_started_ns is None:
            self.hold_started_ns = now_ns
            self.detail = (
                f"Holding at {self.active_target} for "
                f"{self.hold_time_s:.1f} s."
            )
        if now_ns - self.hold_started_ns >= int(self.hold_time_s * 1.0e9):
            self.outcome = (
                "succeeded",
                NavigateToTarget.Result.STATUS_SUCCEEDED,
                f"Arrived at {self.active_target}.",
            )
            self.stage = "SUCCEEDED"

    def _publish_limited(self, desired: Twist) -> None:
        maximum_delta = (
            self.maximum_linear_acceleration * self.control_period
        )
        delta_x = desired.linear.x - self.last_command.linear.x
        delta_y = desired.linear.y - self.last_command.linear.y
        delta_x, delta_y = limit_vector(
            delta_x, delta_y, maximum_delta
        )
        command = Twist()
        command.linear.x = self.last_command.linear.x + delta_x
        command.linear.y = self.last_command.linear.y + delta_y
        angular_delta = clamp(
            desired.angular.z - self.last_command.angular.z,
            -self.maximum_angular_acceleration * self.control_period,
            self.maximum_angular_acceleration * self.control_period,
        )
        command.angular.z = self.last_command.angular.z + angular_delta
        self.command_publisher.publish(command)
        self.last_command = command

    def _stop_immediately(self) -> None:
        command = Twist()
        self.command_publisher.publish(command)
        self.last_command = command

    def _fail(self, status: int, message: str) -> None:
        if self.outcome is None:
            self._stop_immediately()
            self.outcome = ("failed", status, message)
            self.stage = "FAILED"
            self.detail = message
            self.get_logger().error(message)

    def _build_result(self, status: int, message: str):
        result = NavigateToTarget.Result()
        result.status = status
        result.target_name = self.active_target
        result.message = message
        pose = self._map_pose()
        if pose is None or not self.active_target:
            return result
        target = self.route_map.waypoints[self.active_target]
        result.final_x_error_m = pose.x - target.x
        result.final_y_error_m = pose.y - target.y
        desired_yaw = (
            self.active_path.final_yaw
            if self.active_path.final_yaw is not None
            else self.active_travel_yaw
        )
        result.final_yaw_error_rad = normalize_angle(
            pose.yaw - desired_yaw
        )
        return result

    def _publish_status(self, now_ns: int) -> None:
        status = NavigationStatus()
        status.stamp = Time(nanoseconds=now_ns).to_msg()
        status.state = self.stage
        status.target_name = self.active_target
        status.active_waypoint = self.active_waypoint
        status.distance_remaining_m = self.last_tracking_distance
        status.cross_track_error_m = self.last_cross_track_error
        status.yaw_error_rad = self.last_yaw_error
        status.home_set = (
            self.home_transform is not None
            and self.current_location is not None
        )
        status.detail = self.detail
        self.status_publisher.publish(status)

    def destroy_node(self):
        if self.context.ok():
            with self.state_lock:
                self._stop_immediately()
        self.action_server.destroy()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = NavigationNode()
    executor = MultiThreadedExecutor(num_threads=3)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
