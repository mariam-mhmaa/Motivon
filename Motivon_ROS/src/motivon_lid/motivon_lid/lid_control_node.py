#!/usr/bin/env python3

import json
import threading
import time
from typing import Optional

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

try:
    import lgpio
except ImportError:  # pragma: no cover - only available on Raspberry Pi
    lgpio = None


class LidControlNode(Node):
    """Control the box lid motor using the tested Raspberry Pi GPIO wiring."""

    def __init__(self):
        super().__init__("lid_control_node")
        self.callback_group = ReentrantCallbackGroup()

        self.declare_parameter("gpio_chip", 4)
        self.declare_parameter("dir1_pin", 5)
        self.declare_parameter("dir2_pin", 6)
        self.declare_parameter("pwm_pin", 12)
        self.declare_parameter("enc_a_pin", 16)
        self.declare_parameter("enc_b_pin", 20)
        self.declare_parameter("pwm_frequency_hz", 1000)
        self.declare_parameter("pwm_duty_percent", 40.0)
        self.declare_parameter("open_target_ticks", 40000)
        self.declare_parameter("close_target_ticks", 40000)
        self.declare_parameter("move_timeout_s", 10.0)
        self.declare_parameter("encoder_poll_period_s", 0.001)
        self.declare_parameter("status_period_s", 0.10)

        self.gpio_chip = int(self.get_parameter("gpio_chip").value)
        self.dir1_pin = int(self.get_parameter("dir1_pin").value)
        self.dir2_pin = int(self.get_parameter("dir2_pin").value)
        self.pwm_pin = int(self.get_parameter("pwm_pin").value)
        self.enc_a_pin = int(self.get_parameter("enc_a_pin").value)
        self.enc_b_pin = int(self.get_parameter("enc_b_pin").value)
        self.pwm_frequency_hz = int(
            self.get_parameter("pwm_frequency_hz").value
        )
        self.pwm_duty_percent = float(
            self.get_parameter("pwm_duty_percent").value
        )
        self.open_target_ticks = int(
            self.get_parameter("open_target_ticks").value
        )
        self.close_target_ticks = int(
            self.get_parameter("close_target_ticks").value
        )
        self.move_timeout_s = float(
            self.get_parameter("move_timeout_s").value
        )
        self.encoder_poll_period_s = float(
            self.get_parameter("encoder_poll_period_s").value
        )
        status_period_s = float(self.get_parameter("status_period_s").value)

        self.gpio_handle: Optional[int] = None
        self.ticks = 0
        self.last_a = 0
        self.state = "STARTING"
        self.last_result = ""
        self.active_command = ""
        self.stop_requested = False
        self.lock = threading.RLock()

        self.status_pub = self.create_publisher(String, "/lid/status", 10)
        self.create_service(
            Trigger,
            "/lid/open",
            self.open_callback,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/lid/close",
            self.close_callback,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/lid/stop",
            self.stop_callback,
            callback_group=self.callback_group,
        )
        self.create_timer(
            status_period_s,
            self.publish_status,
            callback_group=self.callback_group,
        )

        self.setup_gpio()
        self.stop_motor()
        self.reset_encoder()
        self.state = "IDLE"
        self.get_logger().info(
            "Lid control ready: dir=(%d,%d), pwm=%d, enc=(%d,%d), "
            "open=%d ticks, close=%d ticks."
            % (
                self.dir1_pin,
                self.dir2_pin,
                self.pwm_pin,
                self.enc_a_pin,
                self.enc_b_pin,
                self.open_target_ticks,
                self.close_target_ticks,
            )
        )

    def setup_gpio(self) -> None:
        if lgpio is None:
            raise RuntimeError(
                "lgpio is not installed. Run lid_control_node on the Raspberry Pi."
            )
        self.gpio_handle = lgpio.gpiochip_open(self.gpio_chip)
        lgpio.gpio_claim_output(self.gpio_handle, self.dir1_pin, 0)
        lgpio.gpio_claim_output(self.gpio_handle, self.dir2_pin, 0)
        lgpio.gpio_claim_output(self.gpio_handle, self.pwm_pin, 0)
        lgpio.gpio_claim_input(self.gpio_handle, self.enc_a_pin)
        lgpio.gpio_claim_input(self.gpio_handle, self.enc_b_pin)

    def stop_motor(self) -> None:
        if self.gpio_handle is None:
            return
        lgpio.tx_pwm(self.gpio_handle, self.pwm_pin, self.pwm_frequency_hz, 0)
        lgpio.gpio_write(self.gpio_handle, self.dir1_pin, 0)
        lgpio.gpio_write(self.gpio_handle, self.dir2_pin, 0)

    def motor_open(self) -> None:
        lgpio.gpio_write(self.gpio_handle, self.dir1_pin, 0)
        lgpio.gpio_write(self.gpio_handle, self.dir2_pin, 1)
        lgpio.tx_pwm(
            self.gpio_handle,
            self.pwm_pin,
            self.pwm_frequency_hz,
            self.pwm_duty_percent,
        )

    def motor_close(self) -> None:
        lgpio.gpio_write(self.gpio_handle, self.dir1_pin, 1)
        lgpio.gpio_write(self.gpio_handle, self.dir2_pin, 0)
        lgpio.tx_pwm(
            self.gpio_handle,
            self.pwm_pin,
            self.pwm_frequency_hz,
            self.pwm_duty_percent,
        )

    def reset_encoder(self) -> None:
        self.ticks = 0
        self.last_a = lgpio.gpio_read(self.gpio_handle, self.enc_a_pin)

    def update_encoder(self) -> None:
        a_value = lgpio.gpio_read(self.gpio_handle, self.enc_a_pin)
        b_value = lgpio.gpio_read(self.gpio_handle, self.enc_b_pin)
        if a_value != self.last_a:
            if b_value != a_value:
                self.ticks += 1
            else:
                self.ticks -= 1
        self.last_a = a_value

    def run_motion(self, command: str, target_ticks: int) -> tuple[bool, str]:
        with self.lock:
            if self.state in ("OPENING", "CLOSING"):
                return False, f"Lid already busy: {self.state}."
            self.stop_requested = False
            self.active_command = command
            self.state = "OPENING" if command == "open" else "CLOSING"
            self.last_result = ""
            self.reset_encoder()
            if command == "open":
                self.motor_open()
            else:
                self.motor_close()

        start_time = time.monotonic()
        success = False
        reason = ""
        try:
            handle = self.gpio_handle
            enc_a_pin = self.enc_a_pin
            enc_b_pin = self.enc_b_pin
            last_a = self.last_a
            while rclpy.ok():
                a_value = lgpio.gpio_read(handle, enc_a_pin)
                b_value = lgpio.gpio_read(handle, enc_b_pin)
                if a_value != last_a:
                    if b_value != a_value:
                        self.ticks += 1
                    else:
                        self.ticks -= 1
                last_a = a_value
                current_ticks = abs(self.ticks)
                if current_ticks >= target_ticks:
                    success = True
                    reason = f"{command} complete at {self.ticks} ticks."
                    break
                if self.stop_requested:
                    reason = f"{command} stopped at {self.ticks} ticks."
                    break
                if time.monotonic() - start_time > self.move_timeout_s:
                    reason = f"{command} timeout at {self.ticks} ticks."
                    break
                if self.encoder_poll_period_s > 0.0:
                    time.sleep(self.encoder_poll_period_s)
            self.last_a = last_a
        finally:
            with self.lock:
                self.stop_motor()
                final_ticks = self.ticks
                self.reset_encoder()
                self.active_command = ""
                self.stop_requested = False
                self.state = "IDLE" if success else "FAULT"
                self.last_result = reason or f"{command} ended at {final_ticks} ticks."
        return success, reason

    def open_callback(self, _request, response):
        success, message = self.run_motion("open", self.open_target_ticks)
        response.success = success
        response.message = message
        return response

    def close_callback(self, _request, response):
        success, message = self.run_motion("close", self.close_target_ticks)
        response.success = success
        response.message = message
        return response

    def stop_callback(self, _request, response):
        with self.lock:
            self.stop_requested = True
            self.stop_motor()
            if self.state not in ("OPENING", "CLOSING"):
                self.state = "IDLE"
            self.last_result = "stop requested"
        response.success = True
        response.message = "Lid stop requested."
        return response

    def publish_status(self) -> None:
        with self.lock:
            payload = {
                "state": self.state,
                "active_command": self.active_command,
                "ticks": self.ticks,
                "last_result": self.last_result,
            }
        msg = String()
        msg.data = json.dumps(payload)
        self.status_pub.publish(msg)

    def destroy_node(self):
        with self.lock:
            self.stop_motor()
            if self.gpio_handle is not None and lgpio is not None:
                lgpio.gpiochip_close(self.gpio_handle)
                self.gpio_handle = None
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = LidControlNode()
    executor = MultiThreadedExecutor(num_threads=2)
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
