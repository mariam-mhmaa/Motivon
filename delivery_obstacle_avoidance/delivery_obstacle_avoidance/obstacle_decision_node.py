import json
import math
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String


def finite_distance(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value) or value <= 0.0:
        return None
    return value


class ObstacleDecisionNode(Node):
    """Classify obstacles and command pose-based avoidance through the ESP bridge."""

    def __init__(self):
        super().__init__("obstacle_decision_node")

        self.declare_parameter("dead_zone_cm", 3.0)
        self.declare_parameter("emergency_stop_cm", 20.0)
        self.declare_parameter("front_blocked_cm", 22.0)
        self.declare_parameter("front_clear_cm", 40.0)
        self.declare_parameter("back_blocked_cm", 22.0)
        self.declare_parameter("back_clear_cm", 40.0)
        self.declare_parameter("side_blocked_cm", 22.0)
        self.declare_parameter("side_motion_clear_cm", 40.0)
        self.declare_parameter("avoidance_side_limit_cm", 22.0)
        self.declare_parameter("static_wait_s", 10.0)
        self.declare_parameter("enable_static_avoidance", True)
        self.declare_parameter("front_clear_confirm_s", 0.40)
        self.declare_parameter("edge_near_max_cm", 45.0)
        self.declare_parameter("edge_far_min_cm", 60.0)
        self.declare_parameter("edge_jump_min_cm", 25.0)
        self.declare_parameter("edge_confirm_samples", 2)
        self.declare_parameter("safety_release_confirm_s", 0.50)
        self.declare_parameter("sensor_stale_timeout_s", 0.35)
        self.declare_parameter("esp_transition_fresh_s", 0.75)
        self.declare_parameter("esp_stale_timeout_s", 2.00)
        self.declare_parameter("startup_sensor_grace_s", 1.00)
        self.declare_parameter("stop_repeat_s", 1.00)
        self.declare_parameter("motion_command_epsilon", 0.02)
        self.declare_parameter("rotation_command_epsilon", 0.10)
        self.declare_parameter("wheel_target_epsilon", 0.05)
        self.declare_parameter("lateral_body_margin_m", 0.34)
        self.declare_parameter("forward_body_margin_m", 0.38)
        self.declare_parameter(
            "side_avoidance_longitudinal_margin_m",
            0.38,
        )
        self.declare_parameter(
            "side_avoidance_lateral_margin_m",
            0.34,
        )
        self.declare_parameter("maximum_lateral_search_m", 0.90)
        self.declare_parameter("maximum_forward_search_m", 1.20)
        self.declare_parameter("pass_obstacle_seen_cm", 45.0)
        self.declare_parameter("pass_obstacle_clear_cm", 60.0)
        self.declare_parameter("avoidance_stage_timeout_s", 15.0)
        self.declare_parameter("avoidance_stall_timeout_s", 3.0)
        self.declare_parameter("avoidance_progress_m", 0.02)
        self.declare_parameter("avoidance_pause_timeout_s", 0.0)
        self.declare_parameter("max_static_replans", 4)
        self.declare_parameter("avoidance_measurement_mode", False)
        self.declare_parameter("avoidance_command_retry_s", 0.50)
        self.declare_parameter("pose_tolerance_m", 0.06)
        self.declare_parameter("yaw_tolerance_deg", 6.0)
        self.declare_parameter("decision_period_s", 0.10)
        self.declare_parameter("resume_saved_target", True)

        self.dead_zone_cm = float(self.get_parameter("dead_zone_cm").value)
        self.emergency_stop_cm = float(self.get_parameter("emergency_stop_cm").value)
        self.front_blocked_cm = float(self.get_parameter("front_blocked_cm").value)
        self.front_clear_cm = float(self.get_parameter("front_clear_cm").value)
        self.back_blocked_cm = float(self.get_parameter("back_blocked_cm").value)
        self.back_clear_cm = float(self.get_parameter("back_clear_cm").value)
        self.side_blocked_cm = float(self.get_parameter("side_blocked_cm").value)
        self.side_motion_clear_cm = float(
            self.get_parameter("side_motion_clear_cm").value
        )
        self.avoidance_side_limit_cm = float(
            self.get_parameter("avoidance_side_limit_cm").value
        )
        self.static_wait_s = float(self.get_parameter("static_wait_s").value)
        self.enable_static_avoidance = bool(
            self.get_parameter("enable_static_avoidance").value
        )
        self.front_clear_confirm_s = float(
            self.get_parameter("front_clear_confirm_s").value
        )
        self.edge_near_max_cm = float(
            self.get_parameter("edge_near_max_cm").value
        )
        self.edge_far_min_cm = float(
            self.get_parameter("edge_far_min_cm").value
        )
        self.edge_jump_min_cm = float(
            self.get_parameter("edge_jump_min_cm").value
        )
        self.edge_confirm_samples = max(
            2,
            int(self.get_parameter("edge_confirm_samples").value),
        )
        self.safety_release_confirm_s = float(
            self.get_parameter("safety_release_confirm_s").value
        )
        self.sensor_stale_timeout_s = float(
            self.get_parameter("sensor_stale_timeout_s").value
        )
        self.esp_transition_fresh_s = float(
            self.get_parameter("esp_transition_fresh_s").value
        )
        self.esp_stale_timeout_s = float(
            self.get_parameter("esp_stale_timeout_s").value
        )
        self.startup_sensor_grace_s = float(
            self.get_parameter("startup_sensor_grace_s").value
        )
        self.stop_repeat_s = float(self.get_parameter("stop_repeat_s").value)
        self.motion_command_epsilon = float(
            self.get_parameter("motion_command_epsilon").value
        )
        self.rotation_command_epsilon = float(
            self.get_parameter("rotation_command_epsilon").value
        )
        self.wheel_target_epsilon = float(
            self.get_parameter("wheel_target_epsilon").value
        )
        self.lateral_body_margin_m = float(
            self.get_parameter("lateral_body_margin_m").value
        )
        self.forward_body_margin_m = float(
            self.get_parameter("forward_body_margin_m").value
        )
        self.side_avoidance_longitudinal_margin_m = float(
            self.get_parameter(
                "side_avoidance_longitudinal_margin_m"
            ).value
        )
        self.side_avoidance_lateral_margin_m = float(
            self.get_parameter("side_avoidance_lateral_margin_m").value
        )
        self.maximum_lateral_search_m = float(
            self.get_parameter("maximum_lateral_search_m").value
        )
        self.maximum_forward_search_m = float(
            self.get_parameter("maximum_forward_search_m").value
        )
        self.pass_obstacle_seen_cm = float(
            self.get_parameter("pass_obstacle_seen_cm").value
        )
        self.pass_obstacle_clear_cm = float(
            self.get_parameter("pass_obstacle_clear_cm").value
        )
        self.avoidance_stage_timeout_s = float(
            self.get_parameter("avoidance_stage_timeout_s").value
        )
        self.avoidance_stall_timeout_s = float(
            self.get_parameter("avoidance_stall_timeout_s").value
        )
        self.avoidance_progress_m = float(
            self.get_parameter("avoidance_progress_m").value
        )
        self.avoidance_pause_timeout_s = float(
            self.get_parameter("avoidance_pause_timeout_s").value
        )
        self.max_static_replans = max(
            1,
            int(self.get_parameter("max_static_replans").value),
        )
        self.avoidance_measurement_mode = bool(
            self.get_parameter("avoidance_measurement_mode").value
        )
        self.avoidance_command_retry_s = float(
            self.get_parameter("avoidance_command_retry_s").value
        )
        self.pose_tolerance_m = float(self.get_parameter("pose_tolerance_m").value)
        self.yaw_tolerance_deg = float(self.get_parameter("yaw_tolerance_deg").value)
        self.resume_saved_target = bool(self.get_parameter("resume_saved_target").value)

        self.command_pub = self.create_publisher(String, "/robot/motion_command", 10)
        self.state_pub = self.create_publisher(String, "/obstacle/state", 10)
        self.operator_command_sub = self.create_subscription(
            String,
            "/operator/motion_command",
            self.on_operator_command,
            10,
        )
        sensor_qos = QoSProfile(depth=1)
        self.scan_sub = self.create_subscription(
            String, "/obstacle/scan", self.on_scan, sensor_qos
        )
        self.raw_scan_sub = self.create_subscription(
            String, "/obstacle/raw_scan", self.on_raw_scan, sensor_qos
        )
        self.esp_data_sub = self.create_subscription(String, "/esp/data", self.on_esp_data, 10)

        self.state = "READY"
        self.distances = {}
        self.raw_distances = {}
        self.esp_data = None
        self.started_s = self.now_s()
        self.last_raw_scan_s = None
        self.last_esp_data_s = None
        self.last_gui_stop_count = None
        self.blocked_since = None
        self.front_clear_since = None
        self.safety_release_since = None
        self.safety_hazard_sensor = None
        self.saved_target = None
        self.saved_pose_mode = False
        self.original_target_resume_pending = False
        self.last_original_target_resume_command_s = None
        self.nominal_path_start = None
        self.nominal_path_goal = None
        self.nominal_path_axis = None
        self.nominal_path_length_m = None
        self.nominal_path_max_progress_m = 0.0
        self.static_replan_count = 0
        self.rejoin_nominal_after_avoidance = False
        self.forbidden_detour_directions = set()
        self.avoidance_pause_obstacle_direction = None
        self.primary_travel_direction = "front"
        self.avoidance_side = None
        self.side_obstacle_direction = None
        self.longitudinal_detour_direction = None
        self.side_avoidance_final_forward_m = None
        self.side_avoidance_final_lateral_m = None
        self.avoidance_origin = None
        self.avoidance_forward_axis = None
        self.avoidance_left_axis = None
        self.avoidance_lateral_limit_m = None
        self.avoidance_final_lateral_m = None
        self.avoidance_target = None
        self.avoidance_stage_started_s = None
        self.avoidance_last_progress_s = None
        self.avoidance_last_progress_pose = None
        self.avoidance_condition_since = None
        self.avoidance_obstacle_seen = False
        self.avoidance_pause_state = None
        self.avoidance_pause_sensor = None
        self.avoidance_pause_started_s = None
        self.avoidance_abort_reason = None
        self.last_avoidance_command_s = None
        self.front_edge_detector = self.new_edge_detector()
        self.rear_edge_detector = self.new_edge_detector()
        self.strafe_measurement = None
        self.measurement_checkpoint = None
        self.measurement_continue_action = None
        self.measurement_checkpoints = []
        self.measurement_settled_recorded = False
        self.last_stop_command_s = 0.0
        self.last_state_log = None
        self.status_reason = ""
        self.status_reason_state = None

        period = float(self.get_parameter("decision_period_s").value)
        self.create_timer(period, self.evaluate)
        self.get_logger().info("Obstacle decision node started.")

    def now_s(self):
        return self.get_clock().now().nanoseconds / 1_000_000_000.0

    def publish_command(self, command):
        msg = String()
        msg.data = json.dumps(command)
        self.command_pub.publish(msg)

    def publish_stop(self, reason, force=False):
        now = self.now_s()
        if not force and now - self.last_stop_command_s < self.stop_repeat_s:
            return
        self.last_stop_command_s = now
        self.get_logger().warn(f"Publishing STOP command: {reason}")
        self.publish_command({"type": "stop", "reason": reason})

    def cancel_supervisor_activity(self, next_state):
        self.state = next_state
        self.blocked_since = None
        self.front_clear_since = None
        self.safety_release_since = None
        self.safety_hazard_sensor = None
        self.saved_target = None
        self.saved_pose_mode = False
        self.original_target_resume_pending = False
        self.last_original_target_resume_command_s = None
        self.reset_nominal_path()
        self.avoidance_abort_reason = None
        self.reset_avoidance()

    @staticmethod
    def state_description(state):
        descriptions = {
            "READY": "Ready for a new movement command",
            "CLEAR": "Path clear; normal movement active",
            "WAITING_DYNAMIC": "Obstacle ahead; stopped and waiting for it to move",
            "PERSISTENT_STOPPED": "Obstacle remains; avoidance is disabled",
            "STATIC_STRAFE_FIND_EDGE": "Avoiding: moving sideways to find the obstacle edge",
            "STATIC_STRAFE_MARGIN": "Avoiding: adding sideways body clearance",
            "STATIC_FORWARD_FIND_EDGE": "Avoiding: moving forward past the obstacle",
            "STATIC_FORWARD_MARGIN": "Avoiding: adding forward body clearance",
            "STATIC_RETURN_WAIT_CLEAR": "Avoiding: checking that the return path is clear",
            "STATIC_RETURN_PATH": "Avoiding: returning to the original path",
            "STATIC_SIDE_LONGITUDINAL_FIND_EDGE": "Side obstacle: moving front or back to find its edge",
            "STATIC_SIDE_LONGITUDINAL_MARGIN": "Side obstacle: adding front or back body clearance",
            "STATIC_SIDE_STRAFE_FIND_EDGE": "Side obstacle: strafing past the obstacle",
            "STATIC_SIDE_STRAFE_MARGIN": "Side obstacle: adding sideways body clearance",
            "STATIC_SIDE_RETURN_WAIT_CLEAR": "Side obstacle: checking the path back to the original line",
            "STATIC_SIDE_RETURN_PATH": "Side obstacle: returning to the original sideways path",
            "STATIC_NOMINAL_REJOIN": "Multiple obstacles cleared: returning to the closest point on the navigation path",
            "MEASUREMENT_PAUSED": "Measurement checkpoint; robot stopped until Continue Measurement",
            "AVOIDANCE_PAUSED": "Temporary obstacle detected; stopped until the movement direction is clear",
            "AVOIDANCE_ABORTED": "Avoidance could not continue; reset is required",
            "SAFETY_STOPPED": "Obstacle in the movement direction; stopped",
            "SENSOR_FAULT": "Ultrasonic data was lost; reset is required",
            "OPERATOR_STOPPED": "Stopped by the operator; reset is required",
            "RESETTING": "Resetting previous trial; confirming the robot is stopped",
            "RESET_REQUIRED": "System recovered but must be reset before moving",
        }
        return descriptions.get(state, state.replace("_", " ").title())

    def reset_is_safe(self):
        if not self.sensor_stream_fresh():
            return False, "ultrasonic_data_not_fresh"
        if not self.esp_stream_fresh() or self.current_pose() is None:
            return False, "esp_data_not_fresh"
        return True, "ready"

    def pose_command_hazard(self, pose_command):
        pose = self.current_pose()
        if pose is None:
            return "missing_current_pose"

        dx = pose_command["x"] - pose["x"]
        dy = pose_command["y"] - pose["y"]
        yaw_rad = math.radians(pose["yaw"])
        forward_error = math.cos(yaw_rad) * dx + math.sin(yaw_rad) * dy
        left_error = -math.sin(yaw_rad) * dx + math.cos(yaw_rad) * dy

        checks = []
        if forward_error > self.pose_tolerance_m:
            checks.append(("front", self.raw_distance("front_center"), self.front_blocked_cm))
        elif forward_error < -self.pose_tolerance_m:
            checks.append(("back", self.raw_distance("back_center"), self.back_blocked_cm))

        if left_error > self.pose_tolerance_m:
            checks.append(("left", self.raw_distance("left"), self.side_blocked_cm))
        elif left_error < -self.pose_tolerance_m:
            checks.append(("right", self.raw_distance("right"), self.side_blocked_cm))

        for direction, value, threshold in checks:
            if value is not None and value <= threshold:
                return f"{direction}_blocked_{value:.1f}_cm"
        return None

    def on_operator_command(self, msg):
        try:
            command = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.get_logger().error(f"Ignoring malformed operator command: {exc}")
            return

        command_type = command.get("type")

        if command_type == "stop":
            self.cancel_supervisor_activity("OPERATOR_STOPPED")
            reason = "operator_stop"
            self.publish_stop("operator_stop", force=True)
            self.get_logger().warn(
                "Operator STOP received; movement remains disabled until Reset Trial."
            )
            self.publish_state({"reason": reason})
            return

        if command_type == "reset_trial":
            safe, reason = self.reset_is_safe()
            if not safe:
                self.cancel_supervisor_activity("RESET_REQUIRED")
                self.publish_stop(f"reset_rejected_{reason}", force=True)
                self.get_logger().error(
                    f"Reset Trial rejected: {reason}. Robot remains stopped."
                )
                self.publish_state({"reason": f"reset_rejected_{reason}"})
                return

            self.cancel_supervisor_activity("RESETTING")
            self.publish_stop("operator_trial_reset_stopping", force=True)
            self.get_logger().warn(
                "Reset Trial accepted. Waiting for ESP confirmation that the robot is stopped."
            )
            self.publish_state({"reason": "operator_trial_reset_stopping"})
            return

        if command_type == "continue_measurement":
            self.continue_measurement_test()
            return

        if command_type in ("zero_pose", "imu_cal"):
            self.cancel_supervisor_activity("OPERATOR_STOPPED")
            self.publish_command({"type": command_type})
            self.get_logger().warn(
                f"Operator command -> {command_type}; Reset Trial is required afterward."
            )
            self.publish_state({"reason": f"operator_{command_type}"})
            return

        if command_type != "pose":
            self.get_logger().error(
                f"Unsupported operator command type: {command_type}"
            )
            return

        try:
            pose_command = {
                "type": "pose",
                "x": float(command["x"]),
                "y": float(command["y"]),
                "yaw": float(command["yaw"]),
                "reason": "operator_pose",
            }
        except (KeyError, TypeError, ValueError) as exc:
            self.get_logger().error(f"Invalid operator pose command: {exc}")
            return

        if not all(
            math.isfinite(pose_command[key])
            for key in ("x", "y", "yaw")
        ):
            self.get_logger().error(
                "Invalid operator pose command: values must be finite."
            )
            return

        if self.state not in ("READY", "CLEAR"):
            self.publish_stop("operator_pose_rejected_reset_required", force=True)
            self.get_logger().error(
                f"Operator pose rejected while state is {self.state}. "
                "Press Reset Trial first."
            )
            self.publish_state({"reason": "pose_rejected_reset_required"})
            return

        if not self.sensor_stream_fresh():
            self.cancel_supervisor_activity("RESET_REQUIRED")
            self.publish_stop("operator_pose_rejected_sensor_stale", force=True)
            self.get_logger().error(
                "Operator pose rejected because ultrasonic data is stale."
            )
            self.publish_state({"reason": "pose_rejected_ultrasonic_data_stale"})
            return

        if not self.esp_stream_fresh() or self.current_pose() is None:
            self.cancel_supervisor_activity("RESET_REQUIRED")
            self.publish_stop("operator_pose_rejected_esp_stale", force=True)
            self.get_logger().error(
                "Operator pose rejected because ESP pose data is unavailable or stale."
            )
            self.publish_state({"reason": "pose_rejected_esp_data_stale"})
            return

        hazard = self.pose_command_hazard(pose_command)
        if hazard is not None:
            self.cancel_supervisor_activity("RESET_REQUIRED")
            self.publish_stop(f"operator_pose_rejected_{hazard}", force=True)
            self.get_logger().error(
                f"Operator pose rejected because the starting direction is blocked: {hazard}."
            )
            self.publish_state({"reason": f"pose_rejected_{hazard}"})
            return

        self.state = "CLEAR"
        self.blocked_since = None
        self.front_clear_since = None
        self.safety_release_since = None
        self.safety_hazard_sensor = None
        self.avoidance_abort_reason = None
        self.original_target_resume_pending = False
        self.last_original_target_resume_command_s = None
        self.reset_avoidance()
        self.initialize_nominal_path(pose_command)
        self.publish_command(pose_command)
        self.get_logger().warn(
            "Operator pose accepted: "
            f"x={pose_command['x']:.3f}, y={pose_command['y']:.3f}, "
            f"yaw={pose_command['yaw']:.1f}"
        )
        self.publish_state({"reason": "operator_pose_started"})

    def publish_state(self, extra=None):
        now = self.now_s()
        state_text = self.state_description(self.state)
        if self.state == "AVOIDANCE_PAUSED" and self.avoidance_pause_sensor:
            state_text = (
                f"Temporary obstacle {self.avoidance_pause_sensor}; "
                "stopped and waiting to continue"
            )
        elif self.state == "AVOIDANCE_ABORTED":
            state_text = (
                "Avoidance stopped safely"
                if not self.avoidance_abort_reason
                else (
                    "Avoidance stopped safely: "
                    f"{self.avoidance_abort_reason.replace('_', ' ')}"
                )
            )
        elif self.state == "MEASUREMENT_PAUSED":
            state_text = (
                f"Measurement checkpoint {self.measurement_checkpoint}; "
                "robot stopped until Continue Measurement"
            )
        final_destination = (
            self.saved_target
            if self.saved_target is not None
            else self.nominal_path_goal
        )
        payload = {
            "state": self.state,
            "state_text": state_text,
            "reason": self.status_reason,
            "final_destination": final_destination,
            "reset_required": self.state in (
                "AVOIDANCE_ABORTED",
                "OPERATOR_STOPPED",
                "RESETTING",
                "RESET_REQUIRED",
                "SENSOR_FAULT",
            ),
            "front_cm": self.front_distance(),
            "back_cm": self.distance("back_center"),
            "left_cm": self.distance("left"),
            "right_cm": self.distance("right"),
            "raw_front_cm": self.raw_distance("front_center"),
            "raw_back_cm": self.raw_distance("back_center"),
            "intended_directions": sorted(self.intended_directions()),
            "sensor_data_age_s": (
                None
                if self.last_raw_scan_s is None
                else max(0.0, now - self.last_raw_scan_s)
            ),
            "esp_data_age_s": self.esp_data_age_s(),
            "esp_pose_mode": (
                None
                if self.esp_data is None
                else bool(self.esp_data.get("poseMode", False))
            ),
            "avoidance_side": self.avoidance_side,
            "side_obstacle_direction": self.side_obstacle_direction,
            "longitudinal_detour_direction": self.longitudinal_detour_direction,
            "avoidance_target": self.avoidance_target,
            "avoidance_coordinates_m": self.avoidance_coordinates(),
            "avoidance_lateral_limit_m": self.avoidance_lateral_limit_m,
            "side_avoidance_final_forward_m": (
                self.side_avoidance_final_forward_m
            ),
            "side_avoidance_final_lateral_m": (
                self.side_avoidance_final_lateral_m
            ),
            "avoidance_obstacle_seen": self.avoidance_obstacle_seen,
            "avoidance_pause_direction": self.avoidance_pause_sensor,
            "avoidance_paused_for_s": (
                None
                if self.avoidance_pause_started_s is None
                else max(0.0, now - self.avoidance_pause_started_s)
            ),
            "avoidance_abort_reason": self.avoidance_abort_reason,
            "original_target_resume_pending": (
                self.original_target_resume_pending
            ),
            "static_replan_count": self.static_replan_count,
            "rejoin_nominal_after_avoidance": (
                self.rejoin_nominal_after_avoidance
            ),
            "forbidden_detour_directions": sorted(
                self.forbidden_detour_directions
            ),
            "interrupted_obstacle_direction": (
                self.avoidance_pause_obstacle_direction
            ),
            "nominal_path": self.nominal_path_summary(),
            "front_edge_detector": self.edge_detector_summary(
                self.front_edge_detector
            ),
            "rear_edge_detector": self.edge_detector_summary(
                self.rear_edge_detector
            ),
            "strafe_measurement": self.strafe_measurement,
            "measurement_mode": self.avoidance_measurement_mode,
            "measurement_checkpoint": self.measurement_checkpoint,
            "measurement_checkpoints": self.measurement_checkpoints,
        }
        if self.blocked_since is not None:
            payload["blocked_for_s"] = max(0.0, now - self.blocked_since)
        if extra:
            if "reason" in extra:
                self.status_reason = str(extra["reason"])
                self.status_reason_state = self.state
            payload.update(extra)

        msg = String()
        msg.data = json.dumps(payload)
        self.state_pub.publish(msg)

    def on_scan(self, msg):
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning("Ignoring malformed /obstacle/scan JSON.")
            return

        distances = payload.get("distances_cm", {})
        self.distances = {key: finite_distance(value) for key, value in distances.items()}

    @staticmethod
    def new_edge_detector():
        return {
            "armed": False,
            "candidate_count": 0,
            "detected": False,
            "near_cm": None,
            "far_cm": None,
            "previous_cm": None,
            "detected_s": None,
            "history_cm": deque(maxlen=6),
        }

    def reset_edge_detector(self, detector, initial_value=None):
        detector["armed"] = False
        detector["candidate_count"] = 0
        detector["detected"] = False
        detector["near_cm"] = None
        detector["far_cm"] = None
        detector["previous_cm"] = None
        detector["detected_s"] = None
        detector["history_cm"].clear()
        self.update_edge_detector(detector, initial_value)

    def update_edge_detector(self, detector, value):
        if value is None:
            detector["candidate_count"] = 0
            detector["previous_cm"] = None
            return False

        value = float(value)
        previous_cm = detector["previous_cm"]
        detector["history_cm"].append(value)

        if detector["detected"]:
            detector["previous_cm"] = value
            return True

        if value <= self.edge_near_max_cm:
            detector["armed"] = True
            detector["near_cm"] = value
            detector["far_cm"] = None
            detector["candidate_count"] = 0
            detector["previous_cm"] = value
            return False

        if not detector["armed"]:
            detector["previous_cm"] = value
            return False

        if detector["candidate_count"] == 0:
            if (
                previous_cm is not None
                and previous_cm <= self.edge_near_max_cm
                and value >= self.edge_far_min_cm
                and value - previous_cm >= self.edge_jump_min_cm
            ):
                detector["candidate_count"] = 1
                detector["far_cm"] = value
                detector["near_cm"] = previous_cm
            detector["previous_cm"] = value
            return False

        if value >= self.edge_far_min_cm:
            detector["candidate_count"] += 1
            detector["far_cm"] = value
            if detector["candidate_count"] >= self.edge_confirm_samples:
                detector["detected"] = True
                detector["detected_s"] = self.now_s()
                detector["previous_cm"] = value
                return True
        else:
            detector["candidate_count"] = 0
            detector["far_cm"] = None

        detector["previous_cm"] = value
        return False

    @staticmethod
    def edge_detector_summary(detector):
        return {
            "armed": detector["armed"],
            "candidate_count": detector["candidate_count"],
            "detected": detector["detected"],
            "near_cm": detector["near_cm"],
            "far_cm": detector["far_cm"],
            "previous_cm": detector["previous_cm"],
            "history_cm": list(detector["history_cm"]),
        }

    def on_raw_scan(self, msg):
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning("Ignoring malformed /obstacle/raw_scan JSON.")
            return

        raw_distances = payload.get("raw_cm", {})
        self.raw_distances = {
            key: finite_distance(value) for key, value in raw_distances.items()
        }
        self.last_raw_scan_s = self.now_s()

        if self.state == "STATIC_STRAFE_FIND_EDGE":
            self.update_edge_detector(
                self.front_edge_detector,
                self.direction_distance(
                    self.primary_travel_direction,
                    raw=True,
                ),
            )
        elif (
            self.state == "STATIC_FORWARD_FIND_EDGE"
            and self.avoidance_side in ("left", "right")
        ):
            self.update_edge_detector(
                self.rear_edge_detector,
                self.raw_distance(self.inner_obstacle_sensor()),
            )
        elif (
            self.state == "STATIC_SIDE_LONGITUDINAL_FIND_EDGE"
            and self.side_obstacle_direction in ("left", "right")
        ):
            self.update_edge_detector(
                self.front_edge_detector,
                self.raw_distance(self.side_obstacle_direction),
            )
        elif (
            self.state == "STATIC_SIDE_STRAFE_FIND_EDGE"
            and self.longitudinal_detour_direction in ("front", "back")
        ):
            self.update_edge_detector(
                self.rear_edge_detector,
                self.raw_distance(self.side_inner_sensor()),
            )

        self.handle_immediate_safety()

    def on_esp_data(self, msg):
        try:
            esp_data = json.loads(msg.data)
            self.last_esp_data_s = self.now_s()
        except json.JSONDecodeError:
            self.get_logger().warning("Ignoring malformed /esp/data JSON.")
            return

        self.esp_data = esp_data
        self.nominal_path_projection(update_progress=True)

        try:
            gui_stop_count = int(esp_data.get("guiStopCount", 0))
        except (TypeError, ValueError):
            gui_stop_count = 0

        if self.last_gui_stop_count is None:
            self.last_gui_stop_count = gui_stop_count
        elif gui_stop_count != self.last_gui_stop_count:
            self.last_gui_stop_count = gui_stop_count
            self.cancel_supervisor_activity("OPERATOR_STOPPED")
            self.get_logger().warn(
                "GUI STOP detected; autonomous trial cancelled and left stopped."
            )
            self.publish_state({"reason": "gui_emergency_stop"})

    def distance(self, key):
        value = self.distances.get(key)
        if value is None or value < self.dead_zone_cm:
            return None
        return value

    def raw_distance(self, key):
        value = self.raw_distances.get(key)
        if value is None or value < self.dead_zone_cm:
            return None
        return value

    def front_distance(self):
        center = self.distance("front_center")
        if center is not None:
            return center

        candidates = [
            self.distance("front_left"),
            self.distance("front_right"),
        ]
        candidates = [value for value in candidates if value is not None]
        if not candidates:
            return None
        return min(candidates)

    def is_front_blocked(self):
        front = self.front_distance()
        return front is not None and front <= self.front_blocked_cm

    def is_front_clear(self):
        front = self.front_distance()
        return front is not None and front >= self.front_clear_cm

    def sensor_stream_fresh(self):
        if self.last_raw_scan_s is None:
            return self.now_s() - self.started_s <= self.startup_sensor_grace_s
        return self.now_s() - self.last_raw_scan_s <= self.sensor_stale_timeout_s

    def esp_stream_fresh(self):
        age_s = self.esp_data_age_s()
        return age_s is not None and age_s <= self.esp_stale_timeout_s

    def esp_stream_recent_for_transition(self):
        age_s = self.esp_data_age_s()
        return age_s is not None and age_s <= self.esp_transition_fresh_s

    def esp_data_age_s(self):
        if self.last_esp_data_s is None:
            return None
        return self.now_s() - self.last_esp_data_s

    def is_active_avoidance_state(self):
        return self.state.startswith("STATIC_")

    def command_value(self, key):
        if not self.esp_data:
            return 0.0
        try:
            return float(self.esp_data.get("cmd", {}).get(key, 0.0))
        except (TypeError, ValueError):
            return 0.0

    def target_body_error(self):
        pose = self.current_pose()
        if pose is None or not self.esp_data or not self.esp_data.get("poseMode", False):
            return 0.0, 0.0

        try:
            target = self.esp_data["target"]
            dx = float(target["x"]) - pose["x"]
            dy = float(target["y"]) - pose["y"]
        except (KeyError, TypeError, ValueError):
            return 0.0, 0.0

        yaw_rad = math.radians(pose["yaw"])
        forward_error = math.cos(yaw_rad) * dx + math.sin(yaw_rad) * dy
        left_error = -math.sin(yaw_rad) * dx + math.cos(yaw_rad) * dy
        return forward_error, left_error

    def wheel_target_components(self):
        if not self.esp_data:
            return 0.0, 0.0, 0.0

        try:
            wheels = self.esp_data["wheels"]
            fl = float(wheels["FL"]["t"])
            fr = float(wheels["FR"]["t"])
            rl = float(wheels["RL"]["t"])
            rr = float(wheels["RR"]["t"])
        except (KeyError, TypeError, ValueError):
            return 0.0, 0.0, 0.0

        forward = (fl + fr + rl + rr) / 4.0
        left = (-fl + fr + rl - rr) / 4.0
        rotation = (-fl + fr - rl + rr) / 4.0
        return forward, left, rotation

    def intended_directions(self):
        if self.state == "STATIC_NOMINAL_REJOIN":
            return self.waypoint_directions(self.avoidance_target)

        stage_directions = {
            "STATIC_STRAFE_FIND_EDGE": {self.avoidance_side},
            "STATIC_STRAFE_MARGIN": {self.avoidance_side},
            "STATIC_FORWARD_FIND_EDGE": {self.primary_travel_direction},
            "STATIC_FORWARD_MARGIN": {self.primary_travel_direction},
            "STATIC_RETURN_WAIT_CLEAR": set(),
            "STATIC_RETURN_PATH": {
                "right" if self.avoidance_side == "left" else "left"
            },
            "STATIC_SIDE_LONGITUDINAL_FIND_EDGE": {
                self.longitudinal_detour_direction
            },
            "STATIC_SIDE_LONGITUDINAL_MARGIN": {
                self.longitudinal_detour_direction
            },
            "STATIC_SIDE_STRAFE_FIND_EDGE": {
                self.side_obstacle_direction
            },
            "STATIC_SIDE_STRAFE_MARGIN": {
                self.side_obstacle_direction
            },
            "STATIC_SIDE_RETURN_WAIT_CLEAR": set(),
            "STATIC_SIDE_RETURN_PATH": {
                self.opposite_direction(self.longitudinal_detour_direction)
            },
        }
        if self.state in stage_directions:
            return {
                direction
                for direction in stage_directions[self.state]
                if direction is not None
            }

        directions = set()
        epsilon = self.motion_command_epsilon
        vx = self.command_value("vx")
        vy = self.command_value("vy")
        wz = self.command_value("wz")

        if vx > epsilon:
            directions.add("front")
        elif vx < -epsilon:
            directions.add("back")

        if vy > epsilon:
            directions.add("left")
        elif vy < -epsilon:
            directions.add("right")

        if not directions and self.esp_data and self.esp_data.get("poseMode", False):
            forward_error, left_error = self.target_body_error()
            if forward_error > self.pose_tolerance_m:
                directions.add("front")
            elif forward_error < -self.pose_tolerance_m:
                directions.add("back")
            if left_error > self.pose_tolerance_m:
                directions.add("left")
            elif left_error < -self.pose_tolerance_m:
                directions.add("right")

        wheel_forward, wheel_left, wheel_rotation = self.wheel_target_components()
        wheel_epsilon = self.wheel_target_epsilon
        if not directions:
            if wheel_forward > wheel_epsilon:
                directions.add("front")
            elif wheel_forward < -wheel_epsilon:
                directions.add("back")

            if wheel_left > wheel_epsilon:
                directions.add("left")
            elif wheel_left < -wheel_epsilon:
                directions.add("right")

        translating = abs(vx) > epsilon or abs(vy) > epsilon
        wheel_translating = (
            abs(wheel_forward) > wheel_epsilon
            or abs(wheel_left) > wheel_epsilon
        )
        if (
            not translating
            and abs(wz) > self.rotation_command_epsilon
        ):
            directions.update(("front", "back", "left", "right"))
        elif (
            not wheel_translating
            and abs(wheel_rotation) > wheel_epsilon
        ):
            directions.update(("front", "back", "left", "right"))

        return directions

    def waypoint_directions(self, waypoint):
        pose = self.current_pose()
        if pose is None or waypoint is None:
            return set()

        dx = waypoint["x"] - pose["x"]
        dy = waypoint["y"] - pose["y"]
        yaw_rad = math.radians(pose["yaw"])
        forward_error = math.cos(yaw_rad) * dx + math.sin(yaw_rad) * dy
        left_error = -math.sin(yaw_rad) * dx + math.cos(yaw_rad) * dy

        directions = set()
        if forward_error > self.pose_tolerance_m:
            directions.add("front")
        elif forward_error < -self.pose_tolerance_m:
            directions.add("back")
        if left_error > self.pose_tolerance_m:
            directions.add("left")
        elif left_error < -self.pose_tolerance_m:
            directions.add("right")
        return directions

    def enter_front_wait(self, reason):
        first_stop = self.state != "WAITING_DYNAMIC"
        if self.state == "CLEAR":
            self.remember_current_target()
            self.blocked_since = self.now_s()
        self.front_clear_since = None
        self.state = "WAITING_DYNAMIC"
        self.publish_stop(reason, force=first_stop)

    def enter_safety_stop(self, sensor, reason):
        first_stop = (
            self.state != "SAFETY_STOPPED"
            or self.safety_hazard_sensor != sensor
        )
        if self.state == "CLEAR":
            self.remember_current_target()
            self.blocked_since = self.now_s()
        self.safety_hazard_sensor = sensor
        self.safety_release_since = None
        self.state = "SAFETY_STOPPED"
        self.publish_stop(reason, force=first_stop)

    def pause_avoidance(self, sensor, reason):
        if self.state != "AVOIDANCE_PAUSED":
            interrupted_state = self.state
            self.avoidance_pause_state = self.state
            self.avoidance_pause_sensor = sensor
            self.avoidance_pause_started_s = self.now_s()
            self.avoidance_pause_obstacle_direction = (
                self.active_avoidance_obstacle_direction(interrupted_state)
            )
            self.safety_release_since = None
            self.state = "AVOIDANCE_PAUSED"
            self.status_reason = reason
            self.status_reason_state = self.state
            self.get_logger().warn(
                f"Temporary obstacle {sensor}; stopping {self.avoidance_pause_state} "
                "and waiting to continue. "
                "Remembered previous obstacle direction="
                f"{self.avoidance_pause_obstacle_direction}."
            )
        self.publish_stop(reason, force=True)

    def handle_immediate_safety(self):
        if self.state in (
            "AVOIDANCE_PAUSED",
            "AVOIDANCE_ABORTED",
            "OPERATOR_STOPPED",
            "RESETTING",
            "RESET_REQUIRED",
            "SENSOR_FAULT",
            "MEASUREMENT_PAUSED",
        ):
            return

        directions = self.intended_directions()
        front = self.raw_distance("front_center")

        if (
            "front" in directions
            and front is not None
            and front <= self.front_blocked_cm
        ):
            if self.state in ("CLEAR", "WAITING_DYNAMIC"):
                self.enter_front_wait(f"raw_front_{front:.1f}_cm")
            elif self.is_active_avoidance_state():
                self.pause_avoidance(
                    "front",
                    f"raw_front_during_avoidance_{front:.1f}_cm",
                )
            else:
                self.publish_stop(f"raw_front_{front:.1f}_cm")
            return

        directional_checks = (
            ("back", "back_center", self.back_blocked_cm),
            ("left", "left", self.side_blocked_cm),
            ("right", "right", self.side_blocked_cm),
        )
        for direction, key, normal_threshold in directional_checks:
            value = self.raw_distance(key)
            if (
                direction in directions
                and value is not None
                and value <= normal_threshold
            ):
                if self.is_active_avoidance_state():
                    self.pause_avoidance(
                        direction,
                        f"raw_{direction}_during_avoidance_{value:.1f}_cm",
                    )
                else:
                    self.enter_safety_stop(
                        direction,
                        f"raw_{direction}_{value:.1f}_cm",
                    )
                return

    def emergency_obstacle(self, keys=None):
        if keys is None:
            keys = ("front_center", "front_left", "front_right", "left", "right")

        for key in keys:
            value = self.distance(key)
            if value is not None and value < self.emergency_stop_cm:
                return key, value
        return None, None

    def choose_direction_by_clearance(self, candidates, context):
        allowed = {
            direction: distance
            for direction, distance in candidates.items()
            if direction not in self.forbidden_detour_directions
            and distance is not None
            and distance > self.avoidance_side_limit_cm
        }
        rejected = sorted(
            direction
            for direction in candidates
            if direction in self.forbidden_detour_directions
        )

        if len(allowed) == 1:
            direction = next(iter(allowed))
            self.get_logger().warn(
                f"{context}: forced safe direction={direction}; "
                f"direction(s) toward previous obstacle rejected={rejected}."
            )
            return direction
        if len(allowed) > 1:
            return max(allowed, key=allowed.get)

        self.get_logger().error(
            f"{context}: no safe direction available; "
            f"readings={candidates}, forbidden={rejected}."
        )
        return None

    def active_avoidance_obstacle_direction(self, state):
        if state in ("STATIC_STRAFE_FIND_EDGE", "STATIC_STRAFE_MARGIN"):
            return self.primary_travel_direction

        if state in ("STATIC_FORWARD_FIND_EDGE", "STATIC_FORWARD_MARGIN"):
            if self.avoidance_side == "left":
                return "right"
            if self.avoidance_side == "right":
                return "left"

        if state == "STATIC_RETURN_PATH":
            return self.opposite_direction(self.primary_travel_direction)

        if state in (
            "STATIC_SIDE_LONGITUDINAL_FIND_EDGE",
            "STATIC_SIDE_LONGITUDINAL_MARGIN",
        ):
            return self.side_obstacle_direction

        if state in (
            "STATIC_SIDE_STRAFE_FIND_EDGE",
            "STATIC_SIDE_STRAFE_MARGIN",
        ):
            return self.opposite_direction(
                self.longitudinal_detour_direction
            )

        if state == "STATIC_SIDE_RETURN_PATH":
            return self.opposite_direction(self.side_obstacle_direction)

        return None

    def choose_avoidance_side(self):
        return self.choose_direction_by_clearance(
            {
                "left": self.distance("left"),
                "right": self.distance("right"),
            },
            "Choosing left/right avoidance",
        )

    def choose_longitudinal_avoidance_direction(self):
        return self.choose_direction_by_clearance(
            {
                "front": self.front_distance(),
                "back": self.distance("back_center"),
            },
            "Choosing front/back avoidance",
        )

    @staticmethod
    def opposite_direction(direction):
        opposites = {
            "front": "back",
            "back": "front",
            "left": "right",
            "right": "left",
        }
        return opposites.get(direction)

    @staticmethod
    def direction_sensor_key(direction):
        keys = {
            "front": "front_center",
            "back": "back_center",
            "left": "left",
            "right": "right",
        }
        return keys.get(direction)

    def direction_distance(self, direction, raw=False):
        if direction == "front" and not raw:
            return self.front_distance()
        key = self.direction_sensor_key(direction)
        if key is None:
            return None
        return self.raw_distance(key) if raw else self.distance(key)

    def direction_clear_threshold(self, direction):
        if direction == "front":
            return self.front_clear_cm
        if direction == "back":
            return self.back_clear_cm
        if direction in ("left", "right"):
            return self.side_motion_clear_cm
        return None

    def current_pose(self):
        if not self.esp_data:
            return None

        pose = self.esp_data.get("pose", {})
        try:
            return {
                "x": float(pose["x"]),
                "y": float(pose["y"]),
                "yaw": float(pose["yaw"]),
            }
        except (KeyError, TypeError, ValueError):
            return None

    def reset_nominal_path(self):
        self.nominal_path_start = None
        self.nominal_path_goal = None
        self.nominal_path_axis = None
        self.nominal_path_length_m = None
        self.nominal_path_max_progress_m = 0.0
        self.static_replan_count = 0
        self.rejoin_nominal_after_avoidance = False
        self.forbidden_detour_directions.clear()

    def initialize_nominal_path(self, pose_command):
        pose = self.current_pose()
        if pose is None:
            self.reset_nominal_path()
            return False

        dx = pose_command["x"] - pose["x"]
        dy = pose_command["y"] - pose["y"]
        length_m = math.hypot(dx, dy)
        if length_m <= self.pose_tolerance_m:
            self.reset_nominal_path()
            return False

        self.nominal_path_start = dict(pose)
        self.nominal_path_goal = {
            "x": pose_command["x"],
            "y": pose_command["y"],
            "yaw": pose_command["yaw"],
        }
        self.nominal_path_axis = (dx / length_m, dy / length_m)
        self.nominal_path_length_m = length_m
        self.nominal_path_max_progress_m = 0.0
        self.static_replan_count = 0
        self.rejoin_nominal_after_avoidance = False
        self.forbidden_detour_directions.clear()
        self.get_logger().warn(
            "Demo navigation path initialized: "
            f"start=({pose['x']:.3f}, {pose['y']:.3f}), "
            f"goal=({pose_command['x']:.3f}, {pose_command['y']:.3f}), "
            f"length={length_m:.3f} m."
        )
        return True

    def nominal_path_projection(self, pose=None, update_progress=False):
        if (
            self.nominal_path_start is None
            or self.nominal_path_axis is None
            or self.nominal_path_length_m is None
        ):
            return None
        if pose is None:
            pose = self.current_pose()
        if pose is None:
            return None

        dx = pose["x"] - self.nominal_path_start["x"]
        dy = pose["y"] - self.nominal_path_start["y"]
        measured_progress_m = (
            dx * self.nominal_path_axis[0]
            + dy * self.nominal_path_axis[1]
        )
        measured_progress_m = min(
            self.nominal_path_length_m,
            max(0.0, measured_progress_m),
        )
        if update_progress:
            self.nominal_path_max_progress_m = max(
                self.nominal_path_max_progress_m,
                measured_progress_m,
            )
        progress_m = max(
            self.nominal_path_max_progress_m,
            measured_progress_m,
        )

        path_x = (
            self.nominal_path_start["x"]
            + progress_m * self.nominal_path_axis[0]
        )
        path_y = (
            self.nominal_path_start["y"]
            + progress_m * self.nominal_path_axis[1]
        )
        offset_m = math.hypot(pose["x"] - path_x, pose["y"] - path_y)
        return {
            "measured_progress_m": measured_progress_m,
            "progress_m": progress_m,
            "path_x": path_x,
            "path_y": path_y,
            "offset_m": offset_m,
        }

    def nominal_path_summary(self):
        projection = self.nominal_path_projection()
        return {
            "start": self.nominal_path_start,
            "goal": self.nominal_path_goal,
            "length_m": self.nominal_path_length_m,
            "maximum_progress_m": self.nominal_path_max_progress_m,
            "projection": projection,
        }

    def remember_current_target(self):
        if not self.esp_data:
            self.saved_target = None
            self.saved_pose_mode = False
            return

        self.saved_pose_mode = bool(self.esp_data.get("poseMode", False))
        target = self.esp_data.get("target", {})
        try:
            self.saved_target = {
                "x": float(target["x"]),
                "y": float(target["y"]),
                "yaw": float(target["yaw"]),
            }
        except (KeyError, TypeError, ValueError):
            self.saved_target = None

    def esp_has_target(self, target):
        if target is None or not self.esp_data:
            return False

        esp_target = self.esp_data.get("target", {})
        try:
            position_error = math.hypot(
                float(esp_target["x"]) - target["x"],
                float(esp_target["y"]) - target["y"],
            )
            yaw_error = abs(
                self.wrap_deg(
                    float(esp_target["yaw"]) - target["yaw"]
                )
            )
        except (KeyError, TypeError, ValueError):
            return False

        return position_error <= 0.01 and yaw_error <= 1.0

    def pose_reached(self, waypoint):
        pose = self.current_pose()
        if pose is None:
            return False

        dx = waypoint["x"] - pose["x"]
        dy = waypoint["y"] - pose["y"]
        position_error = math.hypot(dx, dy)
        yaw_error = abs(self.wrap_deg(waypoint["yaw"] - pose["yaw"]))

        return position_error < self.pose_tolerance_m and yaw_error < self.yaw_tolerance_deg

    @staticmethod
    def wrap_deg(angle):
        while angle > 180.0:
            angle -= 360.0
        while angle < -180.0:
            angle += 360.0
        return angle

    @staticmethod
    def pose_distance(first, second):
        return math.hypot(first["x"] - second["x"], first["y"] - second["y"])

    def avoidance_coordinates(self, pose=None):
        if (
            self.avoidance_origin is None
            or self.avoidance_forward_axis is None
            or self.avoidance_left_axis is None
        ):
            return None

        if pose is None:
            pose = self.current_pose()
        if pose is None:
            return None

        dx = pose["x"] - self.avoidance_origin["x"]
        dy = pose["y"] - self.avoidance_origin["y"]
        forward_m = (
            dx * self.avoidance_forward_axis[0]
            + dy * self.avoidance_forward_axis[1]
        )
        lateral_m = (
            dx * self.avoidance_left_axis[0]
            + dy * self.avoidance_left_axis[1]
        )
        return forward_m, lateral_m

    def make_avoidance_target(self, forward_m, lateral_m, segment):
        return {
            "type": "pose",
            "x": (
                self.avoidance_origin["x"]
                + forward_m * self.avoidance_forward_axis[0]
                + lateral_m * self.avoidance_left_axis[0]
            ),
            "y": (
                self.avoidance_origin["y"]
                + forward_m * self.avoidance_forward_axis[1]
                + lateral_m * self.avoidance_left_axis[1]
            ),
            "yaw": self.avoidance_origin["yaw"],
            "segment": segment,
        }

    def publish_pose_target(self, target):
        self.publish_command(
            {
                "type": "pose",
                "x": target["x"],
                "y": target["y"],
                "yaw": target["yaw"],
                "segment": target["segment"],
            }
        )

    def send_avoidance_target(self, target, reason):
        self.last_avoidance_command_s = self.now_s()
        self.get_logger().warn(
            f"Sending avoidance pose ({reason}): "
            f"x={target['x']:.3f}, y={target['y']:.3f}, "
            f"yaw={target['yaw']:.1f}, segment={target['segment']}"
        )
        self.publish_pose_target(target)

    def esp_has_avoidance_target(self):
        return (
            bool(self.esp_data and self.esp_data.get("poseMode", False))
            and self.esp_has_target(self.avoidance_target)
        )

    def ensure_avoidance_target_active(self):
        if self.avoidance_target is None:
            return False
        if self.pose_reached(self.avoidance_target):
            return True
        if self.esp_has_avoidance_target():
            return True

        now = self.now_s()
        if (
            self.last_avoidance_command_s is None
            or now - self.last_avoidance_command_s
            >= self.avoidance_command_retry_s
        ):
            self.send_avoidance_target(
                self.avoidance_target,
                "retry_until_esp_confirms",
            )

        self.avoidance_stage_started_s = now
        self.avoidance_last_progress_s = now
        self.avoidance_last_progress_pose = self.current_pose()
        return False

    def start_avoidance_stage(self, state, target):
        pose = self.current_pose()
        if pose is None:
            self.abort_avoidance("missing_esp_pose")
            return False

        self.state = state
        self.avoidance_target = target
        self.avoidance_stage_started_s = self.now_s()
        self.avoidance_last_progress_s = self.now_s()
        self.avoidance_last_progress_pose = pose
        self.avoidance_condition_since = None
        self.get_logger().warn(
            f"Avoidance command -> {state}, segment={target['segment']}, "
            f"x={target['x']:.3f}, y={target['y']:.3f}, "
            f"yaw={target['yaw']:.1f}"
        )
        self.send_avoidance_target(target, "stage_start")
        return True

    def reset_avoidance(self):
        self.primary_travel_direction = "front"
        self.avoidance_side = None
        self.side_obstacle_direction = None
        self.longitudinal_detour_direction = None
        self.side_avoidance_final_forward_m = None
        self.side_avoidance_final_lateral_m = None
        self.avoidance_origin = None
        self.avoidance_forward_axis = None
        self.avoidance_left_axis = None
        self.avoidance_lateral_limit_m = None
        self.avoidance_final_lateral_m = None
        self.avoidance_target = None
        self.avoidance_stage_started_s = None
        self.avoidance_last_progress_s = None
        self.avoidance_last_progress_pose = None
        self.avoidance_condition_since = None
        self.avoidance_obstacle_seen = False
        self.avoidance_pause_state = None
        self.avoidance_pause_sensor = None
        self.avoidance_pause_started_s = None
        self.avoidance_pause_obstacle_direction = None
        self.last_avoidance_command_s = None
        self.reset_edge_detector(self.front_edge_detector)
        self.reset_edge_detector(self.rear_edge_detector)
        self.strafe_measurement = None
        self.measurement_checkpoint = None
        self.measurement_continue_action = None
        self.measurement_checkpoints = []
        self.measurement_settled_recorded = False

    def measurement_continue_hazard(self, action):
        direction = None
        if action in ("start_lateral_edge_search", "start_lateral_margin"):
            direction = self.avoidance_side
        elif action in (
            "start_forward_search",
            "resume_forward_search",
            "start_forward_margin",
        ):
            direction = "front"

        checks = {
            "front": ("front_center", self.front_blocked_cm),
            "left": ("left", self.side_blocked_cm),
            "right": ("right", self.side_blocked_cm),
        }
        key, threshold = checks.get(direction, (None, None))
        value = self.raw_distance(key) if key else None
        if value is not None and threshold is not None and value <= threshold:
            return f"{direction}_blocked_{value:.1f}_cm"
        return None

    def pause_for_measurement(self, checkpoint, continue_action):
        if not self.avoidance_measurement_mode:
            return False

        pose = self.current_pose()
        coordinates = self.avoidance_coordinates(pose)
        inner_sensor = (
            self.inner_obstacle_sensor()
            if self.avoidance_side in ("left", "right")
            else None
        )
        snapshot = {
            "checkpoint": checkpoint,
            "pose": pose,
            "forward_m": None if coordinates is None else coordinates[0],
            "lateral_m": None if coordinates is None else coordinates[1],
            "front_filtered_cm": self.front_distance(),
            "front_raw_cm": self.raw_distance("front_center"),
            "left_cm": self.distance("left"),
            "right_cm": self.distance("right"),
            "inner_sensor": inner_sensor,
            "inner_sensor_cm": (
                None if inner_sensor is None else self.distance(inner_sensor)
            ),
        }
        self.measurement_checkpoints.append(snapshot)
        self.measurement_checkpoint = checkpoint
        self.measurement_continue_action = continue_action
        self.measurement_settled_recorded = False
        self.state = "MEASUREMENT_PAUSED"
        self.avoidance_condition_since = None
        self.publish_stop(f"measurement_checkpoint_{checkpoint}", force=True)

        forward_text = (
            "unknown"
            if snapshot["forward_m"] is None
            else f"{snapshot['forward_m']:.3f} m"
        )
        lateral_text = (
            "unknown"
            if snapshot["lateral_m"] is None
            else f"{snapshot['lateral_m']:.3f} m"
        )
        self.get_logger().warn(
            f"MEASUREMENT CHECKPOINT - {checkpoint} | "
            f"forward={forward_text}, lateral={lateral_text}, "
            f"front={snapshot['front_filtered_cm']} cm, "
            f"left={snapshot['left_cm']} cm, right={snapshot['right_cm']} cm. "
            "Robot is stopped. Measure now, then send continue_measurement."
        )
        return True

    def record_measurement_settled(self):
        if self.measurement_settled_recorded or not self.measurement_checkpoints:
            return

        settled_pose = self.current_pose()
        settled_coordinates = self.avoidance_coordinates(settled_pose)
        snapshot = self.measurement_checkpoints[-1]
        snapshot["settled_pose"] = settled_pose
        snapshot["settled_forward_m"] = (
            None if settled_coordinates is None else settled_coordinates[0]
        )
        snapshot["settled_lateral_m"] = (
            None if settled_coordinates is None else settled_coordinates[1]
        )
        event_pose = snapshot.get("pose")
        snapshot["movement_after_stop_command_m"] = (
            None
            if event_pose is None or settled_pose is None
            else self.pose_distance(event_pose, settled_pose)
        )
        self.measurement_settled_recorded = True
        self.get_logger().warn(
            f"MEASUREMENT SETTLED - {self.measurement_checkpoint} | "
            f"forward={snapshot['settled_forward_m']} m, "
            f"lateral={snapshot['settled_lateral_m']} m, "
            "movement_after_stop_command="
            f"{snapshot['movement_after_stop_command_m']} m"
        )

    def continue_measurement_test(self):
        if not self.avoidance_measurement_mode:
            self.get_logger().error(
                "Continue Measurement rejected because measurement mode is disabled."
            )
            self.publish_state({"reason": "measurement_mode_disabled"})
            return
        if self.state != "MEASUREMENT_PAUSED":
            self.get_logger().error(
                f"Continue Measurement rejected while state is {self.state}."
            )
            self.publish_state({"reason": "not_at_measurement_checkpoint"})
            return
        if not self.sensor_stream_fresh() or not self.esp_stream_fresh():
            self.publish_stop("measurement_continue_rejected_stale_data", force=True)
            self.get_logger().error(
                "Continue Measurement rejected because sensor or ESP data is stale."
            )
            self.publish_state({"reason": "measurement_continue_data_stale"})
            return

        action = self.measurement_continue_action
        hazard = self.measurement_continue_hazard(action)
        if hazard is not None:
            self.publish_stop(
                f"measurement_continue_rejected_{hazard}",
                force=True,
            )
            self.get_logger().error(
                f"Continue Measurement rejected because {hazard}."
            )
            self.publish_state(
                {"reason": f"measurement_continue_rejected_{hazard}"}
            )
            return

        checkpoint = self.measurement_checkpoint
        self.record_measurement_settled()

        self.measurement_checkpoint = None
        self.measurement_continue_action = None
        self.measurement_settled_recorded = False
        self.get_logger().warn(
            f"Continuing measurement test after {checkpoint}: {action}."
        )

        if action == "start_lateral_edge_search":
            self.start_lateral_edge_search_stage()
        elif action == "start_lateral_margin":
            self.start_lateral_margin_stage()
        elif action == "start_forward_search":
            self.start_forward_search_stage()
        elif action == "resume_forward_search":
            if self.avoidance_target is None:
                self.abort_avoidance("missing_forward_target_after_measurement")
                return
            self.state = "STATIC_FORWARD_FIND_EDGE"
            self.avoidance_stage_started_s = self.now_s()
            self.avoidance_last_progress_s = self.now_s()
            self.avoidance_last_progress_pose = self.current_pose()
            self.avoidance_condition_since = None
            self.send_avoidance_target(
                self.avoidance_target,
                "measurement_continue",
            )
        elif action == "start_forward_margin":
            self.start_forward_margin_stage()
        elif action == "begin_return_wait":
            self.begin_return_wait()
        else:
            self.abort_avoidance("unknown_measurement_continue_action")
            return

        self.publish_state(
            {"reason": f"measurement_continued_after_{checkpoint}"}
        )

    def abort_avoidance(self, reason):
        self.avoidance_abort_reason = reason
        self.status_reason = f"avoidance_stopped_{reason}"
        self.status_reason_state = "AVOIDANCE_ABORTED"
        self.get_logger().error(
            f"AVOIDANCE STOPPED | reason={reason}, "
            f"state={self.state}, target={self.avoidance_target}, "
            f"front={self.front_distance()}, "
            f"back={self.distance('back_center')}, "
            f"left={self.distance('left')}, right={self.distance('right')}"
        )
        self.publish_stop(f"avoidance_aborted_{reason}", force=True)
        self.state = "AVOIDANCE_ABORTED"

    def start_static_avoidance(self, side, travel_direction="front"):
        pose = self.current_pose()
        side_distance_cm = self.distance(side)
        if not self.saved_pose_mode or self.saved_target is None:
            self.abort_avoidance("no_saved_pose_target")
            return
        if (
            pose is None
            or travel_direction not in ("front", "back")
            or side in self.forbidden_detour_directions
            or side_distance_cm is None
            or not self.esp_stream_recent_for_transition()
        ):
            reason = (
                "chosen_side_points_toward_previous_obstacle"
                if side in self.forbidden_detour_directions
                else "missing_pose_or_side_data"
            )
            self.abort_avoidance(reason)
            return

        if side_distance_cm <= self.avoidance_side_limit_cm:
            self.abort_avoidance("chosen_side_already_at_stop_limit")
            return

        yaw_rad = math.radians(pose["yaw"])
        self.avoidance_origin = dict(pose)
        self.avoidance_forward_axis = (math.cos(yaw_rad), math.sin(yaw_rad))
        self.avoidance_left_axis = (-math.sin(yaw_rad), math.cos(yaw_rad))
        self.primary_travel_direction = travel_direction
        self.avoidance_side = side
        self.avoidance_lateral_limit_m = self.maximum_lateral_search_m
        self.avoidance_abort_reason = None
        self.avoidance_obstacle_seen = False
        self.measurement_checkpoint = None
        self.measurement_continue_action = None
        self.measurement_checkpoints = []
        self.measurement_settled_recorded = False
        self.strafe_measurement = {
            "side": side,
            "origin_pose": dict(pose),
            "edge": None,
            "margin": None,
        }

        if self.pause_for_measurement(
            "START_REFERENCE_BEFORE_SIDEWAYS_MOTION",
            "start_lateral_edge_search",
        ):
            return

        self.start_lateral_edge_search_stage()

    def start_lateral_edge_search_stage(self):
        self.reset_edge_detector(
            self.front_edge_detector,
            self.direction_distance(
                self.primary_travel_direction,
                raw=True,
            ),
        )
        side_sign = 1.0 if self.avoidance_side == "left" else -1.0
        target = self.make_avoidance_target(
            0.0,
            side_sign * self.avoidance_lateral_limit_m,
            f"strafe_find_front_edge_{self.avoidance_side}",
        )
        self.start_avoidance_stage("STATIC_STRAFE_FIND_EDGE", target)

    def condition_confirmed(self, condition, confirm_s):
        if not condition:
            self.avoidance_condition_since = None
            return False
        if self.avoidance_condition_since is None:
            self.avoidance_condition_since = self.now_s()
            return False
        return self.now_s() - self.avoidance_condition_since >= confirm_s

    def check_avoidance_motion_health(self):
        if self.avoidance_target is None:
            self.abort_avoidance("missing_stage_target")
            return False
        if not self.esp_stream_fresh():
            self.abort_avoidance("esp_data_stale")
            return False
        if not self.esp_stream_recent_for_transition():
            return False
        if not self.ensure_avoidance_target_active():
            return False

        pose = self.current_pose()
        if pose is None:
            self.abort_avoidance("missing_esp_pose")
            return False

        now = self.now_s()
        if now - self.avoidance_stage_started_s > self.avoidance_stage_timeout_s:
            self.abort_avoidance("stage_timeout")
            return False

        if (
            self.avoidance_last_progress_pose is None
            or self.pose_distance(pose, self.avoidance_last_progress_pose)
            >= self.avoidance_progress_m
        ):
            self.avoidance_last_progress_pose = pose
            self.avoidance_last_progress_s = now
        elif (
            not self.pose_reached(self.avoidance_target)
            and now - self.avoidance_last_progress_s
            > self.avoidance_stall_timeout_s
        ):
            self.abort_avoidance("odometry_no_progress")
            return False

        return True

    def start_lateral_margin_stage(self):
        coordinates = self.avoidance_coordinates()
        if coordinates is None:
            self.abort_avoidance("missing_pose_at_front_edge")
            return

        forward_m, lateral_m = coordinates
        side_sign = 1.0 if self.avoidance_side == "left" else -1.0
        final_lateral_m = lateral_m + side_sign * self.lateral_body_margin_m
        if abs(final_lateral_m) > self.avoidance_lateral_limit_m:
            self.abort_avoidance("front_edge_too_late_for_lateral_margin")
            return

        edge_pose = self.current_pose()
        filtered_front_cm = self.front_distance()
        raw_front_cm = self.raw_distance("front_center")
        moving_side_cm = self.distance(self.avoidance_side)
        edge_measurement = {
            "forward_m": forward_m,
            "lateral_m": lateral_m,
            "lateral_abs_m": abs(lateral_m),
            "front_cm": filtered_front_cm,
            "raw_front_cm": raw_front_cm,
            "moving_side_cm": moving_side_cm,
            "detector": self.edge_detector_summary(self.front_edge_detector),
            "pose": edge_pose,
        }
        if self.strafe_measurement is not None:
            self.strafe_measurement["edge"] = edge_measurement

        self.get_logger().warn(
            "STRAFE MEASURE 1/2 - FRONT EDGE DETECTED | "
            f"side={self.avoidance_side}, "
            f"lateral_from_original={abs(lateral_m):.3f} m, "
            f"pose_x={edge_pose['x']:.3f} m, pose_y={edge_pose['y']:.3f} m, "
            f"front_filtered={filtered_front_cm} cm, "
            f"front_raw={raw_front_cm} cm, "
            f"{self.avoidance_side}_clearance={moving_side_cm} cm, "
            f"edge_near={self.front_edge_detector['near_cm']} cm, "
            f"edge_far={self.front_edge_detector['far_cm']} cm, "
            f"next_commanded_margin={self.lateral_body_margin_m:.3f} m"
        )

        self.avoidance_final_lateral_m = final_lateral_m
        target = self.make_avoidance_target(
            forward_m,
            final_lateral_m,
            f"strafe_body_margin_{self.avoidance_side}",
        )
        self.start_avoidance_stage("STATIC_STRAFE_MARGIN", target)

    def start_forward_search_stage(self):
        coordinates = self.avoidance_coordinates()
        if coordinates is None:
            self.abort_avoidance("missing_pose_before_forward_pass")
            return

        forward_m, lateral_m = coordinates
        edge_lateral_m = None
        if (
            self.strafe_measurement is not None
            and self.strafe_measurement.get("edge") is not None
        ):
            edge_lateral_m = self.strafe_measurement["edge"]["lateral_m"]

        actual_margin_m = (
            None
            if edge_lateral_m is None
            else abs(lateral_m - edge_lateral_m)
        )
        inner_sensor = self.inner_obstacle_sensor()
        inner_gap_cm = self.distance(inner_sensor)
        margin_measurement = {
            "forward_m": forward_m,
            "lateral_m": lateral_m,
            "lateral_abs_m": abs(lateral_m),
            "commanded_margin_m": self.lateral_body_margin_m,
            "encoder_margin_m": actual_margin_m,
            "encoder_margin_error_m": (
                None
                if actual_margin_m is None
                else actual_margin_m - self.lateral_body_margin_m
            ),
            "inner_sensor": inner_sensor,
            "inner_gap_cm": inner_gap_cm,
            "front_cm": self.front_distance(),
            "pose": self.current_pose(),
        }
        if self.strafe_measurement is not None:
            self.strafe_measurement["margin"] = margin_measurement

        actual_margin_text = (
            "unknown"
            if actual_margin_m is None
            else f"{actual_margin_m:.3f} m"
        )
        margin_error_text = (
            "unknown"
            if actual_margin_m is None
            else f"{actual_margin_m - self.lateral_body_margin_m:+.3f} m"
        )
        margin_pose = margin_measurement["pose"]
        self.get_logger().warn(
            "STRAFE MEASURE 2/2 - SIDEWAYS MOTION COMPLETE | "
            f"side={self.avoidance_side}, "
            f"total_lateral_from_original={abs(lateral_m):.3f} m, "
            f"pose_x={margin_pose['x']:.3f} m, "
            f"pose_y={margin_pose['y']:.3f} m, "
            f"commanded_after_edge={self.lateral_body_margin_m:.3f} m, "
            f"encoder_after_edge={actual_margin_text}, "
            f"encoder_error={margin_error_text}, "
            f"{inner_sensor}_gap={inner_gap_cm} cm"
        )

        self.avoidance_obstacle_seen = False
        self.reset_edge_detector(
            self.rear_edge_detector,
            self.raw_distance(self.inner_obstacle_sensor()),
        )
        target = self.make_avoidance_target(
            forward_m
            + (
                1.0
                if self.primary_travel_direction == "front"
                else -1.0
            )
            * self.maximum_forward_search_m,
            self.avoidance_final_lateral_m,
            f"{self.primary_travel_direction}_find_rear_edge",
        )
        self.start_avoidance_stage("STATIC_FORWARD_FIND_EDGE", target)

    def start_forward_margin_stage(self):
        coordinates = self.avoidance_coordinates()
        if coordinates is None:
            self.abort_avoidance("missing_pose_at_rear_edge")
            return

        forward_m, _ = coordinates
        travel_sign = (
            1.0 if self.primary_travel_direction == "front" else -1.0
        )
        target = self.make_avoidance_target(
            forward_m + travel_sign * self.forward_body_margin_m,
            self.avoidance_final_lateral_m,
            f"{self.primary_travel_direction}_body_margin",
        )
        self.start_avoidance_stage("STATIC_FORWARD_MARGIN", target)

    def begin_return_wait(self):
        self.state = "STATIC_RETURN_WAIT_CLEAR"
        self.avoidance_target = None
        self.avoidance_stage_started_s = self.now_s()
        self.avoidance_condition_since = None

    def start_return_stage(self):
        coordinates = self.avoidance_coordinates()
        if coordinates is None:
            self.abort_avoidance("missing_pose_before_path_return")
            return

        forward_m, _ = coordinates
        target = self.make_avoidance_target(
            forward_m,
            0.0,
            "return_to_original_path",
        )
        self.start_avoidance_stage("STATIC_RETURN_PATH", target)

    def start_side_static_avoidance(
        self,
        obstacle_direction,
        detour_direction,
    ):
        pose = self.current_pose()
        detour_distance_cm = self.direction_distance(detour_direction)
        if not self.saved_pose_mode or self.saved_target is None:
            self.abort_avoidance("no_saved_pose_target")
            return
        if (
            pose is None
            or obstacle_direction not in ("left", "right")
            or detour_direction not in ("front", "back")
            or detour_direction in self.forbidden_detour_directions
            or detour_distance_cm is None
            or not self.esp_stream_recent_for_transition()
        ):
            reason = (
                "chosen_detour_points_toward_previous_obstacle"
                if detour_direction in self.forbidden_detour_directions
                else "missing_pose_or_detour_data"
            )
            self.abort_avoidance(reason)
            return
        if detour_distance_cm <= self.avoidance_side_limit_cm:
            self.abort_avoidance(
                f"chosen_{detour_direction}_direction_at_stop_limit"
            )
            return

        yaw_rad = math.radians(pose["yaw"])
        self.avoidance_origin = dict(pose)
        self.avoidance_forward_axis = (math.cos(yaw_rad), math.sin(yaw_rad))
        self.avoidance_left_axis = (-math.sin(yaw_rad), math.cos(yaw_rad))
        self.avoidance_side = None
        self.side_obstacle_direction = obstacle_direction
        self.longitudinal_detour_direction = detour_direction
        self.side_avoidance_final_forward_m = None
        self.side_avoidance_final_lateral_m = None
        self.avoidance_abort_reason = None
        self.avoidance_obstacle_seen = False
        self.measurement_checkpoint = None
        self.measurement_continue_action = None
        self.measurement_checkpoints = []
        self.measurement_settled_recorded = False
        self.strafe_measurement = {
            "mode": "side_obstacle",
            "obstacle_direction": obstacle_direction,
            "detour_direction": detour_direction,
            "origin_pose": dict(pose),
        }

        self.get_logger().warn(
            "Starting mirrored side-obstacle avoidance: "
            f"obstacle={obstacle_direction}, "
            f"detour={detour_direction}, "
            f"front={self.front_distance()} cm, "
            f"back={self.distance('back_center')} cm."
        )
        self.start_side_longitudinal_edge_search_stage()

    def start_side_longitudinal_edge_search_stage(self):
        self.reset_edge_detector(
            self.front_edge_detector,
            self.raw_distance(self.side_obstacle_direction),
        )
        detour_sign = (
            1.0 if self.longitudinal_detour_direction == "front" else -1.0
        )
        target = self.make_avoidance_target(
            detour_sign * self.maximum_forward_search_m,
            0.0,
            (
                f"{self.longitudinal_detour_direction}_find_"
                f"{self.side_obstacle_direction}_obstacle_edge"
            ),
        )
        self.start_avoidance_stage(
            "STATIC_SIDE_LONGITUDINAL_FIND_EDGE",
            target,
        )

    def start_side_longitudinal_margin_stage(self):
        coordinates = self.avoidance_coordinates()
        if coordinates is None:
            self.abort_avoidance("missing_pose_at_side_obstacle_first_edge")
            return

        forward_m, lateral_m = coordinates
        detour_sign = (
            1.0 if self.longitudinal_detour_direction == "front" else -1.0
        )
        final_forward_m = (
            forward_m
            + detour_sign * self.side_avoidance_longitudinal_margin_m
        )
        if abs(final_forward_m) > self.maximum_forward_search_m:
            self.abort_avoidance(
                "side_obstacle_first_edge_too_late_for_longitudinal_margin"
            )
            return

        self.get_logger().warn(
            "SIDE AVOIDANCE EDGE 1/2 - SIDE SENSOR CLEARED | "
            f"obstacle={self.side_obstacle_direction}, "
            f"detour={self.longitudinal_detour_direction}, "
            f"forward_from_original={forward_m:.3f} m, "
            f"edge_near={self.front_edge_detector['near_cm']} cm, "
            f"edge_far={self.front_edge_detector['far_cm']} cm, "
            "next_commanded_margin="
            f"{self.side_avoidance_longitudinal_margin_m:.3f} m"
        )

        self.side_avoidance_final_forward_m = final_forward_m
        target = self.make_avoidance_target(
            final_forward_m,
            lateral_m,
            (
                f"{self.longitudinal_detour_direction}_body_margin_"
                f"for_{self.side_obstacle_direction}_obstacle"
            ),
        )
        self.start_avoidance_stage(
            "STATIC_SIDE_LONGITUDINAL_MARGIN",
            target,
        )

    def start_side_strafe_search_stage(self):
        coordinates = self.avoidance_coordinates()
        if coordinates is None:
            self.abort_avoidance("missing_pose_before_sideways_pass")
            return

        forward_m, lateral_m = coordinates
        self.avoidance_obstacle_seen = False
        self.reset_edge_detector(
            self.rear_edge_detector,
            self.raw_distance(self.side_inner_sensor()),
        )
        strafe_sign = 1.0 if self.side_obstacle_direction == "left" else -1.0
        target = self.make_avoidance_target(
            forward_m,
            lateral_m + strafe_sign * self.maximum_lateral_search_m,
            f"strafe_{self.side_obstacle_direction}_find_far_edge",
        )
        self.start_avoidance_stage(
            "STATIC_SIDE_STRAFE_FIND_EDGE",
            target,
        )

    def start_side_strafe_margin_stage(self):
        coordinates = self.avoidance_coordinates()
        if coordinates is None:
            self.abort_avoidance("missing_pose_at_side_obstacle_far_edge")
            return

        forward_m, lateral_m = coordinates
        strafe_sign = 1.0 if self.side_obstacle_direction == "left" else -1.0
        final_lateral_m = (
            lateral_m
            + strafe_sign * self.side_avoidance_lateral_margin_m
        )

        self.get_logger().warn(
            "SIDE AVOIDANCE EDGE 2/2 - FRONT/BACK SENSOR CLEARED | "
            f"sensor={self.side_inner_sensor()}, "
            f"lateral_from_original={lateral_m:.3f} m, "
            f"edge_near={self.rear_edge_detector['near_cm']} cm, "
            f"edge_far={self.rear_edge_detector['far_cm']} cm, "
            "next_commanded_margin="
            f"{self.side_avoidance_lateral_margin_m:.3f} m"
        )

        self.side_avoidance_final_lateral_m = final_lateral_m
        target = self.make_avoidance_target(
            forward_m,
            final_lateral_m,
            f"sideways_body_margin_{self.side_obstacle_direction}",
        )
        self.start_avoidance_stage(
            "STATIC_SIDE_STRAFE_MARGIN",
            target,
        )

    def begin_side_return_wait(self):
        self.state = "STATIC_SIDE_RETURN_WAIT_CLEAR"
        self.avoidance_target = None
        self.avoidance_stage_started_s = self.now_s()
        self.avoidance_condition_since = None

    def start_side_return_stage(self):
        coordinates = self.avoidance_coordinates()
        if coordinates is None:
            self.abort_avoidance("missing_pose_before_side_path_return")
            return

        _, lateral_m = coordinates
        target = self.make_avoidance_target(
            0.0,
            lateral_m,
            "return_to_original_sideways_path",
        )
        self.start_avoidance_stage("STATIC_SIDE_RETURN_PATH", target)

    def side_inner_sensor(self):
        return (
            "back_center"
            if self.longitudinal_detour_direction == "front"
            else "front_center"
        )

    def side_return_sensor(self):
        return self.side_inner_sensor()

    def inner_obstacle_sensor(self):
        return "right" if self.avoidance_side == "left" else "left"

    def return_direction_sensor(self):
        return self.inner_obstacle_sensor()

    def avoidance_pause_release(self):
        thresholds = {
            "front": ("front_center", self.front_clear_cm),
            "back": ("back_center", self.back_clear_cm),
            "left": ("left", self.side_motion_clear_cm),
            "right": ("right", self.side_motion_clear_cm),
        }
        key, threshold = thresholds.get(
            self.avoidance_pause_sensor,
            (None, None),
        )
        value = self.raw_distance(key) if key else None
        return value is not None and threshold is not None and value >= threshold

    def resume_original_target(self):
        if self.resume_saved_target and self.saved_pose_mode and self.saved_target:
            self.original_target_resume_pending = True
            self.last_original_target_resume_command_s = self.now_s()
            self.publish_command(
                {
                    "type": "pose",
                    "x": self.saved_target["x"],
                    "y": self.saved_target["y"],
                    "yaw": self.saved_target["yaw"],
                    "reason": "resume_saved_target",
                }
            )
            self.get_logger().warn(
                "Restoring original destination and waiting for ESP "
                "confirmation: "
                f"x={self.saved_target['x']:.3f}, "
                f"y={self.saved_target['y']:.3f}, "
                f"yaw={self.saved_target['yaw']:.1f}."
            )
            return True
        return False

    def ensure_original_target_resumed(self):
        if not self.original_target_resume_pending:
            return
        if self.saved_target is None:
            self.original_target_resume_pending = False
            self.last_original_target_resume_command_s = None
            return

        if (
            self.esp_has_target(self.saved_target)
            and (
                bool(self.esp_data.get("poseMode", False))
                or self.pose_reached(self.saved_target)
            )
        ):
            self.original_target_resume_pending = False
            self.last_original_target_resume_command_s = None
            self.get_logger().warn(
                "ESP confirmed original destination: "
                f"x={self.saved_target['x']:.3f}, "
                f"y={self.saved_target['y']:.3f}, "
                f"yaw={self.saved_target['yaw']:.1f}."
            )
            return

        now = self.now_s()
        if (
            self.last_original_target_resume_command_s is None
            or now - self.last_original_target_resume_command_s
            >= self.avoidance_command_retry_s
        ):
            self.last_original_target_resume_command_s = now
            self.get_logger().warn(
                "Original destination not yet confirmed by ESP; retrying."
            )
            self.publish_command(
                {
                    "type": "pose",
                    "x": self.saved_target["x"],
                    "y": self.saved_target["y"],
                    "yaw": self.saved_target["yaw"],
                    "reason": "retry_resume_saved_target",
                }
            )

    def start_nominal_path_rejoin(self):
        pose = self.current_pose()
        projection = self.nominal_path_projection(pose)
        if pose is None or projection is None:
            self.abort_avoidance("missing_nominal_path_for_rejoin")
            return

        if projection["offset_m"] <= self.pose_tolerance_m:
            if self.forbidden_detour_directions:
                self.get_logger().warn(
                    "Navigation line recovered; clearing previous-obstacle "
                    "direction locks="
                    f"{sorted(self.forbidden_detour_directions)}."
                )
                self.forbidden_detour_directions.clear()
            self.rejoin_nominal_after_avoidance = False
            self.resume_original_target()
            self.state = "CLEAR"
            self.blocked_since = None
            self.reset_avoidance()
            return

        rejoin_target = {
            "type": "pose",
            "x": projection["path_x"],
            "y": projection["path_y"],
            "yaw": pose["yaw"],
            "segment": "rejoin_closest_forward_nominal_path_point",
        }
        self.reset_avoidance()
        self.rejoin_nominal_after_avoidance = True
        self.get_logger().warn(
            "Rejoining nominal navigation path without losing progress: "
            f"progress={projection['progress_m']:.3f} m, "
            f"offset={projection['offset_m']:.3f} m, "
            f"target=({projection['path_x']:.3f}, "
            f"{projection['path_y']:.3f})."
        )
        self.start_avoidance_stage("STATIC_NOMINAL_REJOIN", rejoin_target)

    def complete_current_avoidance(self):
        if self.rejoin_nominal_after_avoidance:
            self.start_nominal_path_rejoin()
            return

        self.resume_original_target()
        self.state = "CLEAR"
        self.blocked_since = None
        self.reset_avoidance()

    def replan_for_persistent_obstacle(self, direction):
        if direction not in ("front", "back", "left", "right"):
            self.abort_avoidance("invalid_static_replan_direction")
            return
        if self.static_replan_count >= self.max_static_replans:
            self.abort_avoidance("maximum_static_replans_reached")
            return
        if (
            self.nominal_path_axis is None
            or self.nominal_path_goal is None
            or self.saved_target is None
        ):
            self.abort_avoidance("nominal_path_not_available_for_replan")
            return

        previous_obstacle_direction = (
            self.avoidance_pause_obstacle_direction
        )
        if previous_obstacle_direction is not None:
            self.forbidden_detour_directions.add(
                previous_obstacle_direction
            )
            self.get_logger().warn(
                "Locked previous obstacle direction="
                f"{previous_obstacle_direction}; the new avoidance will not "
                "choose a detour back toward that obstacle. "
                "Active direction locks="
                f"{sorted(self.forbidden_detour_directions)}."
            )

        self.static_replan_count += 1
        self.rejoin_nominal_after_avoidance = True
        self.get_logger().warn(
            "Second static obstacle confirmed during avoidance. "
            f"Replanning from current pose for blocked direction={direction}; "
            f"replan={self.static_replan_count}/{self.max_static_replans}."
        )

        self.reset_avoidance()
        self.rejoin_nominal_after_avoidance = True

        if direction in ("front", "back"):
            side = self.choose_avoidance_side()
            if side is None:
                self.abort_avoidance(
                    "no_safe_side_away_from_previous_obstacle"
                )
                return
            self.start_static_avoidance(side, direction)
            return

        detour_direction = self.choose_longitudinal_avoidance_direction()
        if detour_direction is None:
            self.abort_avoidance(
                "no_safe_front_or_back_away_from_previous_obstacle"
            )
            return
        self.start_side_static_avoidance(direction, detour_direction)

    def evaluate(self):
        extra = {}

        if not self.sensor_stream_fresh():
            if self.is_active_avoidance_state() or self.state == "AVOIDANCE_PAUSED":
                self.abort_avoidance("ultrasonic_scan_stale")
                self.finish_evaluation({"reason": "ultrasonic_scan_stale"})
                return
            if self.state != "SENSOR_FAULT":
                self.remember_current_target()
            self.state = "SENSOR_FAULT"
            self.front_clear_since = None
            self.publish_stop("ultrasonic_scan_stale")
            extra["reason"] = "ultrasonic_scan_stale"
            self.finish_evaluation(extra)
            return

        if (
            self.last_esp_data_s is not None
            and not self.esp_stream_fresh()
        ):
            if self.is_active_avoidance_state() or self.state == "AVOIDANCE_PAUSED":
                self.abort_avoidance("esp_data_stale")
                self.finish_evaluation({"reason": "esp_communication_lost"})
                return
            if self.state not in (
                "READY",
                "OPERATOR_STOPPED",
                "RESET_REQUIRED",
                "SENSOR_FAULT",
                "AVOIDANCE_ABORTED",
            ):
                self.cancel_supervisor_activity("RESET_REQUIRED")
                self.publish_stop("esp_communication_lost", force=True)
                self.finish_evaluation({"reason": "esp_communication_lost"})
                return

        if self.state == "SENSOR_FAULT":
            self.state = "RESET_REQUIRED"
            self.blocked_since = None
            self.safety_hazard_sensor = None
            extra["reason"] = "sensor_stream_recovered_reset_required"

        self.ensure_original_target_resumed()

        if self.state == "RESETTING":
            self.publish_stop("resetting_waiting_for_robot_stop")
            stopped = (
                self.esp_data is not None
                and not bool(self.esp_data.get("poseMode", False))
                and abs(self.command_value("vx")) <= self.motion_command_epsilon
                and abs(self.command_value("vy")) <= self.motion_command_epsilon
                and abs(self.command_value("wz")) <= self.rotation_command_epsilon
            )
            if stopped:
                self.state = "READY"
                extra["reason"] = "reset_complete_robot_stopped"

        elif self.state == "CLEAR":
            if "front" in self.intended_directions() and self.is_front_blocked():
                self.enter_front_wait("filtered_front_obstacle")

        elif self.state == "WAITING_DYNAMIC":
            self.publish_stop("waiting_dynamic_front_blocked")
            if self.is_front_clear():
                if self.front_clear_since is None:
                    self.front_clear_since = self.now_s()
                elif self.now_s() - self.front_clear_since >= self.front_clear_confirm_s:
                    self.resume_original_target()
                    self.state = "CLEAR"
                    self.blocked_since = None
                    self.front_clear_since = None
            else:
                self.front_clear_since = None

            if (
                not self.is_front_clear()
                and self.is_front_blocked()
                and self.blocked_since is not None
                and self.now_s() - self.blocked_since >= self.static_wait_s
            ):
                if not self.enable_static_avoidance:
                    self.state = "PERSISTENT_STOPPED"
                    self.publish_stop("persistent_obstacle_avoidance_disabled")
                    extra["reason"] = "static_avoidance_disabled"
                else:
                    side = self.choose_avoidance_side()
                    if side is None:
                        self.publish_stop("static_obstacle_no_valid_side_reading")
                        extra["reason"] = "no_valid_side_reading"
                    else:
                        self.start_static_avoidance(side)

        elif self.state == "PERSISTENT_STOPPED":
            self.publish_stop("persistent_obstacle_avoidance_disabled")
            if self.is_front_clear():
                if self.front_clear_since is None:
                    self.front_clear_since = self.now_s()
                elif self.now_s() - self.front_clear_since >= self.front_clear_confirm_s:
                    self.resume_original_target()
                    self.state = "CLEAR"
                    self.blocked_since = None
                    self.front_clear_since = None
            else:
                self.front_clear_since = None

        elif self.state == "STATIC_STRAFE_FIND_EDGE":
            if self.check_avoidance_motion_health():
                travel_distance = self.direction_distance(
                    self.primary_travel_direction
                )
                travel_clear_threshold = self.direction_clear_threshold(
                    self.primary_travel_direction
                )
                if self.front_edge_detector["detected"]:
                    self.get_logger().warn(
                        "Fast primary-direction edge transition confirmed: "
                        f"sensor={self.primary_travel_direction}, "
                        f"near={self.front_edge_detector['near_cm']} cm, "
                        f"far={self.front_edge_detector['far_cm']} cm, "
                        f"samples={self.front_edge_detector['candidate_count']}."
                    )
                    if not self.pause_for_measurement(
                        "1_OF_5_FRONT_EDGE_FOUND",
                        "start_lateral_margin",
                    ):
                        self.start_lateral_margin_stage()
                elif self.condition_confirmed(
                    (
                        travel_distance is not None
                        and travel_clear_threshold is not None
                        and travel_distance >= travel_clear_threshold
                    ),
                    self.front_clear_confirm_s,
                ):
                    self.get_logger().warn(
                        "Primary-direction edge transition was not sharp enough; "
                        "using the slower filtered-clear fallback."
                    )
                    if not self.pause_for_measurement(
                        "1_OF_5_FRONT_EDGE_FOUND",
                        "start_lateral_margin",
                    ):
                        self.start_lateral_margin_stage()
                elif self.pose_reached(self.avoidance_target):
                    self.abort_avoidance("front_edge_not_found_within_lateral_limit")

        elif self.state == "STATIC_STRAFE_MARGIN":
            if self.check_avoidance_motion_health() and self.pose_reached(
                self.avoidance_target
            ):
                if not self.pause_for_measurement(
                    "2_OF_5_LATERAL_MARGIN_COMPLETE",
                    "start_forward_search",
                ):
                    self.start_forward_search_stage()

        elif self.state == "STATIC_FORWARD_FIND_EDGE":
            if self.check_avoidance_motion_health():
                obstacle_side = self.distance(self.inner_obstacle_sensor())
                raw_obstacle_side = self.raw_distance(
                    self.inner_obstacle_sensor()
                )
                if (
                    not self.avoidance_obstacle_seen
                    and (
                        (
                            raw_obstacle_side is not None
                            and raw_obstacle_side <= self.pass_obstacle_seen_cm
                        )
                        or self.rear_edge_detector["armed"]
                        or (
                            obstacle_side is not None
                            and obstacle_side <= self.pass_obstacle_seen_cm
                        )
                    )
                ):
                    self.avoidance_obstacle_seen = True
                    self.avoidance_condition_since = None
                    extra["reason"] = "obstacle_side_detected"
                    if self.pause_for_measurement(
                        "3_OF_5_SIDE_OBSTACLE_FIRST_SEEN",
                        "resume_forward_search",
                    ):
                        self.finish_evaluation(extra)
                        return

                if (
                    self.avoidance_obstacle_seen
                    and self.rear_edge_detector["detected"]
                ):
                    self.get_logger().warn(
                        "Fast rear edge transition confirmed: "
                        f"sensor={self.inner_obstacle_sensor()}, "
                        f"near={self.rear_edge_detector['near_cm']} cm, "
                        f"far={self.rear_edge_detector['far_cm']} cm, "
                        f"samples={self.rear_edge_detector['candidate_count']}."
                    )
                    if not self.pause_for_measurement(
                        "4_OF_5_REAR_EDGE_CLEARED",
                        "start_forward_margin",
                    ):
                        self.start_forward_margin_stage()
                elif self.avoidance_obstacle_seen and self.condition_confirmed(
                    (
                        obstacle_side is not None
                        and obstacle_side >= self.pass_obstacle_clear_cm
                    ),
                    self.front_clear_confirm_s,
                ):
                    if not self.pause_for_measurement(
                        "4_OF_5_REAR_EDGE_CLEARED",
                        "start_forward_margin",
                    ):
                        self.start_forward_margin_stage()
                elif self.pose_reached(self.avoidance_target):
                    reason = (
                        "obstacle_side_never_detected"
                        if not self.avoidance_obstacle_seen
                        else "rear_edge_not_found_within_forward_limit"
                    )
                    self.abort_avoidance(reason)

        elif self.state == "STATIC_FORWARD_MARGIN":
            if self.check_avoidance_motion_health() and self.pose_reached(
                self.avoidance_target
            ):
                if not self.pause_for_measurement(
                    "5_OF_5_FORWARD_MARGIN_COMPLETE",
                    "begin_return_wait",
                ):
                    self.begin_return_wait()

        elif self.state == "MEASUREMENT_PAUSED":
            stopped = (
                self.esp_data is not None
                and not bool(self.esp_data.get("poseMode", False))
                and abs(self.command_value("vx")) <= self.motion_command_epsilon
                and abs(self.command_value("vy")) <= self.motion_command_epsilon
                and abs(self.command_value("wz")) <= self.rotation_command_epsilon
            )
            if stopped:
                self.record_measurement_settled()
            else:
                self.publish_stop(
                    f"measurement_checkpoint_{self.measurement_checkpoint}"
                )

        elif self.state == "STATIC_RETURN_WAIT_CLEAR":
            return_distance = self.distance(self.return_direction_sensor())
            if self.condition_confirmed(
                (
                    return_distance is not None
                    and return_distance >= self.side_motion_clear_cm
                ),
                self.safety_release_confirm_s,
            ):
                self.start_return_stage()

        elif self.state == "STATIC_RETURN_PATH":
            if self.check_avoidance_motion_health() and self.pose_reached(
                self.avoidance_target
            ):
                self.complete_current_avoidance()

        elif self.state == "STATIC_SIDE_LONGITUDINAL_FIND_EDGE":
            if self.check_avoidance_motion_health():
                obstacle_distance = self.direction_distance(
                    self.side_obstacle_direction
                )
                clear_threshold = self.direction_clear_threshold(
                    self.side_obstacle_direction
                )
                if self.front_edge_detector["detected"]:
                    self.get_logger().warn(
                        "Fast side-obstacle first edge confirmed: "
                        f"sensor={self.side_obstacle_direction}, "
                        f"near={self.front_edge_detector['near_cm']} cm, "
                        f"far={self.front_edge_detector['far_cm']} cm, "
                        f"samples={self.front_edge_detector['candidate_count']}."
                    )
                    self.start_side_longitudinal_margin_stage()
                elif self.condition_confirmed(
                    (
                        obstacle_distance is not None
                        and clear_threshold is not None
                        and obstacle_distance >= clear_threshold
                    ),
                    self.front_clear_confirm_s,
                ):
                    self.get_logger().warn(
                        "Side-obstacle first edge was not sharp enough; "
                        "using the slower filtered-clear fallback."
                    )
                    self.start_side_longitudinal_margin_stage()
                elif self.pose_reached(self.avoidance_target):
                    self.abort_avoidance(
                        "side_obstacle_first_edge_not_found_within_limit"
                    )

        elif self.state == "STATIC_SIDE_LONGITUDINAL_MARGIN":
            if self.check_avoidance_motion_health() and self.pose_reached(
                self.avoidance_target
            ):
                self.start_side_strafe_search_stage()

        elif self.state == "STATIC_SIDE_STRAFE_FIND_EDGE":
            if self.check_avoidance_motion_health():
                inner_sensor = self.side_inner_sensor()
                obstacle_end = self.distance(inner_sensor)
                raw_obstacle_end = self.raw_distance(inner_sensor)
                if (
                    not self.avoidance_obstacle_seen
                    and (
                        (
                            raw_obstacle_end is not None
                            and raw_obstacle_end <= self.pass_obstacle_seen_cm
                        )
                        or self.rear_edge_detector["armed"]
                        or (
                            obstacle_end is not None
                            and obstacle_end <= self.pass_obstacle_seen_cm
                        )
                    )
                ):
                    self.avoidance_obstacle_seen = True
                    self.avoidance_condition_since = None
                    extra["reason"] = "side_obstacle_front_back_sensor_detected"

                if (
                    self.avoidance_obstacle_seen
                    and self.rear_edge_detector["detected"]
                ):
                    self.get_logger().warn(
                        "Fast side-obstacle far edge confirmed: "
                        f"sensor={inner_sensor}, "
                        f"near={self.rear_edge_detector['near_cm']} cm, "
                        f"far={self.rear_edge_detector['far_cm']} cm, "
                        f"samples={self.rear_edge_detector['candidate_count']}."
                    )
                    self.start_side_strafe_margin_stage()
                elif self.avoidance_obstacle_seen and self.condition_confirmed(
                    (
                        obstacle_end is not None
                        and obstacle_end >= self.pass_obstacle_clear_cm
                    ),
                    self.front_clear_confirm_s,
                ):
                    self.start_side_strafe_margin_stage()
                elif self.pose_reached(self.avoidance_target):
                    reason = (
                        "side_obstacle_not_seen_by_front_back_sensor"
                        if not self.avoidance_obstacle_seen
                        else "side_obstacle_far_edge_not_found_within_limit"
                    )
                    self.abort_avoidance(reason)

        elif self.state == "STATIC_SIDE_STRAFE_MARGIN":
            if self.check_avoidance_motion_health() and self.pose_reached(
                self.avoidance_target
            ):
                self.begin_side_return_wait()

        elif self.state == "STATIC_SIDE_RETURN_WAIT_CLEAR":
            return_sensor = self.side_return_sensor()
            return_direction = self.opposite_direction(
                self.longitudinal_detour_direction
            )
            return_distance = self.distance(return_sensor)
            return_threshold = self.direction_clear_threshold(return_direction)
            if self.condition_confirmed(
                (
                    return_distance is not None
                    and return_threshold is not None
                    and return_distance >= return_threshold
                ),
                self.safety_release_confirm_s,
            ):
                self.start_side_return_stage()

        elif self.state == "STATIC_SIDE_RETURN_PATH":
            if self.check_avoidance_motion_health() and self.pose_reached(
                self.avoidance_target
            ):
                self.complete_current_avoidance()

        elif self.state == "STATIC_NOMINAL_REJOIN":
            if self.check_avoidance_motion_health() and self.pose_reached(
                self.avoidance_target
            ):
                if self.forbidden_detour_directions:
                    self.get_logger().warn(
                        "Navigation line recovered; clearing "
                        "previous-obstacle direction locks="
                        f"{sorted(self.forbidden_detour_directions)}."
                    )
                    self.forbidden_detour_directions.clear()
                self.rejoin_nominal_after_avoidance = False
                self.resume_original_target()
                self.state = "CLEAR"
                self.blocked_since = None
                self.reset_avoidance()

        elif self.state == "AVOIDANCE_PAUSED":
            self.publish_stop(
                f"avoidance_paused_{self.avoidance_pause_sensor}"
            )
            pause_cleared = self.avoidance_pause_release()
            if (
                self.avoidance_pause_timeout_s > 0.0
                and self.now_s() - self.avoidance_pause_started_s
                > self.avoidance_pause_timeout_s
            ):
                self.abort_avoidance("pause_timeout")
            elif (
                not pause_cleared
                and self.now_s() - self.avoidance_pause_started_s
                >= self.static_wait_s
            ):
                blocked_direction = self.avoidance_pause_sensor
                self.replan_for_persistent_obstacle(blocked_direction)
            elif self.condition_confirmed(
                pause_cleared,
                self.safety_release_confirm_s,
            ):
                resume_state = self.avoidance_pause_state
                cleared_sensor = self.avoidance_pause_sensor
                self.state = resume_state
                self.avoidance_stage_started_s = self.now_s()
                self.avoidance_last_progress_s = self.now_s()
                self.avoidance_last_progress_pose = self.current_pose()
                self.avoidance_condition_since = None
                self.avoidance_pause_state = None
                self.avoidance_pause_sensor = None
                self.avoidance_pause_started_s = None
                self.avoidance_pause_obstacle_direction = None
                if self.avoidance_target is None:
                    self.abort_avoidance("missing_target_after_pause")
                else:
                    extra["reason"] = (
                        f"temporary_{cleared_sensor}_obstacle_cleared_continuing"
                    )
                    self.get_logger().warn(
                        f"Temporary obstacle {cleared_sensor} cleared; "
                        f"continuing {resume_state}."
                    )
                    self.send_avoidance_target(
                        self.avoidance_target,
                        "temporary_obstacle_cleared",
                    )

        elif self.state == "AVOIDANCE_ABORTED":
            self.publish_stop(
                f"avoidance_aborted_{self.avoidance_abort_reason}"
            )

        elif self.state == "SAFETY_STOPPED":
            self.publish_stop(f"safety_stopped_{self.safety_hazard_sensor}")
            thresholds = {
                "back": ("back_center", self.back_clear_cm),
                "left": ("left", self.side_motion_clear_cm),
                "right": ("right", self.side_motion_clear_cm),
            }
            key, release_threshold = thresholds.get(
                self.safety_hazard_sensor, (None, None)
            )
            value = self.raw_distance(key) if key else None
            persistent_side_obstacle = (
                self.safety_hazard_sensor in ("left", "right")
                and self.blocked_since is not None
                and self.now_s() - self.blocked_since >= self.static_wait_s
                and value is not None
                and release_threshold is not None
                and value < release_threshold
            )

            if persistent_side_obstacle and self.enable_static_avoidance:
                detour_direction = (
                    self.choose_longitudinal_avoidance_direction()
                )
                if detour_direction is None:
                    extra["reason"] = "no_valid_front_or_back_reading"
                else:
                    obstacle_direction = self.safety_hazard_sensor
                    self.safety_hazard_sensor = None
                    self.safety_release_since = None
                    self.start_side_static_avoidance(
                        obstacle_direction,
                        detour_direction,
                    )
            elif persistent_side_obstacle:
                extra["reason"] = "side_static_avoidance_disabled"
            elif (
                value is not None
                and release_threshold is not None
                and value >= release_threshold
            ):
                if self.safety_release_since is None:
                    self.safety_release_since = self.now_s()
                elif (
                    self.now_s() - self.safety_release_since
                    >= self.safety_release_confirm_s
                ):
                    self.resume_original_target()
                    self.state = "CLEAR"
                    self.blocked_since = None
                    self.safety_hazard_sensor = None
                    self.safety_release_since = None
                    extra["reason"] = "directional_hazard_cleared_target_resumed"
            else:
                self.safety_release_since = None

        self.finish_evaluation(extra)

    def finish_evaluation(self, extra):
        if self.state != self.last_state_log:
            if (
                "reason" not in extra
                and self.status_reason_state != self.state
            ):
                self.status_reason = ""
                self.status_reason_state = None
            self.get_logger().warn(
                f"STATUS: {self.state_description(self.state)} | "
                f"state={self.state}, front={self.front_distance()}, "
                f"back={self.distance('back_center')}, "
                f"left={self.distance('left')}, right={self.distance('right')}, "
                f"side_obstacle={self.side_obstacle_direction}, "
                f"detour={self.longitudinal_detour_direction}"
            )
            self.last_state_log = self.state

        self.publish_state(extra)


def main(args=None):
    rclpy.init(args=args)
    node = ObstacleDecisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
