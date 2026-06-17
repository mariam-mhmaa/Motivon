#!/usr/bin/env python3

from dataclasses import dataclass
import threading
import time
from typing import Dict, List, Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger

from motivon_interfaces.action import NavigateToTarget, VerifyIdentity
from motivon_interfaces.msg import MissionEvent, MissionStatus
from motivon_interfaces.srv import StartMission


TERMINAL_STATES = {"IDLE", "COMPLETE", "ABORTED", "FAULTED"}
SAFETY_CLEAR_VALUES = {"", "OK", "CLEAR", "READY"}


@dataclass
class DeliveryRequest:
    request_id: str
    user: str
    item: str
    station: str


class MissionManagerNode(Node):
    """Run the fixed HOME-WP1-WP2-WP3-HOME delivery workflow."""

    def __init__(self) -> None:
        super().__init__("mission_manager_node")
        self.callback_group = ReentrantCallbackGroup()
        self.lock = threading.RLock()

        self._declare_parameters()
        self.station_targets = {
            "Station A": str(self.get_parameter("station_a_target").value),
            "Station B": str(self.get_parameter("station_b_target").value),
            "Station C": str(self.get_parameter("station_c_target").value),
        }
        self.home_target = str(self.get_parameter("home_target").value)
        self.no_request_hold_s = float(
            self.get_parameter("no_request_hold_s").value
        )
        self.service_wait_timeout_s = float(
            self.get_parameter("service_wait_timeout_s").value
        )
        self.lid_motion_timeout_s = float(
            self.get_parameter("lid_motion_timeout_s").value
        )
        self.navigation_server_timeout_s = float(
            self.get_parameter("navigation_server_timeout_s").value
        )
        self.navigation_goal_timeout_s = float(
            self.get_parameter("navigation_goal_timeout_s").value
        )
        self.service_retry_count = int(
            self.get_parameter("service_retry_count").value
        )
        self.use_vision = bool(self.get_parameter("use_vision").value)
        self.vision_action_name = str(
            self.get_parameter("vision_action_name").value
        )
        self.vision_server_timeout_s = float(
            self.get_parameter("vision_server_timeout_s").value
        )
        self.vision_attempt_timeout_s = float(
            self.get_parameter("vision_attempt_timeout_s").value
        )
        self.vision_primary_attempts = int(
            self.get_parameter("vision_primary_attempts").value
        )
        self.vision_secondary_attempts = int(
            self.get_parameter("vision_secondary_attempts").value
        )
        self.vision_retry_pause_s = float(
            self.get_parameter("vision_retry_pause_s").value
        )
        self.vision_required_success_frames = int(
            self.get_parameter("vision_required_success_frames").value
        )
        self.vision_min_confidence = float(
            self.get_parameter("vision_min_confidence").value
        )
        self.identity_map = self._load_identity_map()
        self.manager_identity = self._map_identity(
            str(self.get_parameter("manager_identity").value)
        )

        self.status_pub = self.create_publisher(
            MissionStatus, "/mission/status", 10
        )
        self.event_pub = self.create_publisher(
            MissionEvent, "/mission/events", 10
        )
        self.base_enable_pub = self.create_publisher(
            Bool, "/base/enable", 10
        )

        self.navigate_client = ActionClient(
            self,
            NavigateToTarget,
            "/navigation/navigate_to_target",
            callback_group=self.callback_group,
        )
        self.verify_identity_client = ActionClient(
            self,
            VerifyIdentity,
            self.vision_action_name,
            callback_group=self.callback_group,
        )
        self.lid_open_client = self.create_client(
            Trigger, "/lid/open", callback_group=self.callback_group
        )
        self.lid_close_client = self.create_client(
            Trigger, "/lid/close", callback_group=self.callback_group
        )
        self.lid_stop_client = self.create_client(
            Trigger, "/lid/stop", callback_group=self.callback_group
        )
        self.set_home_client = self.create_client(
            Trigger, "/navigation/set_home", callback_group=self.callback_group
        )
        self.reset_odom_client = self.create_client(
            Trigger, "/wheel_odometry/reset", callback_group=self.callback_group
        )

        self.create_service(
            StartMission,
            "/mission/start",
            self.start_callback,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/mission/cancel",
            self.cancel_callback,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/mission/confirm_manager_verified",
            self.confirm_manager_verified_callback,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/mission/confirm_manager_loaded",
            self.confirm_manager_loaded_callback,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/mission/confirm_user_verified",
            self.confirm_user_verified_callback,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/mission/confirm_user_received",
            self.confirm_user_received_callback,
            callback_group=self.callback_group,
        )

        self.create_subscription(
            String,
            "/system/mode",
            self.mode_callback,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            String,
            "/safety/state",
            self.safety_callback,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            String,
            "/lid/status",
            self.lid_status_callback,
            10,
            callback_group=self.callback_group,
        )

        self.state = "IDLE"
        self.detail = "Ready for selected delivery requests."
        self.current_target = ""
        self.current_station = ""
        self.active_request: Optional[DeliveryRequest] = None
        self.requests: List[DeliveryRequest] = []
        self.completed_request_ids: List[str] = []
        self.cancel_requested = False
        self.faulted = False
        self.safety_paused = False
        self.mode = "AUTO"
        self.latest_lid_status = ""
        self.worker: Optional[threading.Thread] = None
        self.active_goal_handle = None
        self.active_vision_goal_handle = None

        self.manager_verified_event = threading.Event()
        self.manager_loaded_event = threading.Event()
        self.user_verified_event = threading.Event()
        self.user_received_event = threading.Event()

        self.create_timer(0.10, self.publish_status)
        self.get_logger().info("Mission manager ready.")

    def _declare_parameters(self) -> None:
        defaults = {
            "station_a_target": "WP1",
            "station_b_target": "WP2",
            "station_c_target": "WP3",
            "home_target": "HOME",
            "no_request_hold_s": 3.0,
            "service_wait_timeout_s": 5.0,
            "lid_motion_timeout_s": 75.0,
            "navigation_server_timeout_s": 5.0,
            "navigation_goal_timeout_s": 180.0,
            "service_retry_count": 3,
            "use_vision": True,
            "vision_action_name": "/vision/verify_identity",
            "vision_server_timeout_s": 5.0,
            "vision_attempt_timeout_s": 8.0,
            "vision_primary_attempts": 3,
            "vision_secondary_attempts": 3,
            "vision_retry_pause_s": 2.0,
            "vision_required_success_frames": 3,
            "vision_min_confidence": 0.20,
            "manager_identity": "nour",
            "identity_map_entries": [
                "nour=Nour",
                "ainour=Ainour",
                "mariam=Mariam",
                "zeina=Zeina",
            ],
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

    def _load_identity_map(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        entries = self.get_parameter("identity_map_entries").value
        for entry in entries:
            text = str(entry)
            if "=" in text:
                key, value = text.split("=", 1)
            elif ":" in text:
                key, value = text.split(":", 1)
            else:
                continue
            key = key.strip().lower()
            value = value.strip()
            if key and value:
                mapping[key] = value
                mapping[value.lower()] = value
        return mapping

    def _map_identity(self, identity: str) -> str:
        text = str(identity).strip()
        if not text:
            return ""
        return self.identity_map.get(text.lower(), text)

    def start_callback(self, request, response):
        validation = self._validate_start_request(request)
        if validation:
            response.success = False
            response.message = validation
            return response

        with self.lock:
            if self.state not in TERMINAL_STATES:
                response.success = False
                response.message = f"Mission already active: {self.state}."
                return response

            self.requests = [
                DeliveryRequest(
                    request_id=str(request.request_ids[index]),
                    user=str(request.users[index]),
                    item=str(request.items[index]),
                    station=str(request.stations[index]),
                )
                for index in range(len(request.request_ids))
            ]
            self.completed_request_ids = []
            self.cancel_requested = False
            self.faulted = False
            self.active_request = None
            self.current_target = ""
            self.current_station = ""
            self._clear_confirmation_events()
            self._set_state_locked(
                "REQUESTS_RECEIVED",
                f"Received {len(self.requests)} selected request(s).",
            )
            self.worker = threading.Thread(
                target=self._run_mission,
                name="motivon_mission_worker",
                daemon=True,
            )
            self.worker.start()

        self._publish_event(
            "MISSION_STARTED",
            message=f"Mission accepted with {len(request.request_ids)} request(s).",
        )
        response.success = True
        response.message = "Mission accepted."
        return response

    def _validate_start_request(self, request) -> str:
        count = len(request.request_ids)
        if count == 0:
            return "At least one request is required."
        if not (
            count
            == len(request.users)
            == len(request.items)
            == len(request.stations)
        ):
            return "request_ids, users, items, and stations must match length."
        for station in request.stations:
            if str(station) not in self.station_targets:
                return f"Unknown station: {station}."
        for request_id in request.request_ids:
            if not str(request_id).strip():
                return "Request IDs must not be empty."
        return ""

    def cancel_callback(self, _request, response):
        self._request_abort("Mission cancelled by manager.", fault=False)
        response.success = True
        response.message = "Mission cancel requested."
        return response

    def confirm_manager_verified_callback(self, _request, response):
        if self.use_vision:
            response.success = False
            response.message = (
                "Manager identity is verified automatically by /vision/verify_identity."
            )
            return response
        result = self._confirm(
            response,
            "MANAGER_VERIFYING",
            self.manager_verified_event,
            "Manager verification confirmed.",
        )
        if result.success:
            self._publish_event("VISION_VERIFIED", message=result.message)
        return result

    def confirm_manager_loaded_callback(self, _request, response):
        return self._confirm(
            response,
            "WAITING_FOR_MANAGER_LOAD",
            self.manager_loaded_event,
            "Manager loading confirmed.",
        )

    def confirm_user_verified_callback(self, _request, response):
        if self.use_vision:
            response.success = False
            response.message = (
                "User identity is verified automatically by /vision/verify_identity."
            )
            return response
        result = self._confirm(
            response,
            "USER_VERIFYING",
            self.user_verified_event,
            "User verification confirmed.",
        )
        if result.success:
            self._publish_event("VISION_VERIFIED", message=result.message)
        return result

    def confirm_user_received_callback(self, _request, response):
        return self._confirm(
            response,
            "WAITING_FOR_USER_RECEIPT",
            self.user_received_event,
            "User receipt confirmed.",
        )

    def _confirm(self, response, expected_state, event, message):
        with self.lock:
            if self.state != expected_state:
                response.success = False
                response.message = (
                    f"Cannot confirm while mission state is {self.state}."
                )
                return response
            event.set()
            self.detail = message
        response.success = True
        response.message = message
        return response

    def mode_callback(self, msg: String) -> None:
        mode = msg.data.strip().upper()
        with self.lock:
            self.mode = mode
        if mode == "MANUAL":
            self._request_abort("Manual mode selected.", fault=False)

    def safety_callback(self, msg: String) -> None:
        paused = msg.data.strip().upper() not in SAFETY_CLEAR_VALUES
        with self.lock:
            self.safety_paused = paused
            if paused:
                self.detail = "Safety stop active; mission is paused."

    def lid_status_callback(self, msg: String) -> None:
        with self.lock:
            self.latest_lid_status = msg.data

    def _run_mission(self) -> None:
        try:
            self._set_state(
                "MANAGER_VERIFYING",
                (
                    f"Verifying manager identity ({self.manager_identity})."
                    if self.use_vision
                    else "Waiting for manager verification."
                ),
            )
            if self.use_vision:
                if not self._verify_identity_with_retries(
                    self.manager_identity,
                    "HOME_LOADING",
                    "MANAGER",
                    abort_on_failure=True,
                ):
                    return
            elif not self._wait_for_event(self.manager_verified_event):
                return

            self._set_state("OPENING_LID_FOR_LOADING", "Opening lid for loading.")
            if not self._call_lid(self.lid_open_client, "/lid/open"):
                return

            self._set_state(
                "WAITING_FOR_MANAGER_LOAD",
                "Waiting for manager to load selected items.",
            )
            if not self._wait_for_event(self.manager_loaded_event):
                return

            self._set_state("SETTING_HOME", "Resetting odometry and setting HOME.")
            if not self._prepare_home():
                return

            self._set_state(
                "CLOSING_LID_AFTER_LOADING",
                "Closing lid before starting route.",
            )
            if not self._call_lid(self.lid_close_client, "/lid/close"):
                return

            self._publish_base_enable(True)

            route = [
                ("Station A", self.station_targets["Station A"]),
                ("Station B", self.station_targets["Station B"]),
                ("Station C", self.station_targets["Station C"]),
            ]
            for station, target in route:
                if self._should_stop():
                    return
                self.current_station = station
                self.current_target = target
                self._set_state(
                    f"NAVIGATING_TO_{target}",
                    f"Navigating to {station} ({target}).",
                )
                if not self._navigate_to(target):
                    return
                if not self._handle_station(station, target):
                    return

            self.current_station = ""
            self.current_target = self.home_target
            self._set_state("RETURNING_HOME", "Returning to HOME.")
            if not self._navigate_to(self.home_target):
                return

            self._publish_base_enable(False)
            self.current_target = ""
            self._set_state("COMPLETE", "Mission complete.")
            self._publish_event("MISSION_COMPLETE", message="Mission complete.")
        except Exception as error:
            self._fault(f"Unexpected mission error: {type(error).__name__}: {error}")

    def _prepare_home(self) -> bool:
        if not self._call_trigger(
            self.reset_odom_client,
            "/wheel_odometry/reset",
            timeout_s=self.service_wait_timeout_s,
        ):
            return False
        return self._call_trigger(
            self.set_home_client,
            "/navigation/set_home",
            timeout_s=self.service_wait_timeout_s,
        )

    def _handle_station(self, station: str, target: str) -> bool:
        station_requests = [
            request for request in self.requests if request.station == station
        ]
        self._set_state(f"HANDLING_{target}", f"Handling {station}.")
        if not station_requests:
            return self._hold_no_request_station(station)

        for request in station_requests:
            if self._should_stop():
                return False
            self.active_request = request
            self._publish_event(
                "REQUEST_ACTIVE",
                request,
                f"Handling {request.request_id} at {station}.",
            )
            self.user_received_event.clear()
            self.user_verified_event.clear()

            self._set_state(
                "USER_VERIFYING",
                (
                    f"Verifying {request.user} for {request.request_id}."
                    if self.use_vision
                    else f"Waiting for user verification for {request.request_id}."
                ),
            )
            if self.use_vision:
                if not self._verify_identity_with_retries(
                    request.user,
                    "STATION_DELIVERY",
                    request.request_id,
                    abort_on_failure=False,
                ):
                    self._publish_event(
                        "REQUEST_SKIPPED_UNVERIFIED",
                        request,
                        (
                            f"{request.request_id} skipped because "
                            f"{request.user} was not verified."
                        ),
                    )
                    self.active_request = None
                    continue
            elif not self._wait_for_event(self.user_verified_event):
                return False

            self._set_state(
                "OPENING_LID_FOR_USER",
                f"Opening lid for {request.request_id}.",
            )
            if not self._call_lid(self.lid_open_client, "/lid/open"):
                return False

            self._set_state(
                "WAITING_FOR_USER_RECEIPT",
                f"Waiting for receipt confirmation for {request.request_id}.",
            )
            if not self._wait_for_event(self.user_received_event):
                return False

            self._set_state(
                "CLOSING_LID_AFTER_USER",
                f"Closing lid after {request.request_id}.",
            )
            if not self._call_lid(self.lid_close_client, "/lid/close"):
                return False

            self.completed_request_ids.append(request.request_id)
            self._publish_event(
                "REQUEST_COMPLETED",
                request,
                f"{request.request_id} completed.",
            )
            self.active_request = None

        self._set_state(f"HANDLING_{target}", f"{station} complete.")
        return True

    def _hold_no_request_station(self, station: str) -> bool:
        self._set_state(
            "NO_REQUEST_HOLDING_3S",
            f"No request at {station}; holding {self.no_request_hold_s:.1f} s.",
        )
        deadline = time.monotonic() + self.no_request_hold_s
        while time.monotonic() < deadline:
            if self._should_stop():
                return False
            if not self._wait_while_safety_paused():
                return False
            remaining = max(0.0, deadline - time.monotonic())
            self.detail = f"No request at {station}; holding {remaining:.1f} s."
            time.sleep(0.05)
        return True

    def _navigate_to(self, target: str) -> bool:
        for attempt in range(1, self.service_retry_count + 1):
            if self._should_stop():
                return False
            if not self._wait_while_safety_paused():
                return False
            if not self.navigate_client.wait_for_server(
                timeout_sec=self.navigation_server_timeout_s
            ):
                self.detail = (
                    "Waiting for /navigation/navigate_to_target action server "
                    f"({attempt}/{self.service_retry_count})."
                )
                continue

            goal = NavigateToTarget.Goal()
            goal.target_name = target
            goal.hold_time_s = 0.0
            send_future = self.navigate_client.send_goal_async(goal)
            if not self._wait_for_future(
                send_future,
                self.service_wait_timeout_s,
                f"send navigation goal {target}",
            ):
                continue
            goal_handle = send_future.result()
            if goal_handle is None or not goal_handle.accepted:
                self.detail = f"Navigation rejected {target}; resetting HOME."
                self._prepare_home()
                continue

            with self.lock:
                self.active_goal_handle = goal_handle
            result_future = goal_handle.get_result_async()
            if not self._wait_for_navigation_result(result_future, target):
                return False
            try:
                result = result_future.result().result
            except Exception as error:
                self._fault(
                    f"Navigation to {target} returned an invalid result: {error}."
                )
                return False
            with self.lock:
                self.active_goal_handle = None
            if result.status == NavigateToTarget.Result.STATUS_SUCCEEDED:
                return True
            if result.status == NavigateToTarget.Result.STATUS_CANCELLED:
                return False
            self._fault(
                f"Navigation to {target} failed: {result.message} "
                f"(status {result.status})."
            )
            return False

        self._fault(f"Navigation to {target} could not be started.")
        return False

    def _wait_for_navigation_result(self, result_future, target: str) -> bool:
        started = time.monotonic()
        while not result_future.done():
            if self._should_stop():
                self._cancel_active_navigation()
                return False
            if self.safety_paused:
                started += 0.10
            elif time.monotonic() - started > self.navigation_goal_timeout_s:
                self._cancel_active_navigation()
                self._fault(f"Navigation to {target} timed out.")
                return False
            time.sleep(0.10)
        return True

    def _verify_identity_with_retries(
        self,
        expected_identity: str,
        context: str,
        request_id: str,
        abort_on_failure: bool,
    ) -> bool:
        expected = self._map_identity(expected_identity)
        if not expected:
            message = "Vision verification requested with an empty identity."
            if abort_on_failure:
                self._fault(message)
            else:
                self.detail = message
            return False

        total_attempts = self.vision_primary_attempts + self.vision_secondary_attempts
        last_failure = "Vision verification did not run."

        for attempt in range(1, total_attempts + 1):
            if self._should_stop():
                return False
            if not self._wait_while_safety_paused():
                return False

            if attempt == self.vision_primary_attempts + 1:
                self._set_state(
                    self.state,
                    (
                        f"Vision did not verify {expected}; waiting "
                        f"{self.vision_retry_pause_s:.1f} s before retry block."
                    ),
                )
                if not self._sleep_interruptible(self.vision_retry_pause_s):
                    return False

            self.detail = (
                f"Vision verification attempt {attempt}/{total_attempts} "
                f"for {expected}."
            )
            result = self._send_verify_identity_goal(
                expected,
                context,
                request_id,
                attempt,
            )
            if result is not None and result.verified:
                self._publish_event(
                    "VISION_VERIFIED",
                    message=(
                        f"{expected} verified as {result.matched_identity} "
                        f"with confidence {result.confidence:.2f}."
                    ),
                )
                return True

            if result is None:
                last_failure = "Vision action did not return a result."
            else:
                last_failure = result.failure_reason or (
                    f"Expected {expected}, saw {result.matched_identity}."
                )

            self._publish_event(
                "VISION_VERIFY_ATTEMPT_FAILED",
                message=(
                    f"Attempt {attempt}/{total_attempts} failed for "
                    f"{expected}: {last_failure}"
                ),
            )

        message = f"Vision could not verify {expected}: {last_failure}"
        if abort_on_failure:
            self._fault(message)
        else:
            self.detail = message
        return False

    def _send_verify_identity_goal(
        self,
        expected: str,
        context: str,
        request_id: str,
        attempt: int,
    ):
        if not self.verify_identity_client.wait_for_server(
            timeout_sec=self.vision_server_timeout_s
        ):
            self.detail = (
                f"Waiting for {self.vision_action_name} action server."
            )
            return None

        goal = VerifyIdentity.Goal()
        goal.expected_identity = expected
        goal.context = context
        goal.request_id = request_id
        goal.timeout_s = float(self.vision_attempt_timeout_s)
        goal.required_success_frames = int(self.vision_required_success_frames)
        goal.min_confidence = float(self.vision_min_confidence)

        send_future = self.verify_identity_client.send_goal_async(
            goal,
            feedback_callback=lambda feedback_msg: self._on_vision_feedback(
                feedback_msg,
                expected,
                attempt,
            ),
        )
        if not self._wait_for_future(
            send_future,
            self.service_wait_timeout_s,
            f"send vision goal for {expected}",
        ):
            return None

        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            self.detail = f"Vision rejected verification goal for {expected}."
            return None

        with self.lock:
            self.active_vision_goal_handle = goal_handle

        result_future = goal_handle.get_result_async()
        try:
            if not self._wait_for_vision_result(result_future, expected):
                return None
            return result_future.result().result
        except Exception as error:
            self.detail = f"Vision result for {expected} failed: {error}."
            return None
        finally:
            with self.lock:
                self.active_vision_goal_handle = None

    def _on_vision_feedback(self, feedback_msg, expected: str, attempt: int) -> None:
        feedback = feedback_msg.feedback
        with self.lock:
            self.detail = (
                f"Vision attempt {attempt} for {expected}: {feedback.state}; "
                f"face={feedback.face_detected}, "
                f"current={feedback.current_identity}, "
                f"conf={feedback.current_confidence:.2f}, "
                f"remaining={feedback.remaining_s:.1f} s."
            )

    def _wait_for_vision_result(self, result_future, expected: str) -> bool:
        deadline = time.monotonic() + self.vision_attempt_timeout_s + 3.0
        while not result_future.done():
            if self._should_stop():
                self._cancel_active_vision()
                return False
            if self.safety_paused:
                deadline += 0.10
            elif time.monotonic() > deadline:
                self._cancel_active_vision()
                self.detail = f"Vision verification for {expected} timed out."
                return False
            time.sleep(0.05)
        return True

    def _sleep_interruptible(self, duration_s: float) -> bool:
        deadline = time.monotonic() + max(0.0, duration_s)
        while time.monotonic() < deadline:
            if self._should_stop():
                return False
            if not self._wait_while_safety_paused():
                return False
            time.sleep(0.05)
        return True

    def _call_lid(self, client, service_name: str) -> bool:
        return self._call_trigger(
            client, service_name, timeout_s=self.lid_motion_timeout_s
        )

    def _call_trigger(self, client, service_name: str, timeout_s: float) -> bool:
        for attempt in range(1, self.service_retry_count + 1):
            if self._should_stop():
                return False
            if not self._wait_while_safety_paused():
                return False
            if not client.wait_for_service(timeout_sec=self.service_wait_timeout_s):
                self.detail = (
                    f"Waiting for {service_name} "
                    f"({attempt}/{self.service_retry_count})."
                )
                continue
            future = client.call_async(Trigger.Request())
            if not self._wait_for_future(
                future,
                timeout_s,
                service_name,
            ):
                continue
            try:
                response = future.result()
            except Exception as error:
                self.detail = f"{service_name} failed: {error}."
                continue
            if response.success:
                return True
            self.detail = f"{service_name} returned failure: {response.message}."

        self._fault(f"{service_name} failed after retries.")
        return False

    def _wait_for_future(self, future, timeout_s: float, label: str) -> bool:
        deadline = time.monotonic() + timeout_s
        while not future.done():
            if self._should_stop():
                return False
            if self.safety_paused:
                deadline += 0.10
            elif time.monotonic() > deadline:
                self.detail = f"Timeout while waiting for {label}."
                return False
            time.sleep(0.05)
        return True

    def _wait_for_event(self, event: threading.Event) -> bool:
        while not event.is_set():
            if self._should_stop():
                return False
            if not self._wait_while_safety_paused():
                return False
            time.sleep(0.05)
        return True

    def _wait_while_safety_paused(self) -> bool:
        while self.safety_paused:
            if self._should_stop():
                return False
            time.sleep(0.10)
        return True

    def _should_stop(self) -> bool:
        with self.lock:
            return self.cancel_requested or self.faulted

    def _request_abort(self, message: str, fault: bool) -> None:
        with self.lock:
            if self.state in TERMINAL_STATES:
                return
            self.cancel_requested = True
            if fault:
                self.faulted = True
            self.detail = message
            self._set_state_locked("FAULTED" if fault else "ABORTING", message)
            self._clear_confirmation_events(set_all=True)
        self._cancel_active_navigation()
        self._cancel_active_vision()
        self._call_lid_stop_best_effort()
        self._publish_base_enable(False)
        self._publish_event("MISSION_FAULTED" if fault else "MISSION_CANCELLED", message=message)
        with self.lock:
            if not fault:
                self._set_state_locked("ABORTED", message)

    def _fault(self, message: str) -> None:
        self.get_logger().error(message)
        self._request_abort(message, fault=True)

    def _cancel_active_navigation(self) -> None:
        with self.lock:
            goal_handle = self.active_goal_handle
        if goal_handle is None:
            return
        try:
            future = goal_handle.cancel_goal_async()
            self._wait_for_future(future, 2.0, "cancel navigation")
        except Exception as error:
            self.get_logger().warning(f"Navigation cancel failed: {error}")

    def _cancel_active_vision(self) -> None:
        with self.lock:
            goal_handle = self.active_vision_goal_handle
        if goal_handle is None:
            return
        try:
            future = goal_handle.cancel_goal_async()
            self._wait_for_future(future, 2.0, "cancel vision verification")
        except Exception as error:
            self.get_logger().warning(f"Vision cancel failed: {error}")

    def _call_lid_stop_best_effort(self) -> None:
        if not self.lid_stop_client.wait_for_service(timeout_sec=0.2):
            return
        try:
            self.lid_stop_client.call_async(Trigger.Request())
        except Exception as error:
            self.get_logger().warning(f"Lid stop request failed: {error}")

    def _publish_base_enable(self, enabled: bool) -> None:
        msg = Bool()
        msg.data = bool(enabled)
        for _ in range(3):
            self.base_enable_pub.publish(msg)
            time.sleep(0.03)

    def _set_state(self, state: str, detail: str) -> None:
        with self.lock:
            self._set_state_locked(state, detail)

    def _set_state_locked(self, state: str, detail: str) -> None:
        if self.state != state:
            self.get_logger().info(f"Mission state: {self.state} -> {state}")
        self.state = state
        self.detail = detail

    def _clear_confirmation_events(self, set_all: bool = False) -> None:
        events = (
            self.manager_verified_event,
            self.manager_loaded_event,
            self.user_verified_event,
            self.user_received_event,
        )
        for event in events:
            if set_all:
                event.set()
            else:
                event.clear()

    def _publish_event(
        self,
        event_type: str,
        request: Optional[DeliveryRequest] = None,
        message: str = "",
    ) -> None:
        event = MissionEvent()
        event.stamp = self.get_clock().now().to_msg()
        event.event_type = event_type
        event.state = self.state
        event.message = message
        if request is not None:
            event.request_id = request.request_id
            event.station = request.station
            event.user = request.user
            event.item = request.item
        self.event_pub.publish(event)

    def publish_status(self) -> None:
        with self.lock:
            status = MissionStatus()
            status.stamp = self.get_clock().now().to_msg()
            status.state = self.state
            status.detail = self.detail
            status.current_target = self.current_target
            status.current_station = self.current_station
            if self.active_request is not None:
                status.active_request_id = self.active_request.request_id
                status.active_user = self.active_request.user
                status.active_item = self.active_request.item
            status.completed_count = len(self.completed_request_ids)
            status.total_count = len(self.requests)
            status.can_confirm_manager_verified = (
                not self.use_vision and self.state == "MANAGER_VERIFYING"
            )
            status.can_confirm_manager_loaded = (
                self.state == "WAITING_FOR_MANAGER_LOAD"
            )
            status.can_confirm_user_verified = (
                not self.use_vision and self.state == "USER_VERIFYING"
            )
            status.can_confirm_user_received = (
                self.state == "WAITING_FOR_USER_RECEIPT"
            )
            status.mission_active = self.state not in TERMINAL_STATES
            status.safety_paused = self.safety_paused
            status.faulted = self.faulted
        self.status_pub.publish(status)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MissionManagerNode()
    executor = MultiThreadedExecutor(num_threads=4)
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
