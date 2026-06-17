#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import os
from pathlib import Path
import sys
import threading
import time
from typing import Dict, Optional

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage

from motivon_interfaces.action import VerifyIdentity
from motivon_interfaces.msg import VisionDetection, VisionStatus


@dataclass
class DetectionSnapshot:
    sequence: int = 0
    face_detected: bool = False
    person_name: str = "NO_FACE"
    is_unknown: bool = True
    confidence: float = 0.0
    threshold: float = 0.0
    bbox_x1: int = 0
    bbox_y1: int = 0
    bbox_x2: int = 0
    bbox_y2: int = 0
    bbox_width: int = 0
    bbox_height: int = 0
    detail: str = "No frame processed yet."


class VisionNode(Node):
    """ROS wrapper around the existing real-time face recognizer."""

    def __init__(self) -> None:
        super().__init__("vision_node")
        self.callback_group = ReentrantCallbackGroup()
        self.lock = threading.RLock()
        self.recognition_lock = threading.RLock()

        self._declare_parameters()
        self.identity_map = self._load_identity_map()

        self.vision_project_dir = self._resolve_vision_project_dir(
            str(self.get_parameter("vision_project_dir").value)
        )
        self.camera_host = str(self.get_parameter("camera_host").value)
        self.camera_port = int(self.get_parameter("camera_port").value)
        self.camera_width = int(self.get_parameter("camera_width").value)
        self.camera_height = int(self.get_parameter("camera_height").value)
        self.camera_framerate = int(self.get_parameter("camera_framerate").value)
        self.auto_start_camera_server = bool(
            self.get_parameter("auto_start_camera_server").value
        )
        self.process_every_n_frames = max(
            1, int(self.get_parameter("process_every_n_frames").value)
        )
        self.smoothing_enabled = bool(
            self.get_parameter("smoothing_enabled").value
        )
        self.default_timeout_s = float(
            self.get_parameter("default_timeout_s").value
        )
        self.default_required_success_frames = int(
            self.get_parameter("default_required_success_frames").value
        )
        self.default_min_confidence = float(
            self.get_parameter("default_min_confidence").value
        )
        self.reconnect_period_s = float(
            self.get_parameter("reconnect_period_s").value
        )
        self.show_preview = bool(self.get_parameter("show_preview").value)
        self.preview_width = int(self.get_parameter("preview_width").value)
        self.preview_height = int(self.get_parameter("preview_height").value)
        self.preview_window_name = str(
            self.get_parameter("preview_window_name").value
        )
        self.publish_debug_image = bool(
            self.get_parameter("publish_debug_image").value
        )
        self.debug_image_quality = int(
            self.get_parameter("debug_image_quality").value
        )
        self.display_available = bool(
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        )
        self.preview_display_warning_emitted = False

        self.status_pub = self.create_publisher(
            VisionStatus, "/vision/status", 10
        )
        self.detection_pub = self.create_publisher(
            VisionDetection, "/vision/detection", 10
        )
        self.debug_image_pub = self.create_publisher(
            CompressedImage, "/vision/debug_image/compressed", 1
        )
        self.verify_server = ActionServer(
            self,
            VerifyIdentity,
            "/vision/verify_identity",
            execute_callback=self.execute_verify_identity,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self.callback_group,
        )

        self.state = "STARTING"
        self.detail = "Loading vision backend."
        self.camera_ok = False
        self.model_ok = False
        self.busy = False
        self.active_context = ""
        self.expected_identity = ""
        self.latest_detection = DetectionSnapshot()
        self.latest_raw_person_name = None
        self.latest_raw_confidence = 0.0
        self.latest_raw_is_unknown = True
        self.latest_margin = 0.0
        self.frames_read = 0
        self.frames_processed = 0
        self.detections_seen = 0
        self.active_goal_handle = None

        self.realtime_module = None
        self.camera_module = None
        self.recognizer = None
        self.camera = None
        self.camera_server = None
        self.running = True

        status_period_s = float(self.get_parameter("status_period_s").value)
        self.create_timer(
            status_period_s,
            self.publish_status,
            callback_group=self.callback_group,
        )

        self.worker = threading.Thread(
            target=self._capture_loop,
            name="motivon_vision_capture",
            daemon=True,
        )
        self.worker.start()
        self.get_logger().info(
            "Vision node ready: project=%s camera=%s:%d."
            % (self.vision_project_dir, self.camera_host, self.camera_port)
        )

    def _declare_parameters(self) -> None:
        defaults = {
            "vision_project_dir": "",
            "camera_host": "172.20.10.10",
            "camera_port": 8890,
            "camera_width": 1280,
            "camera_height": 720,
            "camera_framerate": 8,
            "auto_start_camera_server": False,
            "process_every_n_frames": 2,
            "smoothing_enabled": True,
            "confidence_threshold": 0.20,
            "margin_threshold": 0.02,
            "use_external_calibration": False,
            "use_known_detector": False,
            "default_timeout_s": 8.0,
            "default_required_success_frames": 3,
            "default_min_confidence": 0.20,
            "status_period_s": 0.20,
            "reconnect_period_s": 2.0,
            "show_preview": False,
            "preview_width": 720,
            "preview_height": 720,
            "preview_window_name": "Face Recognition System - Pi RAW TCP Camera",
            "publish_debug_image": False,
            "debug_image_quality": 85,
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
                mapping[value.strip().lower()] = value
        return mapping

    def _resolve_vision_project_dir(self, configured_path: str) -> Path:
        if configured_path.strip():
            path = Path(configured_path).expanduser().resolve()
            self._validate_vision_project_dir(path)
            return path

        search_roots = []
        cwd = Path.cwd().resolve()
        search_roots.append(cwd)
        search_roots.extend(cwd.parents)

        source_path = Path(__file__).resolve()
        search_roots.append(source_path.parent)
        search_roots.extend(source_path.parents)

        for root in search_roots:
            for relative in (
                Path("Vision again") / "Vision again",
                Path("Vision again"),
            ):
                candidate = root / relative
                if self._is_vision_project_dir(candidate):
                    return candidate.resolve()

        raise RuntimeError(
            "Could not find the existing vision project folder. Set "
            "vision_project_dir to the directory containing 06_real_time_camera.py."
        )

    @staticmethod
    def _is_vision_project_dir(path: Path) -> bool:
        return (
            path.exists()
            and (path / "06_real_time_camera.py").exists()
            and (path / "camera.py").exists()
            and (path / "models" / "classifier.pkl").exists()
        )

    def _validate_vision_project_dir(self, path: Path) -> None:
        if not self._is_vision_project_dir(path):
            raise RuntimeError(
                f"Invalid vision_project_dir: {path}. Expected "
                "06_real_time_camera.py, camera.py, and models/classifier.pkl."
            )

    def _load_backend(self) -> None:
        if self.realtime_module is not None and self.recognizer is not None:
            return

        if str(self.vision_project_dir) not in sys.path:
            sys.path.insert(0, str(self.vision_project_dir))

        script_path = self.vision_project_dir / "06_real_time_camera.py"
        spec = importlib.util.spec_from_file_location(
            "motivon_realtime_camera", script_path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load {script_path}.")

        module = importlib.util.module_from_spec(spec)
        sys.modules["motivon_realtime_camera"] = module
        spec.loader.exec_module(module)
        module.PROCESS_EVERY_N_FRAMES = self.process_every_n_frames
        self.realtime_module = module
        self.camera_module = importlib.import_module("camera")

        recognizer_class = getattr(module, "FaceRecognitionSystem")
        self.recognizer = recognizer_class(
            confidence_threshold=float(
                self.get_parameter("confidence_threshold").value
            ),
            margin_threshold=float(self.get_parameter("margin_threshold").value),
            use_external_calibration=bool(
                self.get_parameter("use_external_calibration").value
            ),
            use_known_detector=bool(
                self.get_parameter("use_known_detector").value
            ),
        )
        self.model_ok = True
        self.state = "IDLE"
        self.detail = "Vision model loaded; waiting for camera frames."

    def _open_camera(self) -> bool:
        if self.camera is not None:
            return True

        if self.camera_module is None:
            return False

        if self.auto_start_camera_server and self.camera_server is None:
            self.camera_server = self.camera_module.get_server_camera(
                host="0.0.0.0",
                port=self.camera_port,
                width=self.camera_width,
                height=self.camera_height,
                framerate=self.camera_framerate,
            )
            self.camera_server.start_server()

        camera = self.camera_module.get_client_camera(
            host=self.camera_host,
            port=self.camera_port,
            width=self.camera_width,
            height=self.camera_height,
            framerate=self.camera_framerate,
        )
        if not camera.open():
            camera.release()
            self.camera_ok = False
            self.detail = (
                f"Camera stream unavailable at {self.camera_host}:"
                f"{self.camera_port}."
            )
            return False

        self.camera = camera
        self.camera_ok = True
        self.detail = "Camera connected."
        return True

    def _capture_loop(self) -> None:
        last_frame_time = time.monotonic()
        while self.running and rclpy.ok():
            try:
                self._load_backend()
                if not self._open_camera():
                    time.sleep(self.reconnect_period_s)
                    continue

                ok, frame = self.camera.read()
                if not ok:
                    self.camera_ok = False
                    self.detail = "Waiting for camera frame."
                    if time.monotonic() - last_frame_time > self.reconnect_period_s:
                        self._release_camera()
                        last_frame_time = time.monotonic()
                    time.sleep(0.05)
                    continue

                last_frame_time = time.monotonic()
                self.camera_ok = True
                self.frames_read += 1
                if self.frames_read % self.process_every_n_frames != 0:
                    self._show_preview(frame, self._latest_detection_copy())
                    continue

                self._process_frame(frame)
            except Exception as error:
                self.model_ok = self.recognizer is not None
                self.camera_ok = False
                self.state = "FAULT" if self.recognizer is None else "IDLE"
                self.detail = (
                    f"Vision loop error: {type(error).__name__}: {error}"
                )
                self.get_logger().warning(self.detail)
                self._release_camera()
                time.sleep(self.reconnect_period_s)

    def _process_frame(self, frame) -> None:
        with self.recognition_lock:
            person_name, confidence, bbox, is_unknown, margin = (
                self.recognizer.recognize_face(frame)
            )
            raw_person_name = person_name
            raw_confidence = confidence
            raw_is_unknown = is_unknown
            if self.smoothing_enabled:
                person_name, confidence, is_unknown = (
                    self.recognizer.smooth_prediction(
                        person_name,
                        confidence,
                        is_unknown,
                    )
                )
                person_name, confidence, is_unknown = (
                    self.recognizer.stabilize_identity(
                        person_name,
                        confidence,
                        is_unknown,
                        margin,
                    )
                )

        self.frames_processed += 1
        threshold = float(getattr(self.recognizer, "confidence_threshold", 0.0))
        detection = self._make_detection_snapshot(
            person_name,
            confidence,
            bbox,
            is_unknown,
            threshold,
        )
        with self.lock:
            detection.sequence = self.latest_detection.sequence + 1
            self.latest_detection = detection
            if detection.face_detected:
                self.detections_seen += 1
            self.latest_raw_person_name = raw_person_name
            self.latest_raw_confidence = float(raw_confidence)
            self.latest_raw_is_unknown = bool(raw_is_unknown)
            self.latest_margin = float(margin)
            if not self.busy and self.state != "FAULT":
                self.state = "IDLE"
                self.detail = detection.detail
        self._sync_recognizer_stats(detection)
        self._publish_detection(detection)
        self._show_preview(frame, detection)

    def _make_detection_snapshot(
        self,
        person_name,
        confidence,
        bbox,
        is_unknown,
        threshold: float,
    ) -> DetectionSnapshot:
        if bbox is None or person_name is None:
            return DetectionSnapshot(
                person_name="NO_FACE",
                confidence=0.0,
                threshold=threshold,
                detail="No face detected.",
            )

        x1, y1, x2, y2 = [int(value) for value in bbox]
        name = "UNKNOWN" if is_unknown else self.normalize_identity(person_name)
        return DetectionSnapshot(
            face_detected=True,
            person_name=name,
            is_unknown=bool(is_unknown),
            confidence=float(confidence),
            threshold=threshold,
            bbox_x1=x1,
            bbox_y1=y1,
            bbox_x2=x2,
            bbox_y2=y2,
            bbox_width=max(0, x2 - x1),
            bbox_height=max(0, y2 - y1),
            detail=f"Detected {name} with confidence {float(confidence):.2f}.",
        )

    def _publish_detection(self, detection: DetectionSnapshot) -> None:
        msg = VisionDetection()
        msg.stamp = self.get_clock().now().to_msg()
        msg.frame_id = "camera_frame"
        msg.face_detected = detection.face_detected
        msg.person_name = detection.person_name
        msg.is_unknown = detection.is_unknown
        msg.confidence = float(detection.confidence)
        msg.threshold = float(detection.threshold)
        msg.bbox_x1 = int(detection.bbox_x1)
        msg.bbox_y1 = int(detection.bbox_y1)
        msg.bbox_x2 = int(detection.bbox_x2)
        msg.bbox_y2 = int(detection.bbox_y2)
        msg.bbox_width = int(detection.bbox_width)
        msg.bbox_height = int(detection.bbox_height)
        msg.detail = detection.detail
        self.detection_pub.publish(msg)

    def _show_preview(self, frame, detection: DetectionSnapshot) -> None:
        if (
            not self.show_preview
            and not self.publish_debug_image
        ) or self.realtime_module is None:
            return

        try:
            cv2 = self.realtime_module.cv2
            display_frame, scale_x, scale_y, crop_x, crop_y = (
                self._make_preview_frame(frame)
            )
            bbox = None
            if detection.face_detected:
                bbox = [
                    int((detection.bbox_x1 - crop_x) * scale_x),
                    int((detection.bbox_y1 - crop_y) * scale_y),
                    int((detection.bbox_x2 - crop_x) * scale_x),
                    int((detection.bbox_y2 - crop_y) * scale_y),
                ]

            display_frame = self.recognizer.draw_predictions(
                display_frame,
                detection.person_name,
                detection.confidence,
                bbox,
                detection.is_unknown,
            )
            with self.lock:
                raw_person_name = self.latest_raw_person_name
                raw_confidence = self.latest_raw_confidence
                raw_is_unknown = self.latest_raw_is_unknown
                frame_count = self.frames_read
                stream_mode = self._preview_stream_mode(frame)

            display_frame = self.recognizer.draw_info_panel(
                display_frame,
                frame_count,
                self.smoothing_enabled,
                raw_person_name,
                raw_confidence,
                detection.person_name,
                detection.confidence,
                raw_is_unknown,
                detection.is_unknown,
                stream_mode,
            )
            self._publish_debug_image(display_frame)
            if self.show_preview and self.display_available:
                cv2.imshow(self.preview_window_name, display_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    self.show_preview = False
                    cv2.destroyWindow(self.preview_window_name)
            elif self.show_preview and not self.preview_display_warning_emitted:
                self.preview_display_warning_emitted = True
                self.get_logger().warning(
                    "WSL display is not available; use the Windows vision "
                    "preview launched by the GUI."
                )
        except Exception as error:
            self.show_preview = False
            self.get_logger().warning(
                f"Vision preview disabled: {type(error).__name__}: {error}"
            )

    def _publish_debug_image(self, display_frame) -> None:
        if not self.publish_debug_image:
            return
        cv2 = self.realtime_module.cv2
        quality = max(1, min(100, self.debug_image_quality))
        ok, encoded = cv2.imencode(
            ".jpg",
            display_frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), quality],
        )
        if not ok:
            return

        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "camera_frame"
        msg.format = "jpeg"
        msg.data = encoded.tobytes()
        self.debug_image_pub.publish(msg)

    def _make_preview_frame(self, frame):
        cv2 = self.realtime_module.cv2
        frame_h, frame_w = frame.shape[:2]
        target_w = max(1, self.preview_width)
        target_h = max(1, self.preview_height)

        crop_size = min(frame_w, frame_h)
        crop_x = (frame_w - crop_size) // 2
        crop_y = (frame_h - crop_size) // 2
        square_frame = frame[crop_y:crop_y + crop_size, crop_x:crop_x + crop_size]
        display_frame = cv2.resize(square_frame, (target_w, target_h))
        return (
            display_frame,
            target_w / crop_size,
            target_h / crop_size,
            crop_x,
            crop_y,
        )

    def _preview_stream_mode(self, frame) -> str:
        frame_h, frame_w = frame.shape[:2]
        return (
            f"decoded {frame_w}x{frame_h} "
            f"(server target {self.camera_width}x{self.camera_height} "
            f"@ {self.camera_framerate} fps)"
        )

    def _sync_recognizer_stats(self, detection: DetectionSnapshot) -> None:
        stats = getattr(self.recognizer, "processing_stats", None)
        if not isinstance(stats, dict):
            return
        stats["total_frames_processed"] = self.frames_processed
        stats["total_detections_published"] = self.detections_seen
        if detection.face_detected and detection.is_unknown:
            stats["total_unknowns_detected"] = (
                int(stats.get("total_unknowns_detected", 0)) + 1
            )

    def publish_status(self) -> None:
        with self.lock:
            latest = self.latest_detection
            msg = VisionStatus()
            msg.stamp = self.get_clock().now().to_msg()
            msg.state = self.state
            msg.detail = self.detail
            msg.camera_ok = bool(self.camera_ok)
            msg.model_ok = bool(self.model_ok)
            msg.busy = bool(self.busy)
            msg.active_context = self.active_context
            msg.expected_identity = self.expected_identity
            msg.last_identity = latest.person_name
            msg.last_confidence = float(latest.confidence)
            msg.face_detected = bool(latest.face_detected)
        self.status_pub.publish(msg)

    def goal_callback(self, goal_request) -> GoalResponse:
        expected = self.normalize_identity(goal_request.expected_identity)
        if not expected:
            self.get_logger().warning("Rejected vision goal with empty expected_identity.")
            return GoalResponse.REJECT
        with self.lock:
            if self.busy:
                self.get_logger().warning("Rejected vision goal while busy.")
                return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def cancel_callback(self, _goal_handle) -> CancelResponse:
        return CancelResponse.ACCEPT

    def execute_verify_identity(self, goal_handle):
        request = goal_handle.request
        expected = self.normalize_identity(request.expected_identity)
        timeout_s = float(request.timeout_s) if request.timeout_s > 0 else self.default_timeout_s
        required_frames = (
            int(request.required_success_frames)
            if request.required_success_frames > 0
            else self.default_required_success_frames
        )
        min_confidence = (
            float(request.min_confidence)
            if request.min_confidence > 0
            else self.default_min_confidence
        )

        with self.lock:
            self.busy = True
            self.active_goal_handle = goal_handle
            self.active_context = str(request.context)
            self.expected_identity = expected
            self.state = "VERIFYING"
            self.detail = f"Verifying {expected}."
            start_sequence = self.latest_detection.sequence
            start_frames = self.frames_processed
            start_detections = self.detections_seen

        self._reset_temporal_tracking()

        deadline = time.monotonic() + timeout_s
        success_streak = 0
        matched_identity = ""
        matched_confidence = 0.0
        failure_reason = "Timed out before identity was verified."
        last_sequence = start_sequence

        try:
            while rclpy.ok() and time.monotonic() < deadline:
                if goal_handle.is_cancel_requested:
                    failure_reason = "Verification cancelled."
                    result = self._make_result(
                        False,
                        matched_identity,
                        matched_confidence,
                        failure_reason,
                        start_frames,
                        start_detections,
                    )
                    goal_handle.canceled()
                    return result

                detection = self._latest_detection_copy()
                if detection.sequence != last_sequence:
                    last_sequence = detection.sequence
                    if self._is_expected_match(
                        detection,
                        expected,
                        min_confidence,
                    ):
                        success_streak += 1
                        matched_identity = detection.person_name
                        matched_confidence = detection.confidence
                        failure_reason = ""
                    else:
                        success_streak = 0
                        failure_reason = self._failure_from_detection(
                            detection,
                            expected,
                            min_confidence,
                        )

                remaining_s = max(0.0, deadline - time.monotonic())
                feedback = VerifyIdentity.Feedback()
                feedback.state = (
                    "MATCHING"
                    if success_streak > 0
                    else "SEARCHING"
                )
                feedback.face_detected = detection.face_detected
                feedback.current_identity = detection.person_name
                feedback.current_confidence = float(detection.confidence)
                feedback.remaining_s = float(remaining_s)
                goal_handle.publish_feedback(feedback)

                with self.lock:
                    self.detail = (
                        f"Verifying {expected}: {success_streak}/"
                        f"{required_frames} matching frame(s)."
                    )

                if success_streak >= required_frames:
                    result = self._make_result(
                        True,
                        matched_identity,
                        matched_confidence,
                        "",
                        start_frames,
                        start_detections,
                    )
                    goal_handle.succeed()
                    return result

                time.sleep(0.05)

            result = self._make_result(
                False,
                matched_identity,
                matched_confidence,
                failure_reason,
                start_frames,
                start_detections,
            )
            goal_handle.succeed()
            return result
        finally:
            with self.lock:
                self.busy = False
                self.active_goal_handle = None
                self.active_context = ""
                self.expected_identity = ""
                if self.state == "VERIFYING":
                    self.state = "IDLE"
                if not self.detail:
                    self.detail = "Verification finished."

    def _make_result(
        self,
        verified: bool,
        matched_identity: str,
        confidence: float,
        failure_reason: str,
        start_frames: int,
        start_detections: int,
    ):
        result = VerifyIdentity.Result()
        result.verified = bool(verified)
        result.matched_identity = str(matched_identity)
        result.confidence = float(confidence)
        result.failure_reason = str(failure_reason)
        result.frames_processed = max(0, int(self.frames_processed - start_frames))
        result.detections_seen = max(0, int(self.detections_seen - start_detections))
        return result

    def _latest_detection_copy(self) -> DetectionSnapshot:
        with self.lock:
            return DetectionSnapshot(**self.latest_detection.__dict__)

    def _is_expected_match(
        self,
        detection: DetectionSnapshot,
        expected: str,
        min_confidence: float,
    ) -> bool:
        if not detection.face_detected or detection.is_unknown:
            return False
        return (
            self.normalize_identity(detection.person_name) == expected
            and detection.confidence >= min_confidence
        )

    def _failure_from_detection(
        self,
        detection: DetectionSnapshot,
        expected: str,
        min_confidence: float,
    ) -> str:
        if not detection.face_detected:
            return "No face detected."
        if detection.is_unknown:
            return "Face detected but identity is unknown."
        if detection.confidence < min_confidence:
            return (
                f"{detection.person_name} confidence {detection.confidence:.2f} "
                f"is below {min_confidence:.2f}."
            )
        return f"Expected {expected}, saw {detection.person_name}."

    def _reset_temporal_tracking(self) -> None:
        if self.recognizer is None:
            return
        with self.recognition_lock:
            history = getattr(self.recognizer, "prediction_history", None)
            if history is not None:
                history.clear()
            for attr, value in (
                ("locked_identity", None),
                ("pending_identity", None),
                ("pending_count", 0),
                ("switch_candidate", None),
                ("switch_count", 0),
                ("unknown_streak", 0),
            ):
                if hasattr(self.recognizer, attr):
                    setattr(self.recognizer, attr, value)

    def normalize_identity(self, identity: str) -> str:
        text = str(identity).strip()
        if not text:
            return ""
        return self.identity_map.get(text.lower(), text)

    def _release_camera(self) -> None:
        if self.camera is not None:
            try:
                self.camera.release()
            except Exception as error:
                self.get_logger().warning(f"Camera release failed: {error}")
            self.camera = None

    def _cancel_active_verification(self) -> None:
        with self.lock:
            goal_handle = self.active_goal_handle
        if goal_handle is None:
            return
        try:
            goal_handle.abort()
        except Exception as error:
            self.get_logger().warning(f"Vision goal abort failed: {error}")

    def destroy_node(self):
        self.running = False
        self._cancel_active_verification()
        self._release_camera()
        if self.camera_server is not None:
            try:
                self.camera_server.stop_server()
            except Exception as error:
                self.get_logger().warning(f"Camera server stop failed: {error}")
        if self.show_preview and self.realtime_module is not None:
            try:
                self.realtime_module.cv2.destroyWindow(self.preview_window_name)
            except Exception:
                pass
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VisionNode()
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
