import json
import statistics
import threading
import time
from collections import deque

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

try:
    import lgpio
except ImportError:  # Allows syntax checks on machines without Raspberry Pi GPIO libs.
    lgpio = None


class ServoPulseThread(threading.Thread):
    def __init__(self, handle, front_pin, back_pin, front_pulse_us, back_pulse_us, step_us):
        super().__init__(daemon=True)
        self.handle = handle
        self.front_pin = front_pin
        self.back_pin = back_pin
        self.front_pulse_us = front_pulse_us
        self.back_pulse_us = back_pulse_us
        self.target_front_pulse_us = front_pulse_us
        self.target_back_pulse_us = back_pulse_us
        self.step_us = max(1, int(step_us))
        self.running = True
        self.lock = threading.Lock()

    def set_pulses(self, front_pulse_us, back_pulse_us):
        with self.lock:
            self.target_front_pulse_us = int(front_pulse_us)
            self.target_back_pulse_us = int(back_pulse_us)

    def move_toward_target(self):
        with self.lock:
            front_error = self.target_front_pulse_us - self.front_pulse_us
            back_error = self.target_back_pulse_us - self.back_pulse_us

            if abs(front_error) <= self.step_us:
                self.front_pulse_us = self.target_front_pulse_us
            else:
                self.front_pulse_us += self.step_us if front_error > 0 else -self.step_us

            if abs(back_error) <= self.step_us:
                self.back_pulse_us = self.target_back_pulse_us
            else:
                self.back_pulse_us += self.step_us if back_error > 0 else -self.step_us

            return self.front_pulse_us, self.back_pulse_us

    def run(self):
        while self.running:
            front_pulse, back_pulse = self.move_toward_target()

            lgpio.gpio_write(self.handle, self.front_pin, 1)
            time.sleep(front_pulse / 1_000_000.0)
            lgpio.gpio_write(self.handle, self.front_pin, 0)

            lgpio.gpio_write(self.handle, self.back_pin, 1)
            time.sleep(back_pulse / 1_000_000.0)
            lgpio.gpio_write(self.handle, self.back_pin, 0)

            used_time = (front_pulse + back_pulse) / 1_000_000.0
            remaining = 0.020 - used_time
            if remaining > 0:
                time.sleep(remaining)


