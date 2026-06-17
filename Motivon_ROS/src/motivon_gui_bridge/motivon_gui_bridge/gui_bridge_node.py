#!/usr/bin/env python3

import asyncio
import threading
import time
from typing import Any, Dict, List

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import rclpy
from geometry_msgs.msg import Twist
from motivon_interfaces.msg import (
    MissionEvent,
    MissionStatus,
    NavigationStatus,
    ObstacleState,
    VisionDetection,
    VisionStatus,
)
from motivon_interfaces.srv import StartMission
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Bool, String, UInt32
from std_srvs.srv import Trigger
import uvicorn


class GuiBridgeNode(Node):
    """Expose a normal network API for the Windows GUI."""

    def __init__(self) -> None:
        super().__init__("gui_bridge_node")
        self.callback_group = ReentrantCallbackGroup()
        self.lock = threading.RLock()

        self.declare_parameter("host", "0.0.0.0")
        self.declare_parameter("port", 8000)
        self.declare_parameter("initial_mode", "AUTO")
        self.declare_parameter("status_publish_period_s", 0.20)

        self.host = str(self.get_parameter("host").value)
        self.port = int(self.get_parameter("port").value)
        self.status_publish_period_s = float(
            self.get_parameter("status_publish_period_s").value
        )

        self.status_cache: Dict[str, Any] = {
            "mission": {},
            "navigation": {},
            "obstacle": {},
            "vision": {},
            "vision_detection": {},
            "cmd_vel_gate": "",
            "lid": "",
            "base_heartbeat": None,
            "last_event": {},
            "bridge_time_s": time.time(),
        }

        self.start_client = self.create_client(
            StartMission, "/mission/start", callback_group=self.callback_group
        )
        self.trigger_clients = {
            "cancel": self.create_client(
                Trigger, "/mission/cancel", callback_group=self.callback_group
            ),
            "confirm_manager_verified": self.create_client(
                Trigger,
                "/mission/confirm_manager_verified",
                callback_group=self.callback_group,
            ),
            "confirm_manager_loaded": self.create_client(
                Trigger,
                "/mission/confirm_manager_loaded",
                callback_group=self.callback_group,
            ),
            "confirm_user_verified": self.create_client(
                Trigger,
                "/mission/confirm_user_verified",
                callback_group=self.callback_group,
            ),
            "confirm_user_received": self.create_client(
                Trigger,
                "/mission/confirm_user_received",
                callback_group=self.callback_group,
            ),
        }

        self.mode_pub = self.create_publisher(String, "/system/mode", 10)
        self.manual_pub = self.create_publisher(Twist, "/manual/cmd_vel", 10)
        self.software_reset_pub = self.create_publisher(
            Bool, "/base/software_reset", 10
        )

        self.create_subscription(
            MissionStatus,
            "/mission/status",
            self.on_mission_status,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            MissionEvent,
            "/mission/events",
            self.on_mission_event,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            NavigationStatus,
            "/navigation/status",
            self.on_navigation_status,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            ObstacleState,
            "/obstacle/state",
            self.on_obstacle_state,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            VisionStatus,
            "/vision/status",
            self.on_vision_status,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            VisionDetection,
            "/vision/detection",
            self.on_vision_detection,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            String,
            "/cmd_vel_gate/status",
            self.on_gate_status,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            String,
            "/lid/status",
            self.on_lid_status,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            UInt32,
            "/base/heartbeat",
            self.on_base_heartbeat,
            qos_profile_sensor_data,
            callback_group=self.callback_group,
        )

        self.app = self._create_app()
        self.publish_mode(str(self.get_parameter("initial_mode").value))
        self.get_logger().info(
            f"GUI bridge ready on {self.host}:{self.port}."
        )

    def _create_app(self) -> FastAPI:
        app = FastAPI(title="Motivon GUI Bridge")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/api/status")
        async def status():
            return self.snapshot()

        @app.post("/api/mission/start")
        async def start_mission(request: Request):
            payload = await request.json()
            return await asyncio.to_thread(self.start_mission, payload)

        @app.post("/api/mission/cancel")
        async def cancel_mission():
            return await asyncio.to_thread(self.call_trigger, "cancel")

        @app.post("/api/mission/confirm-manager-verified")
        async def confirm_manager_verified():
            return await asyncio.to_thread(
                self.call_trigger, "confirm_manager_verified"
            )

        @app.post("/api/mission/confirm-manager-loaded")
        async def confirm_manager_loaded():
            return await asyncio.to_thread(
                self.call_trigger, "confirm_manager_loaded"
            )

        @app.post("/api/mission/confirm-user-verified")
        async def confirm_user_verified():
            return await asyncio.to_thread(
                self.call_trigger, "confirm_user_verified"
            )

        @app.post("/api/mission/confirm-user-received")
        async def confirm_user_received():
            return await asyncio.to_thread(
                self.call_trigger, "confirm_user_received"
            )

        @app.post("/api/mode")
        async def mode(request: Request):
            payload = await request.json()
            mode_value = str(payload.get("mode", "AUTO"))
            self.publish_mode(mode_value)
            return {"success": True, "message": f"Mode set to {mode_value}."}

        @app.post("/api/manual-cmd")
        async def manual_cmd(request: Request):
            payload = await request.json()
            self.publish_manual_command(payload)
            return {"success": True, "message": "Manual command published."}

        @app.post("/api/base/software-reset")
        async def software_reset():
            self.publish_software_reset()
            return {
                "success": True,
                "message": "ESP32 software reset command published.",
            }

        @app.websocket("/ws/status")
        async def websocket_status(websocket: WebSocket):
            await websocket.accept()
            try:
                while True:
                    await websocket.send_json(self.snapshot())
                    await asyncio.sleep(self.status_publish_period_s)
            except WebSocketDisconnect:
                return

        return app

    def start_mission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        requests = payload.get("requests")
        if requests is None:
            requests = self._requests_from_arrays(payload)
        if not isinstance(requests, list) or not requests:
            return {"success": False, "message": "No requests supplied."}

        service_request = StartMission.Request()
        for item in requests:
            service_request.request_ids.append(
                str(item.get("request_id", item.get("id", "")))
            )
            service_request.users.append(
                str(item.get("user_name", item.get("user", "")))
            )
            service_request.items.append(
                str(item.get("object_requested", item.get("item", "")))
            )
            service_request.stations.append(
                str(item.get("target_station", item.get("station", "")))
            )

        if not self.start_client.wait_for_service(timeout_sec=5.0):
            return {
                "success": False,
                "message": "/mission/start service is not available.",
            }
        future = self.start_client.call_async(service_request)
        response = self._wait_for_future(future, 10.0)
        return self._service_response_dict(response)

    @staticmethod
    def _requests_from_arrays(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        ids = payload.get("request_ids", [])
        users = payload.get("users", [])
        items = payload.get("items", [])
        stations = payload.get("stations", [])
        count = min(len(ids), len(users), len(items), len(stations))
        return [
            {
                "request_id": ids[index],
                "user": users[index],
                "item": items[index],
                "station": stations[index],
            }
            for index in range(count)
        ]

    def call_trigger(self, name: str) -> Dict[str, Any]:
        client = self.trigger_clients[name]
        if not client.wait_for_service(timeout_sec=5.0):
            return {
                "success": False,
                "message": f"Mission service {name} is not available.",
            }
        future = client.call_async(Trigger.Request())
        response = self._wait_for_future(future, 10.0)
        return self._service_response_dict(response)

    @staticmethod
    def _service_response_dict(response) -> Dict[str, Any]:
        if response is None:
            return {"success": False, "message": "Service call timed out."}
        return {
            "success": bool(response.success),
            "message": str(response.message),
        }

    @staticmethod
    def _wait_for_future(future, timeout_s: float):
        deadline = time.monotonic() + timeout_s
        while not future.done():
            if time.monotonic() > deadline:
                return None
            time.sleep(0.02)
        return future.result()

    def publish_mode(self, mode_value: str) -> None:
        msg = String()
        msg.data = str(mode_value).strip().upper() or "AUTO"
        self.mode_pub.publish(msg)

    def publish_manual_command(self, payload: Dict[str, Any]) -> None:
        msg = Twist()
        msg.linear.x = float(payload.get("linear_x", payload.get("x", 0.0)))
        msg.linear.y = float(payload.get("linear_y", payload.get("y", 0.0)))
        msg.angular.z = float(
            payload.get("angular_z", payload.get("z", payload.get("yaw", 0.0)))
        )
        self.manual_pub.publish(msg)

    def publish_software_reset(self) -> None:
        msg = Bool()
        msg.data = True
        for _ in range(5):
            self.software_reset_pub.publish(msg)
            time.sleep(0.05)

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            data = dict(self.status_cache)
            data["bridge_time_s"] = time.time()
            return data

    def on_mission_status(self, msg: MissionStatus) -> None:
        with self.lock:
            self.status_cache["mission"] = {
                "state": msg.state,
                "detail": msg.detail,
                "current_target": msg.current_target,
                "current_station": msg.current_station,
                "active_request_id": msg.active_request_id,
                "active_user": msg.active_user,
                "active_item": msg.active_item,
                "completed_count": msg.completed_count,
                "total_count": msg.total_count,
                "can_confirm_manager_verified": msg.can_confirm_manager_verified,
                "can_confirm_manager_loaded": msg.can_confirm_manager_loaded,
                "can_confirm_user_verified": msg.can_confirm_user_verified,
                "can_confirm_user_received": msg.can_confirm_user_received,
                "mission_active": msg.mission_active,
                "safety_paused": msg.safety_paused,
                "faulted": msg.faulted,
            }

    def on_mission_event(self, msg: MissionEvent) -> None:
        with self.lock:
            self.status_cache["last_event"] = {
                "event_type": msg.event_type,
                "request_id": msg.request_id,
                "station": msg.station,
                "user": msg.user,
                "item": msg.item,
                "state": msg.state,
                "message": msg.message,
            }

    def on_navigation_status(self, msg: NavigationStatus) -> None:
        with self.lock:
            self.status_cache["navigation"] = {
                "state": msg.state,
                "target_name": msg.target_name,
                "active_waypoint": msg.active_waypoint,
                "distance_remaining_m": msg.distance_remaining_m,
                "home_set": msg.home_set,
                "detail": msg.detail,
            }

    def on_obstacle_state(self, msg: ObstacleState) -> None:
        with self.lock:
            self.status_cache["obstacle"] = {
                "state": msg.state,
                "blocked": msg.blocked,
                "static_obstacle": msg.static_obstacle,
                "blocked_direction": msg.blocked_direction,
                "detail": msg.detail,
            }

    def on_vision_status(self, msg: VisionStatus) -> None:
        with self.lock:
            self.status_cache["vision"] = {
                "state": msg.state,
                "detail": msg.detail,
                "camera_ok": msg.camera_ok,
                "model_ok": msg.model_ok,
                "busy": msg.busy,
                "active_context": msg.active_context,
                "expected_identity": msg.expected_identity,
                "last_identity": msg.last_identity,
                "last_confidence": msg.last_confidence,
                "face_detected": msg.face_detected,
            }

    def on_vision_detection(self, msg: VisionDetection) -> None:
        with self.lock:
            self.status_cache["vision_detection"] = {
                "frame_id": msg.frame_id,
                "face_detected": msg.face_detected,
                "person_name": msg.person_name,
                "is_unknown": msg.is_unknown,
                "confidence": msg.confidence,
                "threshold": msg.threshold,
                "bbox": {
                    "x1": msg.bbox_x1,
                    "y1": msg.bbox_y1,
                    "x2": msg.bbox_x2,
                    "y2": msg.bbox_y2,
                    "width": msg.bbox_width,
                    "height": msg.bbox_height,
                },
                "detail": msg.detail,
            }

    def on_gate_status(self, msg: String) -> None:
        with self.lock:
            self.status_cache["cmd_vel_gate"] = msg.data

    def on_lid_status(self, msg: String) -> None:
        with self.lock:
            self.status_cache["lid"] = msg.data

    def on_base_heartbeat(self, msg: UInt32) -> None:
        with self.lock:
            self.status_cache["base_heartbeat"] = int(msg.data)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GuiBridgeNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    executor_thread = threading.Thread(target=executor.spin, daemon=True)
    executor_thread.start()
    try:
        uvicorn.run(node.app, host=node.host, port=node.port, log_level="info")
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
