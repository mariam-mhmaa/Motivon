#!/usr/bin/env python3

import shutil
import os
import signal
import subprocess
import threading
import time
from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, JointState
from std_msgs.msg import Bool, String, UInt32
from std_srvs.srv import Trigger


class EnResetPin:
    """Drive ESP32 EN low briefly, then release the GPIO back to input."""

    def __init__(self, bcm_pin: int, pulse_s: float, logger) -> None:
        self.bcm_pin = int(bcm_pin)
        self.pulse_s = float(pulse_s)
        self.logger = logger

    def pulse(self) -> None:
        errors = []
        for method in (
            self._pulse_with_lgpio,
            self._pulse_with_rpi_gpio,
            self._pulse_with_pinctrl,
            self._pulse_with_raspi_gpio,
        ):
            try:
                method()
                return
            except Exception as error:  # pragma: no cover - hardware dependent
                errors.append(f"{method.__name__}: {error}")
        raise RuntimeError("; ".join(errors))

    def _pulse_with_lgpio(self) -> None:
        import lgpio  # type: ignore

        handle = lgpio.gpiochip_open(0)
        try:
            lgpio.gpio_claim_output(handle, self.bcm_pin, 0)
            time.sleep(self.pulse_s)
            lgpio.gpio_free(handle, self.bcm_pin)
        finally:
            lgpio.gpiochip_close(handle)

    def _pulse_with_rpi_gpio(self) -> None:
        import RPi.GPIO as GPIO  # type: ignore

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.bcm_pin, GPIO.OUT, initial=GPIO.LOW)
        time.sleep(self.pulse_s)
        GPIO.setup(self.bcm_pin, GPIO.IN)

    def _pulse_with_pinctrl(self) -> None:
        if shutil.which("pinctrl") is None:
            raise RuntimeError("pinctrl command not found")
        subprocess.run(
            ["pinctrl", "set", str(self.bcm_pin), "op", "dl"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(self.pulse_s)
        subprocess.run(
            ["pinctrl", "set", str(self.bcm_pin), "ip"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    def _pulse_with_raspi_gpio(self) -> None:
        if shutil.which("raspi-gpio") is None:
            raise RuntimeError("raspi-gpio command not found")
        subprocess.run(
            ["raspi-gpio", "set", str(self.bcm_pin), "op", "dl"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(self.pulse_s)
        subprocess.run(
            ["raspi-gpio", "set", str(self.bcm_pin), "ip"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )


class BaseRecoveryNode(Node):
    """Monitor base telemetry and recover the ESP32/micro-ROS session."""

    def __init__(self) -> None:
        super().__init__("base_recovery_node")
        self.callback_group = ReentrantCallbackGroup()
        self.lock = threading.RLock()

        self.declare_parameter("hardware_reset_enabled", True)
        self.declare_parameter("hardware_reset_gpio_bcm", 26)
        self.declare_parameter("hardware_reset_pulse_s", 0.25)
        self.declare_parameter("software_reset_wait_s", 2.5)
        self.declare_parameter("hardware_reset_wait_s", 10.0)
        self.declare_parameter("restart_agent_during_recovery", True)
        self.declare_parameter("agent_udp_port", 8888)
        self.declare_parameter("agent_restart_wait_s", 0.8)
        self.declare_parameter("healthy_window_s", 0.5)
        self.declare_parameter("stale_timeout_s", 4.0)
        self.declare_parameter("lost_timeout_s", 8.0)
        self.declare_parameter("require_imu_data_for_health", False)
        self.declare_parameter("require_imu_ok_for_health", False)
        self.declare_parameter("stop_publish_s", 0.75)

        self.hardware_reset_enabled = bool(
            self.get_parameter("hardware_reset_enabled").value
        )
        self.reset_gpio_bcm = int(
            self.get_parameter("hardware_reset_gpio_bcm").value
        )
        self.reset_pulse_s = float(
            self.get_parameter("hardware_reset_pulse_s").value
        )
        self.software_reset_wait_s = float(
            self.get_parameter("software_reset_wait_s").value
        )
        self.hardware_reset_wait_s = float(
            self.get_parameter("hardware_reset_wait_s").value
        )
        self.restart_agent_during_recovery = bool(
            self.get_parameter("restart_agent_during_recovery").value
        )
        self.agent_udp_port = int(self.get_parameter("agent_udp_port").value)
        self.agent_restart_wait_s = float(
            self.get_parameter("agent_restart_wait_s").value
        )
        self.healthy_window_s = float(self.get_parameter("healthy_window_s").value)
        self.stale_timeout_s = float(self.get_parameter("stale_timeout_s").value)
        self.lost_timeout_s = float(self.get_parameter("lost_timeout_s").value)
        self.require_imu_data_for_health = bool(
            self.get_parameter("require_imu_data_for_health").value
        )
        self.require_imu_ok_for_health = bool(
            self.get_parameter("require_imu_ok_for_health").value
        )
        self.stop_publish_s = float(self.get_parameter("stop_publish_s").value)

        self.last_wheel_s: Optional[float] = None
        self.last_imu_s: Optional[float] = None
        self.last_imu_ok_s: Optional[float] = None
        self.last_heartbeat_s: Optional[float] = None
        self.last_heartbeat_value: Optional[int] = None
        self.imu_ok = False
        self.recovery_busy = False
        self.health_state = "WARMING_UP"
        self.health_detail = "Waiting for ESP32 telemetry."

        self.reset_pin = EnResetPin(
            self.reset_gpio_bcm,
            self.reset_pulse_s,
            self.get_logger(),
        )

        self.reset_pub = self.create_publisher(
            Bool, "/base/software_reset", 10
        )
        self.enable_pub = self.create_publisher(Bool, "/base/enable", 10)
        self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.health_pub = self.create_publisher(String, "/base/health", 10)
        self.health_detail_pub = self.create_publisher(
            String, "/base/health_detail", 10
        )

        self.create_subscription(
            JointState,
            "/base/wheel_states",
            self._on_wheel_state,
            qos_profile_sensor_data,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            Imu,
            "/imu/data_raw",
            self._on_imu,
            qos_profile_sensor_data,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            Bool,
            "/base/imu_ok",
            self._on_imu_ok,
            qos_profile_sensor_data,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            UInt32,
            "/base/heartbeat",
            self._on_heartbeat,
            qos_profile_sensor_data,
            callback_group=self.callback_group,
        )

        self.create_service(
            Trigger,
            "/base/recover",
            self.recover_callback,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/base/hardware_reset",
            self.hardware_reset_callback,
            callback_group=self.callback_group,
        )
        self.create_timer(
            0.25,
            self.publish_health,
            callback_group=self.callback_group,
        )
        self.get_logger().info(
            "Base recovery ready: /base/recover uses software reset first, "
            f"then GPIO{self.reset_gpio_bcm} EN reset if needed."
        )

    def now_s(self) -> float:
        return time.monotonic()

    def _on_wheel_state(self, _msg: JointState) -> None:
        with self.lock:
            self.last_wheel_s = self.now_s()

    def _on_imu(self, _msg: Imu) -> None:
        with self.lock:
            self.last_imu_s = self.now_s()

    def _on_imu_ok(self, msg: Bool) -> None:
        with self.lock:
            self.last_imu_ok_s = self.now_s()
            self.imu_ok = bool(msg.data)

    def _on_heartbeat(self, msg: UInt32) -> None:
        with self.lock:
            self.last_heartbeat_s = self.now_s()
            self.last_heartbeat_value = int(msg.data)

    def telemetry_ages_locked(self) -> dict:
        now = self.now_s()
        return {
            "wheel": self._age(now, self.last_wheel_s),
            "imu": self._age(now, self.last_imu_s),
            "imu_ok": self._age(now, self.last_imu_ok_s),
            "heartbeat": self._age(now, self.last_heartbeat_s),
        }

    @staticmethod
    def _age(now: float, stamp: Optional[float]) -> float:
        if stamp is None:
            return float("inf")
        return max(0.0, now - stamp)

    def raw_health_snapshot_locked(self) -> tuple:
        ages = self.telemetry_ages_locked()
        required_ages = {
            "wheel": ages["wheel"],
            "heartbeat": ages["heartbeat"],
        }
        if self.require_imu_data_for_health:
            required_ages["imu"] = ages["imu"]
        if self.require_imu_ok_for_health:
            required_ages["imu_ok"] = ages["imu_ok"]

        if any(age == float("inf") for age in required_ages.values()):
            missing = [
                name
                for name, age in required_ages.items()
                if age == float("inf")
            ]
            return (
                "WARMING_UP",
                "Waiting for required base telemetry: "
                + ", ".join(missing)
                + ".",
            )
        worst_age = max(required_ages.values())
        if worst_age >= self.lost_timeout_s:
            return (
                "LOST",
                f"Base telemetry lost; worst stream age {worst_age:.2f} s.",
            )
        if worst_age >= self.stale_timeout_s:
            return (
                "STALE",
                f"Base telemetry stale; worst stream age {worst_age:.2f} s.",
            )
        if self.require_imu_ok_for_health and not self.imu_ok:
            return "IMU_NOT_OK", "ESP32 reports IMU is not healthy."
        optional_notes = []
        if ages["imu"] == float("inf"):
            optional_notes.append("IMU stream not required/not seen")
        elif ages["imu"] >= self.stale_timeout_s:
            optional_notes.append(f"IMU age {ages['imu']:.2f} s")
        if ages["imu_ok"] == float("inf"):
            optional_notes.append("imu_ok not required/not seen")
        elif not self.imu_ok:
            optional_notes.append("imu_ok is false")
        if optional_notes:
            return (
                "HEALTHY",
                "Base drive telemetry is healthy; "
                + "; ".join(optional_notes)
                + ".",
            )
        return "HEALTHY", "Base drive telemetry is healthy."

    def health_snapshot(self) -> tuple:
        with self.lock:
            if self.recovery_busy:
                return "RECOVERING", "Base recovery is running."
            return self.raw_health_snapshot_locked()

    def telemetry_ready(self) -> bool:
        with self.lock:
            state, _detail = self.raw_health_snapshot_locked()
        return state == "HEALTHY"

    def publish_health(self) -> None:
        state, detail = self.health_snapshot()
        with self.lock:
            self.health_state = state
            self.health_detail = detail
        msg = String()
        msg.data = state
        self.health_pub.publish(msg)
        detail_msg = String()
        detail_msg.data = detail
        self.health_detail_pub.publish(detail_msg)

    def stop_base(self) -> None:
        disabled = Bool()
        disabled.data = False
        stop = Twist()
        deadline = self.now_s() + self.stop_publish_s
        while self.now_s() < deadline:
            self.cmd_vel_pub.publish(stop)
            self.enable_pub.publish(disabled)
            time.sleep(0.05)

    def publish_software_reset(self) -> bool:
        if self.reset_pub.get_subscription_count() < 1:
            self.get_logger().warning(
                "Skipping ROS software reset: /base/software_reset has no ESP subscriber."
            )
            return False
        msg = Bool()
        msg.data = True
        for _ in range(10):
            self.reset_pub.publish(msg)
            time.sleep(0.05)
        return True

    def clear_telemetry_window(self) -> None:
        with self.lock:
            self.last_wheel_s = None
            self.last_imu_s = None
            self.last_imu_ok_s = None
            self.last_heartbeat_s = None
            self.last_heartbeat_value = None
            self.imu_ok = False

    def wait_for_healthy_telemetry(self, timeout_s: float) -> bool:
        deadline = self.now_s() + timeout_s
        healthy_since: Optional[float] = None
        while self.now_s() < deadline:
            if self.telemetry_ready():
                if healthy_since is None:
                    healthy_since = self.now_s()
                if self.now_s() - healthy_since >= self.healthy_window_s:
                    return True
            else:
                healthy_since = None
            time.sleep(0.10)
        return False

    def hardware_reset_esp(self) -> None:
        if not self.hardware_reset_enabled:
            raise RuntimeError("Hardware reset is disabled by parameter.")
        self.get_logger().warning(
            f"Pulling ESP32 EN low using BCM GPIO{self.reset_gpio_bcm}."
        )
        self.reset_pin.pulse()

    def restart_micro_ros_agent(self) -> None:
        if not self.restart_agent_during_recovery:
            return
        pattern = (
            rf"micro_ros_agent.*udp4.*--port[[:space:]]+{self.agent_udp_port}"
        )
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except FileNotFoundError:
            self.get_logger().warning("pgrep is unavailable; agent restart skipped.")
            return

        pids = []
        for token in result.stdout.split():
            try:
                pid = int(token)
            except ValueError:
                continue
            if pid != os.getpid():
                pids.append(pid)

        if not pids:
            self.get_logger().warning(
                "No running micro-ROS agent process matched the recovery pattern."
            )
            return

        self.get_logger().warning(
            "Restarting micro-ROS agent through launch respawn: "
            + ", ".join(str(pid) for pid in pids)
        )
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
        time.sleep(self.agent_restart_wait_s)

    def hardware_reset_callback(self, _request, response):
        with self.lock:
            if self.recovery_busy:
                response.success = False
                response.message = "Base recovery is already running."
                return response
            self.recovery_busy = True
        try:
            self.stop_base()
            self.clear_telemetry_window()
            self.hardware_reset_esp()
            response.success = True
            response.message = (
                f"GPIO EN reset pulse sent on BCM GPIO{self.reset_gpio_bcm}. "
                "Wait for esp32_base_node and base telemetry to return."
            )
            return response
        except Exception as error:
            response.success = False
            response.message = f"GPIO EN reset failed: {error}"
            self.get_logger().error(response.message)
            return response
        finally:
            with self.lock:
                self.recovery_busy = False
            self.publish_health()

    def recover_callback(self, _request, response):
        return self._run_recovery(response, force_hardware=False)

    def _run_recovery(self, response, force_hardware: bool):
        with self.lock:
            if self.recovery_busy:
                response.success = False
                response.message = "Base recovery is already running."
                return response
            self.recovery_busy = True
        try:
            self.stop_base()
            self.clear_telemetry_window()

            if not force_hardware and self.publish_software_reset():
                self.get_logger().info("Waiting after ROS ESP32 software reset.")
                if self.wait_for_healthy_telemetry(self.software_reset_wait_s):
                    response.success = True
                    response.message = "Base recovered using ROS software reset."
                    return response

            self.stop_base()
            self.restart_micro_ros_agent()
            self.clear_telemetry_window()
            self.hardware_reset_esp()
            if self.wait_for_healthy_telemetry(self.hardware_reset_wait_s):
                response.success = True
                response.message = (
                    "Base recovered using Raspberry Pi GPIO EN reset."
                )
                return response

            with self.lock:
                state, detail = self.raw_health_snapshot_locked()
                ages = self.telemetry_ages_locked()
                heartbeat = self.last_heartbeat_value
            age_text = ", ".join(
                f"{name}=never" if age == float("inf") else f"{name}={age:.2f}s"
                for name, age in ages.items()
            )
            heartbeat_text = "never" if heartbeat is None else str(heartbeat)
            response.success = False
            response.message = (
                f"Base recovery failed; health={state}. {detail} "
                f"Ages: {age_text}. Last heartbeat: {heartbeat_text}. "
                "Check whether the ESP actually rebooted, whether the launch "
                "started micro_ros_agent, and whether the configured GPIO is "
                "BCM pin number not physical header number."
            )
            return response
        except Exception as error:
            response.success = False
            response.message = f"Base recovery failed: {error}"
            self.get_logger().error(response.message)
            return response
        finally:
            with self.lock:
                self.recovery_busy = False
            self.publish_health()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = BaseRecoveryNode()
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
