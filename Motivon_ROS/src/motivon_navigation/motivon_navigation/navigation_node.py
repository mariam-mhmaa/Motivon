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
from motivon_interfaces.msg import NavigationStatus, ObstacleState
from nav_msgs.msg import Odometry
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from std_msgs.msg import String
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
        self.create_subscription(
            ObstacleState,
            "/obstacle/state",
            self._obstacle_callback,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            String,
            "/safety/state",
            self._safety_callback,
            10,
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
        self.latest_obstacle: Optional[ObstacleState] = None
        self.stage_before_obstacle_wait = ""
        self.safety_stop = False
        self.stage_before_safety_pause = ""
        self.avoidance_waypoints = []
        self.avoidance_index = 0
        self.avoidance_segment_start: Optional[Waypoint] = None
        self.avoidance_best_distance = math.inf
        self.avoidance_mode = ""
        self.side_avoidance = {}

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
            "maximum_speed_mps": 0.10,
            "maximum_cross_track_speed_mps": 0.14,
            "maximum_turn_rate_rad_s": 0.50,
            "maximum_linear_acceleration_mps2": 0.45,
            "maximum_angular_acceleration_rad_s2": 1.00,
            "along_track_gain": 0.80,
            "cross_track_gain": 1.00,
            "final_position_gain": 0.80,
            "yaw_hold_gain": 1.50,
            "yaw_alignment_gain": 1.20,
            "final_approach_radius_m": 0.30,
            "connector_tolerance_m": 0.10,
            "station_tolerance_m": 0.05,
            "home_tolerance_m": 0.05,
            "yaw_tolerance_rad": 0.035,
            "arrival_settle_samples": 10,
            "yaw_settle_samples": 18,
            "odometry_stale_timeout_s": 1.20,
            "odometry_abort_timeout_s": 5.00,
            "localization_recovery_samples": 5,
            "maximum_pose_jump_m": 0.40,
            "maximum_yaw_jump_rad": 0.70,
            "progress_timeout_s": 10.0,
            "progress_epsilon_m": 0.015,
            "enable_static_avoidance": True,
            "avoidance_lateral_m": 0.65,
            "avoidance_forward_m": 1.00,
            "side_avoidance_longitudinal_search_m": 1.20,
            "side_avoidance_longitudinal_margin_m": 0.38,
            "side_avoidance_lateral_search_m": 0.90,
            "side_avoidance_lateral_margin_m": 0.34,
            "side_avoidance_edge_seen_cm": 45.0,
            "side_avoidance_edge_clear_cm": 60.0,
            "front_avoidance_lateral_search_m": 0.90,
            "front_avoidance_lateral_margin_m": 0.34,
            "front_avoidance_longitudinal_search_m": 1.20,
            "front_avoidance_longitudinal_margin_m": 0.38,
            "front_avoidance_edge_seen_cm": 45.0,
            "front_avoidance_edge_clear_cm": 60.0,
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
        self.enable_static_avoidance = bool(
            self.get_parameter("enable_static_avoidance").value
        )
        self.avoidance_lateral_m = float(
            self.get_parameter("avoidance_lateral_m").value
        )
        self.avoidance_forward_m = float(
            self.get_parameter("avoidance_forward_m").value
        )
        self.side_avoidance_longitudinal_search_m = float(
            self.get_parameter(
                "side_avoidance_longitudinal_search_m"
            ).value
        )
        self.side_avoidance_longitudinal_margin_m = float(
            self.get_parameter(
                "side_avoidance_longitudinal_margin_m"
            ).value
        )
        self.side_avoidance_lateral_search_m = float(
            self.get_parameter("side_avoidance_lateral_search_m").value
        )
        self.side_avoidance_lateral_margin_m = float(
            self.get_parameter("side_avoidance_lateral_margin_m").value
        )
        self.side_avoidance_edge_seen_cm = float(
            self.get_parameter("side_avoidance_edge_seen_cm").value
        )
        self.side_avoidance_edge_clear_cm = float(
            self.get_parameter("side_avoidance_edge_clear_cm").value
        )
        self.front_avoidance_lateral_search_m = float(
            self.get_parameter("front_avoidance_lateral_search_m").value
        )
        self.front_avoidance_lateral_margin_m = float(
            self.get_parameter("front_avoidance_lateral_margin_m").value
        )
        self.front_avoidance_longitudinal_search_m = float(
            self.get_parameter(
                "front_avoidance_longitudinal_search_m"
            ).value
        )
        self.front_avoidance_longitudinal_margin_m = float(
            self.get_parameter(
                "front_avoidance_longitudinal_margin_m"
            ).value
        )
        self.front_avoidance_edge_seen_cm = float(
            self.get_parameter("front_avoidance_edge_seen_cm").value
        )
        self.front_avoidance_edge_clear_cm = float(
            self.get_parameter("front_avoidance_edge_clear_cm").value
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
            self.avoidance_lateral_m,
            self.avoidance_forward_m,
            self.side_avoidance_longitudinal_search_m,
            self.side_avoidance_longitudinal_margin_m,
            self.side_avoidance_lateral_search_m,
            self.side_avoidance_lateral_margin_m,
            self.side_avoidance_edge_seen_cm,
            self.side_avoidance_edge_clear_cm,
            self.front_avoidance_lateral_search_m,
            self.front_avoidance_lateral_margin_m,
            self.front_avoidance_longitudinal_search_m,
            self.front_avoidance_longitudinal_margin_m,
            self.front_avoidance_edge_seen_cm,
            self.front_avoidance_edge_clear_cm,
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

    def _obstacle_callback(self, message: ObstacleState) -> None:
        with self.state_lock:
            self.latest_obstacle = message

    def _safety_callback(self, message: String) -> None:
        safety_state = message.data.strip().upper()
        with self.state_lock:
            self.safety_stop = safety_state not in (
                "",
                "OK",
                "CLEAR",
                "READY",
            )

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
        self.avoidance_best_distance = math.inf
        self.avoidance_waypoints = []
        self.avoidance_index = 0
        self.avoidance_segment_start = None
        self.avoidance_mode = ""
        self.side_avoidance = {}
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
            if self._handle_safety_pause(now_ns):
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
                if self._handle_navigation_obstacle(pose, now_ns):
                    self._publish_status(now_ns)
                    return
                self._run_translation(pose, now_ns)
            elif self.stage == "WAITING_FOR_OBSTACLE":
                if self._handle_navigation_obstacle(pose, now_ns):
                    self._publish_status(now_ns)
                    return
                self.stage = self.stage_before_obstacle_wait or "NAVIGATING"
                self.detail = "Obstacle cleared; resuming navigation."
                self.last_progress_ns = now_ns
                self.best_distance = math.inf
                self._run_translation(pose, now_ns)
            elif self.stage == "DETOURING":
                self._run_avoidance_translation(pose, now_ns)
            elif self.stage == "ALIGNING_FINAL":
                self._run_yaw_alignment(
                    pose, self.active_path.final_yaw, "HOLDING"
                )
            elif self.stage == "HOLDING":
                self._run_hold(now_ns)
            self._publish_status(now_ns)

    def _handle_safety_pause(self, now_ns: int) -> bool:
        if self.safety_stop:
            self._stop_immediately()
            if self.stage != "SAFETY_PAUSED":
                self.stage_before_safety_pause = self.stage
                self.stage = "SAFETY_PAUSED"
                self.get_logger().warning(
                    "Navigation paused for safety stop."
                )
            self.detail = "Safety stop active; holding navigation goal."
            self.last_progress_ns = now_ns
            return True

        if self.stage == "SAFETY_PAUSED":
            self.stage = self.stage_before_safety_pause or "NAVIGATING"
            self.stage_before_safety_pause = ""
            self.detail = "Safety stop cleared; resuming navigation."
            self.localization_pause_started_ns = None
            self.localization_recovery_count = 0
            self.last_progress_ns = now_ns
            self.best_distance = math.inf
        return False

    def _handle_navigation_obstacle(
        self, pose: Pose2D, now_ns: int
    ) -> bool:
        obstacle = self.latest_obstacle
        if obstacle is None or not obstacle.blocked:
            return False

        if (
            obstacle.static_obstacle
            and self.enable_static_avoidance
            and obstacle.blocked_direction in (
                "front", "back", "left", "right"
            )
        ):
            self._start_static_avoidance(pose, obstacle, now_ns)
            return True

        self._stop_immediately()
        if self.stage != "WAITING_FOR_OBSTACLE":
            self.stage_before_obstacle_wait = self.stage
            self.stage = "WAITING_FOR_OBSTACLE"
            self.get_logger().warning(
                "Navigation paused for obstacle: "
                f"{obstacle.state}, direction={obstacle.blocked_direction}, "
                f"detail={obstacle.detail}"
            )
        self.detail = (
            f"Waiting for obstacle to clear: {obstacle.blocked_direction} "
            f"({obstacle.state})."
        )
        self.last_progress_ns = now_ns
        return True

    def _start_static_avoidance(
        self, pose: Pose2D, obstacle: ObstacleState, now_ns: int
    ) -> None:
        if obstacle.blocked_direction in ("left", "right"):
            self._start_side_static_avoidance(pose, obstacle, now_ns)
            return
        self._start_front_back_static_avoidance(pose, obstacle, now_ns)

    def _start_front_back_static_avoidance(
        self, pose: Pose2D, obstacle: ObstacleState, now_ns: int
    ) -> None:
        detour_side = obstacle.recommended_detour_side
        if detour_side not in ("left", "right"):
            detour_side = "left"
        blocked_direction = obstacle.blocked_direction
        side_sign = 1.0 if detour_side == "left" else -1.0
        longitudinal_sign = -1.0 if blocked_direction == "back" else 1.0
        self.avoidance_mode = "front_back_static"
        self.side_avoidance = {
            "blocked_direction": blocked_direction,
            "detour_side": detour_side,
            "obstacle_side": self._opposite_side(detour_side),
            "side_sign": side_sign,
            "longitudinal_sign": longitudinal_sign,
            "start_x": pose.x,
            "start_y": pose.y,
            "edge_seen": False,
            "lateral_offset_m": 0.0,
        }
        self.avoidance_best_distance = math.inf
        self.position_settle_count = 0
        self.last_progress_ns = now_ns
        self._begin_side_avoidance_leg(
            pose,
            "FRONT_LATERAL_FIND_EDGE",
            "lateral",
            side_sign,
            self.front_avoidance_lateral_search_m,
            now_ns,
        )
        self.stage = "DETOURING"
        self.detail = (
            "Front/back static obstacle avoidance started: "
            f"blocked={blocked_direction}, side={detour_side}."
        )
        self.get_logger().warning(self.detail)

    def _start_side_static_avoidance(
        self, pose: Pose2D, obstacle: ObstacleState, now_ns: int
    ) -> None:
        detour_direction = obstacle.recommended_detour_side
        if detour_direction not in ("front", "back"):
            detour_direction = "front"
        blocked_side = obstacle.blocked_direction
        side_sign = 1.0 if blocked_side == "left" else -1.0
        longitudinal_sign = 1.0 if detour_direction == "front" else -1.0
        self.avoidance_mode = "side_static"
        self.side_avoidance = {
            "blocked_side": blocked_side,
            "detour_direction": detour_direction,
            "side_sign": side_sign,
            "longitudinal_sign": longitudinal_sign,
            "start_x": pose.x,
            "start_y": pose.y,
            "edge_seen": False,
            "longitudinal_offset_m": 0.0,
        }
        self.avoidance_best_distance = math.inf
        self.position_settle_count = 0
        self.last_progress_ns = now_ns
        self._begin_side_avoidance_leg(
            pose,
            "SIDE_LONGITUDINAL_FIND_EDGE",
            "longitudinal",
            longitudinal_sign,
            self.side_avoidance_longitudinal_search_m,
            now_ns,
        )
        self.stage = "DETOURING"
        self.detail = (
            "Side static obstacle avoidance started: "
            f"blocked={blocked_side}, detour={detour_direction}."
        )
        self.get_logger().warning(self.detail)

    def _begin_side_avoidance_leg(
        self,
        pose: Pose2D,
        leg_name: str,
        axis: str,
        direction_sign: float,
        distance_m: float,
        now_ns: int,
    ) -> None:
        forward_x = math.cos(self.active_travel_yaw)
        forward_y = math.sin(self.active_travel_yaw)
        left_x = -math.sin(self.active_travel_yaw)
        left_y = math.cos(self.active_travel_yaw)
        if axis == "longitudinal":
            delta_x = forward_x * direction_sign * distance_m
            delta_y = forward_y * direction_sign * distance_m
        else:
            delta_x = left_x * direction_sign * distance_m
            delta_y = left_y * direction_sign * distance_m

        self.side_avoidance["leg"] = leg_name
        self.side_avoidance["axis"] = axis
        self.side_avoidance["leg_start_x"] = pose.x
        self.side_avoidance["leg_start_y"] = pose.y
        self.side_avoidance["target_x"] = pose.x + delta_x
        self.side_avoidance["target_y"] = pose.y + delta_y
        self.avoidance_segment_start = Waypoint(
            f"{leg_name.lower()}_start", pose.x, pose.y, "connector"
        )
        self.avoidance_waypoints = [
            Waypoint(
                leg_name.lower(),
                self.side_avoidance["target_x"],
                self.side_avoidance["target_y"],
                "connector",
            )
        ]
        self.avoidance_index = 0
        self.avoidance_best_distance = math.inf
        self.position_settle_count = 0
        self.last_progress_ns = now_ns

    def _run_avoidance_translation(
        self, pose: Pose2D, now_ns: int
    ) -> None:
        if self.avoidance_mode == "side_static":
            self._run_side_static_avoidance(pose, now_ns)
            return
        if self.avoidance_mode == "front_back_static":
            self._run_front_back_static_avoidance(pose, now_ns)
            return

        if (
            not self.avoidance_waypoints
            or self.avoidance_segment_start is None
            or self.avoidance_index >= len(self.avoidance_waypoints)
        ):
            self._finish_static_avoidance(now_ns)
            return

        target = self.avoidance_waypoints[self.avoidance_index]
        tracking = tracking_command(
            pose,
            self.avoidance_segment_start,
            target,
            self.active_travel_yaw,
            self.settings,
        )
        self.last_tracking_distance = tracking.distance
        self.last_cross_track_error = tracking.cross_track_error
        self.last_yaw_error = tracking.yaw_error

        if tracking.distance <= self.connector_tolerance:
            self.position_settle_count += 1
            self._stop_immediately()
            if self.position_settle_count >= self.arrival_settle_samples:
                reached = target
                self.avoidance_index += 1
                self.avoidance_segment_start = reached
                self.avoidance_best_distance = math.inf
                self.position_settle_count = 0
                self.last_progress_ns = now_ns
                if self.avoidance_index >= len(self.avoidance_waypoints):
                    self._finish_static_avoidance(now_ns)
                else:
                    self.detail = (
                        "Static obstacle detour continuing to "
                        f"{self.avoidance_waypoints[self.avoidance_index].name}."
                    )
            return

        self.position_settle_count = 0
        if tracking.distance <= (
            self.avoidance_best_distance - self.progress_epsilon
        ):
            self.avoidance_best_distance = tracking.distance
            self.last_progress_ns = now_ns
        elif now_ns - self.last_progress_ns >= self.progress_timeout_ns:
            self._fail(
                NavigateToTarget.Result.STATUS_STALLED,
                f"No progress during static obstacle detour to {target.name}.",
            )
            return

        command = Twist()
        command.linear.x = tracking.body_vx
        command.linear.y = tracking.body_vy
        command.angular.z = tracking.angular_z
        self._publish_limited(command)

    def _run_front_back_static_avoidance(
        self, pose: Pose2D, now_ns: int
    ) -> None:
        if (
            not self.avoidance_waypoints
            or self.avoidance_segment_start is None
            or not self.side_avoidance
        ):
            self._finish_static_avoidance(now_ns)
            return

        leg = str(self.side_avoidance.get("leg", ""))
        target = self.avoidance_waypoints[0]
        tracking = tracking_command(
            pose,
            self.avoidance_segment_start,
            target,
            self.active_travel_yaw,
            self.settings,
        )
        self.last_tracking_distance = tracking.distance
        self.last_cross_track_error = tracking.cross_track_error
        self.last_yaw_error = tracking.yaw_error

        sensor_finished = self._front_back_avoidance_sensor_finished(leg)
        target_finished = tracking.distance <= self.connector_tolerance
        if sensor_finished or target_finished:
            self.position_settle_count += 1
            self._stop_immediately()
            if self.position_settle_count >= self.arrival_settle_samples:
                self._advance_front_back_avoidance_leg(pose, now_ns)
            return

        self.position_settle_count = 0
        if tracking.distance <= (
            self.avoidance_best_distance - self.progress_epsilon
        ):
            self.avoidance_best_distance = tracking.distance
            self.last_progress_ns = now_ns
        elif now_ns - self.last_progress_ns >= self.progress_timeout_ns:
            self._fail(
                NavigateToTarget.Result.STATUS_STALLED,
                f"No progress during front/back obstacle detour {leg}.",
            )
            return

        command = Twist()
        command.linear.x = tracking.body_vx
        command.linear.y = tracking.body_vy
        command.angular.z = tracking.angular_z
        self._publish_limited(command)

    def _front_back_avoidance_sensor_finished(self, leg: str) -> bool:
        if leg == "FRONT_LATERAL_FIND_EDGE":
            blocked_direction = str(
                self.side_avoidance.get("blocked_direction", "")
            )
            return self._obstacle_distance_is_clear(
                blocked_direction, self.front_avoidance_edge_clear_cm
            )

        if leg == "FRONT_LONGITUDINAL_FIND_EDGE":
            obstacle_side = str(self.side_avoidance.get("obstacle_side", ""))
            if self._obstacle_distance_is_blocked(
                obstacle_side, self.front_avoidance_edge_seen_cm
            ):
                self.side_avoidance["edge_seen"] = True
                return False
            return bool(
                self.side_avoidance.get("edge_seen", False)
            ) and self._obstacle_distance_is_clear(
                obstacle_side, self.front_avoidance_edge_clear_cm
            )

        return False

    @staticmethod
    def _opposite_side(side: str) -> str:
        if side == "left":
            return "right"
        if side == "right":
            return "left"
        return ""

    def _advance_front_back_avoidance_leg(
        self, pose: Pose2D, now_ns: int
    ) -> None:
        leg = str(self.side_avoidance.get("leg", ""))
        longitudinal_sign = float(
            self.side_avoidance.get("longitudinal_sign", 1.0)
        )
        side_sign = float(self.side_avoidance.get("side_sign", 1.0))

        if leg == "FRONT_LATERAL_FIND_EDGE":
            self._begin_side_avoidance_leg(
                pose,
                "FRONT_LATERAL_MARGIN",
                "lateral",
                side_sign,
                self.front_avoidance_lateral_margin_m,
                now_ns,
            )
            self.detail = "Front/back detour: adding lateral margin."
            return

        if leg == "FRONT_LATERAL_MARGIN":
            start_x = float(self.side_avoidance.get("start_x", pose.x))
            start_y = float(self.side_avoidance.get("start_y", pose.y))
            left_x = -math.sin(self.active_travel_yaw)
            left_y = math.cos(self.active_travel_yaw)
            offset = (
                (pose.x - start_x) * left_x
                + (pose.y - start_y) * left_y
            )
            self.side_avoidance["lateral_offset_m"] = offset
            self.side_avoidance["edge_seen"] = False
            self._begin_side_avoidance_leg(
                pose,
                "FRONT_LONGITUDINAL_FIND_EDGE",
                "longitudinal",
                longitudinal_sign,
                self.front_avoidance_longitudinal_search_m,
                now_ns,
            )
            self.detail = (
                "Front/back detour: moving along obstacle to far edge."
            )
            return

        if leg == "FRONT_LONGITUDINAL_FIND_EDGE":
            self._begin_side_avoidance_leg(
                pose,
                "FRONT_LONGITUDINAL_MARGIN",
                "longitudinal",
                longitudinal_sign,
                self.front_avoidance_longitudinal_margin_m,
                now_ns,
            )
            self.detail = "Front/back detour: adding longitudinal margin."
            return

        if leg == "FRONT_LONGITUDINAL_MARGIN":
            offset = float(
                self.side_avoidance.get("lateral_offset_m", 0.0)
            )
            if abs(offset) <= self.connector_tolerance:
                self._finish_static_avoidance(now_ns)
                return
            return_sign = -1.0 if offset > 0.0 else 1.0
            self._begin_side_avoidance_leg(
                pose,
                "FRONT_RETURN_PATH",
                "lateral",
                return_sign,
                abs(offset),
                now_ns,
            )
            self.detail = "Front/back detour: returning to original path line."
            return

        if leg == "FRONT_RETURN_PATH":
            self._finish_static_avoidance(now_ns)
            return

        self._finish_static_avoidance(now_ns)

    def _run_side_static_avoidance(
        self, pose: Pose2D, now_ns: int
    ) -> None:
        if (
            not self.avoidance_waypoints
            or self.avoidance_segment_start is None
            or not self.side_avoidance
        ):
            self._finish_static_avoidance(now_ns)
            return

        leg = str(self.side_avoidance.get("leg", ""))
        target = self.avoidance_waypoints[0]
        tracking = tracking_command(
            pose,
            self.avoidance_segment_start,
            target,
            self.active_travel_yaw,
            self.settings,
        )
        self.last_tracking_distance = tracking.distance
        self.last_cross_track_error = tracking.cross_track_error
        self.last_yaw_error = tracking.yaw_error

        sensor_finished = self._side_avoidance_sensor_finished(leg)
        target_finished = tracking.distance <= self.connector_tolerance
        if sensor_finished or target_finished:
            self.position_settle_count += 1
            self._stop_immediately()
            if self.position_settle_count >= self.arrival_settle_samples:
                self._advance_side_avoidance_leg(pose, now_ns)
            return

        self.position_settle_count = 0
        if tracking.distance <= (
            self.avoidance_best_distance - self.progress_epsilon
        ):
            self.avoidance_best_distance = tracking.distance
            self.last_progress_ns = now_ns
        elif now_ns - self.last_progress_ns >= self.progress_timeout_ns:
            self._fail(
                NavigateToTarget.Result.STATUS_STALLED,
                f"No progress during side obstacle detour {leg}.",
            )
            return

        command = Twist()
        command.linear.x = tracking.body_vx
        command.linear.y = tracking.body_vy
        command.angular.z = tracking.angular_z
        self._publish_limited(command)

    def _side_avoidance_sensor_finished(self, leg: str) -> bool:
        if leg == "SIDE_LONGITUDINAL_FIND_EDGE":
            blocked_side = str(self.side_avoidance.get("blocked_side", ""))
            return self._obstacle_distance_is_clear(
                blocked_side, self.side_avoidance_edge_clear_cm
            )

        if leg == "SIDE_STRAFE_FIND_EDGE":
            detour_direction = str(
                self.side_avoidance.get("detour_direction", "")
            )
            if self._obstacle_distance_is_blocked(
                detour_direction, self.side_avoidance_edge_seen_cm
            ):
                self.side_avoidance["edge_seen"] = True
                return False
            return bool(
                self.side_avoidance.get("edge_seen", False)
            ) and self._obstacle_distance_is_clear(
                detour_direction, self.side_avoidance_edge_clear_cm
            )

        return False

    def _advance_side_avoidance_leg(
        self, pose: Pose2D, now_ns: int
    ) -> None:
        leg = str(self.side_avoidance.get("leg", ""))
        longitudinal_sign = float(
            self.side_avoidance.get("longitudinal_sign", 1.0)
        )
        side_sign = float(self.side_avoidance.get("side_sign", 1.0))

        if leg == "SIDE_LONGITUDINAL_FIND_EDGE":
            self._begin_side_avoidance_leg(
                pose,
                "SIDE_LONGITUDINAL_MARGIN",
                "longitudinal",
                longitudinal_sign,
                self.side_avoidance_longitudinal_margin_m,
                now_ns,
            )
            self.detail = "Side detour: adding longitudinal margin."
            return

        if leg == "SIDE_LONGITUDINAL_MARGIN":
            start_x = float(self.side_avoidance.get("start_x", pose.x))
            start_y = float(self.side_avoidance.get("start_y", pose.y))
            forward_x = math.cos(self.active_travel_yaw)
            forward_y = math.sin(self.active_travel_yaw)
            offset = (
                (pose.x - start_x) * forward_x
                + (pose.y - start_y) * forward_y
            )
            self.side_avoidance["longitudinal_offset_m"] = offset
            self.side_avoidance["edge_seen"] = False
            self._begin_side_avoidance_leg(
                pose,
                "SIDE_STRAFE_FIND_EDGE",
                "lateral",
                side_sign,
                self.side_avoidance_lateral_search_m,
                now_ns,
            )
            self.detail = "Side detour: continuing strafe past far edge."
            return

        if leg == "SIDE_STRAFE_FIND_EDGE":
            self._begin_side_avoidance_leg(
                pose,
                "SIDE_STRAFE_MARGIN",
                "lateral",
                side_sign,
                self.side_avoidance_lateral_margin_m,
                now_ns,
            )
            self.detail = "Side detour: adding lateral body margin."
            return

        if leg == "SIDE_STRAFE_MARGIN":
            offset = float(
                self.side_avoidance.get("longitudinal_offset_m", 0.0)
            )
            if abs(offset) <= self.connector_tolerance:
                self._finish_static_avoidance(now_ns)
                return
            return_sign = -1.0 if offset > 0.0 else 1.0
            self._begin_side_avoidance_leg(
                pose,
                "SIDE_RETURN_PATH",
                "longitudinal",
                return_sign,
                abs(offset),
                now_ns,
            )
            self.detail = "Side detour: returning to original path line."
            return

        if leg == "SIDE_RETURN_PATH":
            self._finish_static_avoidance(now_ns)
            return

        self._finish_static_avoidance(now_ns)

    def _obstacle_distance_is_blocked(
        self, direction: str, threshold_cm: float
    ) -> bool:
        value = self._obstacle_distance(direction)
        return value is not None and value <= threshold_cm

    def _obstacle_distance_is_clear(
        self, direction: str, threshold_cm: float
    ) -> bool:
        value = self._obstacle_distance(direction)
        return value is not None and value >= threshold_cm

    def _obstacle_distance(self, direction: str) -> Optional[float]:
        obstacle = self.latest_obstacle
        if obstacle is None:
            return None
        value = None
        if direction == "front":
            value = obstacle.front_cm
        elif direction == "back":
            value = obstacle.back_cm
        elif direction == "left":
            value = obstacle.left_cm
        elif direction == "right":
            value = obstacle.right_cm
        if value is None or not math.isfinite(value) or value <= 0.0:
            return None
        return float(value)

    def _finish_static_avoidance(self, now_ns: int) -> None:
        self.avoidance_waypoints = []
        self.avoidance_index = 0
        self.avoidance_segment_start = None
        self.avoidance_best_distance = math.inf
        self.avoidance_mode = ""
        self.side_avoidance = {}
        self.best_distance = math.inf
        self.position_settle_count = 0
        self.last_progress_ns = now_ns
        self.stage = "NAVIGATING"
        self.detail = "Static obstacle detour complete; resuming route."
        self.get_logger().warning(self.detail)

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
