import json
import math
import statistics
import threading
import time
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String

try:
    import lgpio
except ImportError:  # Allows syntax checks on machines without Raspberry Pi GPIO libs.
    lgpio = None


def finite_distance(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0.0:
        return None
    return value


class ServoPulseThread(threading.Thread):
    def __init__(self, handle, pin, pulse_us, step_us):
        super().__init__(daemon=True)
        self.handle = handle
        self.pin = pin
        self.pulse_us = pulse_us
        self.target_pulse_us = pulse_us
        self.step_us = max(1, int(step_us))
        self.running = True
        self.lock = threading.Lock()

    def set_pulse(self, pulse_us):
        with self.lock:
            self.target_pulse_us = int(pulse_us)

    def current_pulse(self):
        with self.lock:
            return self.pulse_us

    def move_toward_target(self):
        with self.lock:
            error = self.target_pulse_us - self.pulse_us
            if abs(error) <= self.step_us:
                self.pulse_us = self.target_pulse_us
            else:
                self.pulse_us += self.step_us if error > 0 else -self.step_us
            return self.pulse_us

    def run(self):
        while self.running:
            pulse = self.move_toward_target()
            lgpio.gpio_write(self.handle, self.pin, 1)
            time.sleep(pulse / 1_000_000.0)
            lgpio.gpio_write(self.handle, self.pin, 0)
            remaining = 0.020 - (pulse / 1_000_000.0)
            if remaining > 0:
                time.sleep(remaining)


class UltrasonicScanNode(Node):
    """Read four HC-SR04 sensors and perform stopped front-servo checks."""

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
        self.declare_parameter("front_servo_right_45_us", 1100)
        self.declare_parameter("front_servo_center_us", 1500)
        self.declare_parameter("front_servo_left_45_us", 1900)
        self.declare_parameter("back_servo_center_us", 1500)
        self.declare_parameter("scan_period_s", 0.08)
        self.declare_parameter("servo_settle_s", 0.30)
        self.declare_parameter("servo_step_us", 10)
        self.declare_parameter("stationary_scan_samples", 3)
        self.declare_parameter("stationary_scan_max_attempts", 9)
        self.declare_parameter("enable_servo_output", False)
        self.declare_parameter("enable_servo_scan", False)
        self.declare_parameter("print_readings", True)
        self.declare_parameter("print_period_s", 0.50)
        self.declare_parameter("echo_timeout_s", 0.04)
        self.declare_parameter("filter_window", 5)
        self.declare_parameter("reading_expiry_s", 0.50)

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
        self.front_servo_right_45_us = int(
            self.get_parameter("front_servo_right_45_us").value
        )
        self.front_servo_center_us = int(
            self.get_parameter("front_servo_center_us").value
        )
        self.front_servo_left_45_us = int(
            self.get_parameter("front_servo_left_45_us").value
        )
        self.back_servo_center_us = int(
            self.get_parameter("back_servo_center_us").value
        )
        self.servo_settle_s = float(self.get_parameter("servo_settle_s").value)
        self.servo_step_us = int(self.get_parameter("servo_step_us").value)
        self.stationary_scan_samples = max(
            1,
            int(self.get_parameter("stationary_scan_samples").value),
        )
        self.stationary_scan_max_attempts = max(
            self.stationary_scan_samples,
            int(self.get_parameter("stationary_scan_max_attempts").value),
        )
        self.enable_servo_output = bool(self.get_parameter("enable_servo_output").value)
        self.enable_servo_scan = bool(self.get_parameter("enable_servo_scan").value)
        self.print_readings = bool(self.get_parameter("print_readings").value)
        self.print_period_s = float(self.get_parameter("print_period_s").value)
        self.echo_timeout_s = float(self.get_parameter("echo_timeout_s").value)
        self.filter_window = int(self.get_parameter("filter_window").value)
        self.reading_expiry_s = float(self.get_parameter("reading_expiry_s").value)
        self.last_print_s = 0.0

        self.scan_positions = [
            ("right", self.front_servo_right_45_us),
            ("center", self.front_servo_center_us),
            ("left", self.front_servo_left_45_us),
        ]
        self.scan_index = 0
        self.samples = {}
        self.filters = {}
        self.filter_last_valid_s = {}
        self.stationary_scan = None

        sensor_qos = QoSProfile(depth=1)
        self.scan_pub = self.create_publisher(String, "/obstacle/scan", sensor_qos)
        self.raw_pub = self.create_publisher(String, "/obstacle/raw_scan", sensor_qos)
        self.front_scan_result_pub = self.create_publisher(
            String,
            "/obstacle/front_servo_scan_result",
            10,
        )
        self.front_scan_request_sub = self.create_subscription(
            String,
            "/obstacle/front_servo_scan_request",
            self.on_front_scan_request,
            10,
        )

        if lgpio is None:
            raise RuntimeError("lgpio is not installed. Run this node on the Raspberry Pi.")

        chip = int(self.get_parameter("gpio_chip").value)
        self.gpio_handle = lgpio.gpiochip_open(chip)
        lgpio.gpio_claim_output(self.gpio_handle, self.trigger_pin, 0)
        for pin in self.echo_pins.values():
            lgpio.gpio_claim_input(self.gpio_handle, pin)

        self.servo_thread = None
        if self.enable_servo_output:
            lgpio.gpio_claim_output(
                self.gpio_handle,
                self.front_servo_pin,
                0,
            )
            self.get_logger().info(
                "Front servo output armed. PWM starts only when a stationary "
                "validation scan is requested."
            )
        else:
            self.get_logger().info(
                "Servo output disabled; position front/back sensors manually at center."
            )

        if self.enable_servo_scan and not self.enable_servo_output:
            self.get_logger().warning(
                "Servo scanning requested while servo output is disabled; using center readings."
            )
        elif self.enable_servo_scan:
            self.get_logger().warning(
                "Continuous servo scanning is disabled for safety; "
                "the front servo moves only for explicit stationary scan requests."
            )

        scan_period_s = float(self.get_parameter("scan_period_s").value)
        self.create_timer(scan_period_s, self.scan_once)
        self.get_logger().info("Ultrasonic scanner started.")

    def wait_for_echoes_low(self):
        timeout_at = time.monotonic() + 0.005
        while time.monotonic() < timeout_at:
            if all(
                lgpio.gpio_read(self.gpio_handle, pin) == 0
                for pin in self.echo_pins.values()
            ):
                return True
        return False

    def read_all_ultrasonic_cm(self):
        if not self.wait_for_echoes_low():
            return {name: None for name in self.echo_pins}

        lgpio.gpio_write(self.gpio_handle, self.trigger_pin, 0)
        time.sleep(0.000002)
        lgpio.gpio_write(self.gpio_handle, self.trigger_pin, 1)
        time.sleep(0.000010)
        lgpio.gpio_write(self.gpio_handle, self.trigger_pin, 0)

        started_at = {name: None for name in self.echo_pins}
        distances = {name: None for name in self.echo_pins}
        pending = set(self.echo_pins)
        timeout_at = time.monotonic() + self.echo_timeout_s
        while pending and time.monotonic() <= timeout_at:
            now = time.monotonic()
            for name in tuple(pending):
                level = lgpio.gpio_read(self.gpio_handle, self.echo_pins[name])
                if started_at[name] is None:
                    if level == 1:
                        started_at[name] = now
                elif level == 0:
                    distances[name] = ((now - started_at[name]) * 34300.0) / 2.0
                    pending.remove(name)

        return distances

    def filtered_value(self, key, value):
        if key not in self.filters:
            self.filters[key] = deque(maxlen=self.filter_window)

        now = time.monotonic()
        if value is not None:
            self.filters[key].append(float(value))
            self.filter_last_valid_s[key] = now

        last_valid_s = self.filter_last_valid_s.get(key)
        if last_valid_s is None or now - last_valid_s > self.reading_expiry_s:
            self.filters[key].clear()
            return None

        return statistics.median(self.filters[key])

    def update_sample(self, key, value):
        self.samples[key] = self.filtered_value(key, value)

    def publish_front_scan_result(self, result):
        msg = String()
        msg.data = json.dumps(result)
        self.front_scan_result_pub.publish(msg)

    def ensure_servo_thread(self):
        if self.servo_thread is not None:
            return

        self.servo_thread = ServoPulseThread(
            self.gpio_handle,
            self.front_servo_pin,
            self.front_servo_center_us,
            self.servo_step_us,
        )
        self.servo_thread.start()

    def disable_servo_output(self):
        if self.servo_thread is None:
            return
        self.servo_thread.running = False
        self.servo_thread.join(timeout=0.10)
        lgpio.gpio_write(self.gpio_handle, self.front_servo_pin, 0)
        self.servo_thread = None

    def on_front_scan_request(self, msg):
        try:
            request = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning(
                "Ignoring malformed /obstacle/front_servo_scan_request JSON."
            )
            return

        request_id = request.get("request_id")
        side = request.get("side")
        if side not in ("left", "right"):
            self.publish_front_scan_result(
                {
                    "request_id": request_id,
                    "status": "error",
                    "reason": "side_must_be_left_or_right",
                }
            )
            return

        if not self.enable_servo_output:
            self.publish_front_scan_result(
                {
                    "request_id": request_id,
                    "side": side,
                    "status": "error",
                    "reason": "servo_output_disabled",
                }
            )
            return

        if self.stationary_scan is not None:
            self.publish_front_scan_result(
                {
                    "request_id": request_id,
                    "side": side,
                    "status": "error",
                    "reason": "front_servo_scan_busy",
                }
            )
            return

        pulse_us = (
            self.front_servo_left_45_us
            if side == "left"
            else self.front_servo_right_45_us
        )
        filter_key = f"front_{side}"
        self.filters.pop(filter_key, None)
        self.filter_last_valid_s.pop(filter_key, None)
        self.samples.pop(filter_key, None)
        self.stationary_scan = {
            "request_id": request_id,
            "side": side,
            "pulse_us": pulse_us,
            "phase": "moving_to_side",
            "phase_started_s": time.monotonic(),
            "samples_cm": [],
            "attempts": 0,
            "result_reason": None,
        }
        self.ensure_servo_thread()
        self.servo_thread.set_pulse(pulse_us)
        self.get_logger().warning(
            "FRONT SERVO VALIDATION START | "
            f"request={request_id}, side={side}, pulse={pulse_us} us"
        )

    def active_front_position(self):
        scan = self.stationary_scan
        if scan is None:
            return "center", self.front_servo_center_us

        if scan["phase"] == "sampling_side":
            return scan["side"], scan["pulse_us"]
        if scan["phase"] == "verify_center":
            return "center", self.front_servo_center_us
        return "moving", (
            scan["pulse_us"]
            if scan["phase"] in ("moving_to_side", "settling_side")
            else self.front_servo_center_us
        )

    def advance_stationary_scan(self, measured_front):
        scan = self.stationary_scan
        if scan is None:
            return

        now = time.monotonic()
        front_pulse = self.servo_thread.current_pulse()
        phase = scan["phase"]

        if phase == "moving_to_side":
            if front_pulse == scan["pulse_us"]:
                scan["phase"] = "settling_side"
                scan["phase_started_s"] = now
            return

        if phase == "settling_side":
            if now - scan["phase_started_s"] >= self.servo_settle_s:
                scan["phase"] = "sampling_side"
                scan["phase_started_s"] = now
            return

        if phase == "sampling_side":
            scan["attempts"] += 1
            valid = finite_distance(measured_front)
            if valid is not None:
                scan["samples_cm"].append(valid)

            enough_samples = (
                len(scan["samples_cm"]) >= self.stationary_scan_samples
            )
            attempts_exhausted = (
                scan["attempts"] >= self.stationary_scan_max_attempts
            )
            if enough_samples or attempts_exhausted:
                if not enough_samples:
                    scan["result_reason"] = "insufficient_valid_samples"
                scan["phase"] = "moving_to_center"
                scan["phase_started_s"] = now
                self.servo_thread.set_pulse(self.front_servo_center_us)
            return

        if phase == "moving_to_center":
            if front_pulse == self.front_servo_center_us:
                scan["phase"] = "settling_center"
                scan["phase_started_s"] = now
            return

        if phase == "settling_center":
            if now - scan["phase_started_s"] >= self.servo_settle_s:
                scan["phase"] = "verify_center"
                scan["phase_started_s"] = now
            return

        if phase != "verify_center":
            return

        samples = scan["samples_cm"]
        result = {
            "request_id": scan["request_id"],
            "side": scan["side"],
            "pulse_us": scan["pulse_us"],
            "samples_cm": [round(value, 2) for value in samples],
            "valid_sample_count": len(samples),
            "returned_center": True,
        }
        if scan["result_reason"] is None:
            result["status"] = "complete"
            result["median_cm"] = statistics.median(samples)
            self.get_logger().warning(
                "FRONT SERVO VALIDATION COMPLETE | "
                f"request={scan['request_id']}, side={scan['side']}, "
                f"samples={[round(value, 1) for value in samples]}, "
                f"median={result['median_cm']:.1f} cm, returned=center"
            )
        else:
            result["status"] = "error"
            result["reason"] = scan["result_reason"]
            self.get_logger().error(
                "FRONT SERVO VALIDATION FAILED | "
                f"request={scan['request_id']}, side={scan['side']}, "
                f"reason={scan['result_reason']}, returned=center"
            )

        self.stationary_scan = None
        self.disable_servo_output()
        self.publish_front_scan_result(result)

    def scan_once(self):
        front_label, front_pulse = self.active_front_position()
        back_label = "center"

        if self.servo_thread is not None:
            self.servo_thread.set_pulse(front_pulse)

        measured = self.read_all_ultrasonic_cm()
        raw = {
            "left": measured["left"],
            "right": measured["right"],
            f"front_{front_label}": measured["front"],
            f"back_{back_label}": measured["back"],
        }

        for key, value in raw.items():
            self.update_sample(key, value)

        stamp = self.get_clock().now().nanoseconds / 1_000_000_000.0
        payload = {
            "stamp": stamp,
            "active_scan": {
                "front": front_label,
                "back": back_label,
            },
            "distances_cm": self.samples,
        }

        raw_msg = String()
        raw_msg.data = json.dumps(
            {
                "stamp": stamp,
                "raw_cm": raw,
                "active_scan": payload["active_scan"],
            }
        )
        self.raw_pub.publish(raw_msg)

        scan_msg = String()
        scan_msg.data = json.dumps(payload)
        self.scan_pub.publish(scan_msg)

        self.print_distances_if_due(payload)
        if self.stationary_scan is not None:
            self.advance_stationary_scan(measured["front"])

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
        if self.servo_thread is not None:
            self.disable_servo_output()
        if hasattr(self, "gpio_handle"):
            lgpio.gpiochip_close(self.gpio_handle)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = UltrasonicScanNode()
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