class UltrasonicScanNode(Node):
    """Read four HC-SR04 sensors and scan the front/back sensors with servos."""

    def __init__(self):
        super().__init__("ultrasonic_scan_node")

        self.declare_parameter("gpio_chip", 4)
        self.declare_parameter("trigger_pin", 17)
        self.declare_parameter("echo_left_pin", 27)
        self.declare_parameter("echo_right_pin", 22)
        self.declare_parameter("echo_front_pin", 23)
        self.declare_parameter("echo_back_pin", 24)
        self.declare_parameter("front_servo_pin", 13)
        self.declare_parameter("back_servo_pin", 18)
        self.declare_parameter("servo_center_us", 1500)
        self.declare_parameter("servo_plus_45_us", 1750)
        self.declare_parameter("servo_minus_45_us", 1250)
        self.declare_parameter("scan_period_s", 0.80)
        self.declare_parameter("servo_settle_s", 0.30)
        self.declare_parameter("servo_step_us", 10)
        self.declare_parameter("enable_servo_scan", False)
        self.declare_parameter("print_readings", True)
        self.declare_parameter("print_period_s", 0.50)
        self.declare_parameter("echo_timeout_s", 0.04)
        self.declare_parameter("filter_window", 5)

        self.trigger_pin = int(self.get_parameter("trigger_pin").value)
        self.echo_pins = {
            "left": int(self.get_parameter("echo_left_pin").value),
            "right": int(self.get_parameter("echo_right_pin").value),
            "front": int(self.get_parameter("echo_front_pin").value),
            "back": int(self.get_parameter("echo_back_pin").value),
        }
        self.front_servo_pin = int(self.get_parameter("front_servo_pin").value)
        self.back_servo_pin = int(self.get_parameter("back_servo_pin").value)
        self.servo_center_us = int(self.get_parameter("servo_center_us").value)
        self.servo_plus_45_us = int(self.get_parameter("servo_plus_45_us").value)
        self.servo_minus_45_us = int(self.get_parameter("servo_minus_45_us").value)
        self.servo_settle_s = float(self.get_parameter("servo_settle_s").value)
        self.servo_step_us = int(self.get_parameter("servo_step_us").value)
        self.enable_servo_scan = bool(self.get_parameter("enable_servo_scan").value)
        self.print_readings = bool(self.get_parameter("print_readings").value)
        self.print_period_s = float(self.get_parameter("print_period_s").value)
        self.echo_timeout_s = float(self.get_parameter("echo_timeout_s").value)
        self.filter_window = int(self.get_parameter("filter_window").value)
        self.last_print_s = 0.0

        self.scan_positions = [
            ("right", self.servo_plus_45_us),
            ("center", self.servo_center_us),
            ("left", self.servo_minus_45_us),
        ]
        self.scan_index = 0
        self.samples = {}
        self.filters = {}

        self.scan_pub = self.create_publisher(String, "/obstacle/scan", 10)
        self.raw_pub = self.create_publisher(String, "/obstacle/raw_scan", 10)

        if lgpio is None:
            raise RuntimeError("lgpio is not installed. Run this node on the Raspberry Pi.")

        chip = int(self.get_parameter("gpio_chip").value)
        self.gpio_handle = lgpio.gpiochip_open(chip)
        lgpio.gpio_claim_output(self.gpio_handle, self.trigger_pin, 0)
        lgpio.gpio_claim_output(self.gpio_handle, self.front_servo_pin, 0)
        lgpio.gpio_claim_output(self.gpio_handle, self.back_servo_pin, 0)
        for pin in self.echo_pins.values():
            lgpio.gpio_claim_input(self.gpio_handle, pin)

        self.servo_thread = ServoPulseThread(
            self.gpio_handle,
            self.front_servo_pin,
            self.back_servo_pin,
            self.servo_center_us,
            self.servo_center_us,
            self.servo_step_us,
        )
        self.servo_thread.start()

        scan_period_s = float(self.get_parameter("scan_period_s").value)
        self.create_timer(scan_period_s, self.scan_once)
        self.get_logger().info("Ultrasonic scanner started.")

    def read_ultrasonic_cm(self, echo_pin):
        lgpio.gpio_write(self.gpio_handle, self.trigger_pin, 0)
        time.sleep(0.000002)
        lgpio.gpio_write(self.gpio_handle, self.trigger_pin, 1)
        time.sleep(0.000010)
        lgpio.gpio_write(self.gpio_handle, self.trigger_pin, 0)

        timeout_at = time.monotonic() + self.echo_timeout_s
        while lgpio.gpio_read(self.gpio_handle, echo_pin) == 0:
            if time.monotonic() > timeout_at:
                return None

        start = time.monotonic()
        timeout_at = time.monotonic() + self.echo_timeout_s
        while lgpio.gpio_read(self.gpio_handle, echo_pin) == 1:
            if time.monotonic() > timeout_at:
                return None

        end = time.monotonic()
        return ((end - start) * 34300.0) / 2.0

    def filtered_value(self, key, value):
        if key not in self.filters:
            self.filters[key] = deque(maxlen=self.filter_window)

        if value is not None:
            self.filters[key].append(float(value))

        if not self.filters[key]:
            return None

        return statistics.median(self.filters[key])

    def update_sample(self, key, value):
        self.samples[key] = self.filtered_value(key, value)

    def scan_once(self):
        if self.enable_servo_scan:
            front_label, front_pulse = self.scan_positions[self.scan_index]
            back_label, back_pulse = self.scan_positions[self.scan_index]
            self.scan_index = (self.scan_index + 1) % len(self.scan_positions)
        else:
            front_label = "center"
            back_label = "center"
            front_pulse = self.servo_center_us
            back_pulse = self.servo_center_us

        self.servo_thread.set_pulses(front_pulse, back_pulse)
        time.sleep(self.servo_settle_s)

        raw = {}
        raw["left"] = self.read_ultrasonic_cm(self.echo_pins["left"])
        time.sleep(0.030)
        raw["right"] = self.read_ultrasonic_cm(self.echo_pins["right"])
        time.sleep(0.030)
        raw[f"front_{front_label}"] = self.read_ultrasonic_cm(self.echo_pins["front"])
        time.sleep(0.030)
        raw[f"back_{back_label}"] = self.read_ultrasonic_cm(self.echo_pins["back"])

        for key, value in raw.items():
            self.update_sample(key, value)

        payload = {
            "stamp": self.get_clock().now().nanoseconds / 1_000_000_000.0,
            "active_scan": {
                "front": front_label,
                "back": back_label,
            },
            "distances_cm": self.samples,
        }

        scan_msg = String()
        scan_msg.data = json.dumps(payload)
        self.scan_pub.publish(scan_msg)

        raw_msg = String()
        raw_msg.data = json.dumps({"raw_cm": raw, "active_scan": payload["active_scan"]})
        self.raw_pub.publish(raw_msg)

        self.print_distances_if_due(payload)

    def fmt_cm(self, key):
        value = self.samples.get(key)
        if value is None:
            return "----"
        return f"{value:5.1f}"

    def print_distances_if_due(self, payload):
        if not self.print_readings:
            return

        now = time.monotonic()
        if now - self.last_print_s < self.print_period_s:
            return
        self.last_print_s = now

        active_front = payload["active_scan"]["front"]
        active_back = payload["active_scan"]["back"]
        self.get_logger().info(
            "cm | "
            f"F={self.fmt_cm('front_center')} | "
            f"L={self.fmt_cm('left')} | "
            f"R={self.fmt_cm('right')} | "
            f"B={self.fmt_cm('back_center')} | "
            f"scan front={active_front}, back={active_back}"
        )

    def destroy_node(self):
        if hasattr(self, "servo_thread"):
            self.servo_thread.running = False
            self.servo_thread.join(timeout=0.20)
        if hasattr(self, "gpio_handle"):
            lgpio.gpio_write(self.gpio_handle, self.front_servo_pin, 0)
            lgpio.gpio_write(self.gpio_handle, self.back_servo_pin, 0)
            lgpio.gpiochip_close(self.gpio_handle)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = UltrasonicScanNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
