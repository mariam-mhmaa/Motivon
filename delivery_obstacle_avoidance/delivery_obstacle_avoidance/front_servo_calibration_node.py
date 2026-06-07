import json
import statistics
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty, Int32, String

try:
    import lgpio
except ImportError:  # Allows syntax checks on machines without Raspberry Pi GPIO libs.
    lgpio = None


class FrontServoPulseThread(threading.Thread):
    def __init__(self, handle, pin, pulse_us, step_us):
        super().__init__(daemon=True)
        self.handle = handle
        self.pin = pin
        self.pulse_us = int(pulse_us)
        self.target_pulse_us = int(pulse_us)
        self.step_us = max(1, int(step_us))
        self.running = True
        self.lock = threading.Lock()

    def set_target(self, pulse_us):
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
            pulse_us = self.move_toward_target()
            lgpio.gpio_write(self.handle, self.pin, 1)
            time.sleep(pulse_us / 1_000_000.0)
            lgpio.gpio_write(self.handle, self.pin, 0)
            time.sleep(max(0.0, 0.020 - pulse_us / 1_000_000.0))


class FrontServoCalibrationNode(Node):
    """Move the front servo to commanded pulse widths and report front distance."""

    def __init__(self):
        super().__init__("front_servo_calibration_node")

        self.declare_parameter("gpio_chip", 4)
        self.declare_parameter("trigger_pin", 17)
        self.declare_parameter("echo_front_pin", 23)
        self.declare_parameter("front_servo_pin", 13)
        self.declare_parameter("minimum_pulse_us", 1000)
        self.declare_parameter("maximum_pulse_us", 2000)
        self.declare_parameter("right_45_pulse_us", 1100)
        self.declare_parameter("center_pulse_us", 1500)
        self.declare_parameter("left_45_pulse_us", 1900)
        self.declare_parameter("servo_step_us", 10)
        self.declare_parameter("settle_time_s", 0.50)
        self.declare_parameter("samples_per_position", 3)
        self.declare_parameter("sample_interval_s", 0.08)
        self.declare_parameter("echo_timeout_s", 0.04)

        self.trigger_pin = int(self.get_parameter("trigger_pin").value)
        self.echo_front_pin = int(self.get_parameter("echo_front_pin").value)
        self.front_servo_pin = int(self.get_parameter("front_servo_pin").value)
        self.minimum_pulse_us = int(self.get_parameter("minimum_pulse_us").value)
        self.maximum_pulse_us = int(self.get_parameter("maximum_pulse_us").value)
        self.right_45_pulse_us = int(
            self.get_parameter("right_45_pulse_us").value
        )
        self.center_pulse_us = int(self.get_parameter("center_pulse_us").value)
        self.left_45_pulse_us = int(
            self.get_parameter("left_45_pulse_us").value
        )
        self.servo_step_us = int(self.get_parameter("servo_step_us").value)
        self.settle_time_s = float(self.get_parameter("settle_time_s").value)
        self.samples_per_position = int(
            self.get_parameter("samples_per_position").value
        )
        self.sample_interval_s = float(
            self.get_parameter("sample_interval_s").value
        )
        self.echo_timeout_s = float(self.get_parameter("echo_timeout_s").value)

        if lgpio is None:
            raise RuntimeError("lgpio is not installed. Run this node on the Raspberry Pi.")

        chip = int(self.get_parameter("gpio_chip").value)
        self.gpio_handle = lgpio.gpiochip_open(chip)
        lgpio.gpio_claim_output(self.gpio_handle, self.trigger_pin, 0)
        lgpio.gpio_claim_input(self.gpio_handle, self.echo_front_pin)
        lgpio.gpio_claim_output(self.gpio_handle, self.front_servo_pin, 0)

        self.servo_thread = None
        self.result_pub = self.create_publisher(
            String, "/calibration/front_servo_result", 10
        )
        self.command_sub = self.create_subscription(
            Int32,
            "/calibration/front_servo_pulse",
            self.on_pulse_command,
            10,
        )
        self.scan_sub = self.create_subscription(
            Empty,
            "/calibration/front_servo_scan",
            self.on_scan_command,
            10,
        )

        self.get_logger().info(
            "Front servo calibration ready. Send a pulse on "
            "/calibration/front_servo_pulse or trigger the seven-angle scan on "
            "/calibration/front_servo_scan."
        )

    def wait_for_echo_low(self):
        timeout_at = time.monotonic() + 0.005
        while time.monotonic() <= timeout_at:
            if lgpio.gpio_read(self.gpio_handle, self.echo_front_pin) == 0:
                return True
        return False

    def read_front_cm(self):
        if not self.wait_for_echo_low():
            return None

        lgpio.gpio_write(self.gpio_handle, self.trigger_pin, 0)
        time.sleep(0.000002)
        lgpio.gpio_write(self.gpio_handle, self.trigger_pin, 1)
        time.sleep(0.000010)
        lgpio.gpio_write(self.gpio_handle, self.trigger_pin, 0)

        timeout_at = time.monotonic() + self.echo_timeout_s
        while lgpio.gpio_read(self.gpio_handle, self.echo_front_pin) == 0:
            if time.monotonic() > timeout_at:
                return None

        started_at = time.monotonic()
        timeout_at = started_at + self.echo_timeout_s
        while lgpio.gpio_read(self.gpio_handle, self.echo_front_pin) == 1:
            if time.monotonic() > timeout_at:
                return None

        duration_s = time.monotonic() - started_at
        return (duration_s * 34300.0) / 2.0

    def wait_until_target(self, target_pulse_us):
        maximum_move_s = (
            abs(target_pulse_us - self.servo_thread.current_pulse())
            / self.servo_step_us
        ) * 0.020
        timeout_at = time.monotonic() + maximum_move_s + 0.50

        while time.monotonic() <= timeout_at:
            if self.servo_thread.current_pulse() == target_pulse_us:
                return True
            time.sleep(0.020)
        return False

    def move_and_measure(self, requested_pulse_us, label=None):
        if not self.minimum_pulse_us <= requested_pulse_us <= self.maximum_pulse_us:
            self.get_logger().error(
                f"Rejected {requested_pulse_us} us. Allowed range is "
                f"{self.minimum_pulse_us}-{self.maximum_pulse_us} us."
            )
            return None

        position_text = f" ({label})" if label else ""
        self.get_logger().info(
            f"Moving front servo to {requested_pulse_us} us{position_text}."
        )

        if self.servo_thread is None:
            self.servo_thread = FrontServoPulseThread(
                self.gpio_handle,
                self.front_servo_pin,
                requested_pulse_us,
                self.servo_step_us,
            )
            self.servo_thread.start()
        else:
            self.servo_thread.set_target(requested_pulse_us)
            if not self.wait_until_target(requested_pulse_us):
                self.get_logger().error("Servo did not reach the requested pulse in time.")
                return None

        time.sleep(self.settle_time_s)

        samples_cm = []
        for sample_index in range(self.samples_per_position):
            value = self.read_front_cm()
            if value is not None:
                samples_cm.append(value)
            if sample_index + 1 < self.samples_per_position:
                time.sleep(self.sample_interval_s)

        median_cm = statistics.median(samples_cm) if samples_cm else None
        payload = {
            "label": label,
            "pulse_us": requested_pulse_us,
            "settle_time_s": self.settle_time_s,
            "samples_cm": samples_cm,
            "median_cm": median_cm,
            "valid_sample_count": len(samples_cm),
        }

        result_msg = String()
        result_msg.data = json.dumps(payload)
        self.result_pub.publish(result_msg)

        samples_text = ", ".join(f"{value:.1f}" for value in samples_cm) or "none"
        median_text = f"{median_cm:.1f} cm" if median_cm is not None else "invalid"
        self.get_logger().info(
            f"RESULT label={label or 'manual'} | pulse={requested_pulse_us} us | "
            f"samples=[{samples_text}] cm | median={median_text}"
        )
        return payload

    def on_pulse_command(self, msg):
        self.move_and_measure(int(msg.data))

    def scan_positions(self):
        right_span = self.center_pulse_us - self.right_45_pulse_us
        left_span = self.left_45_pulse_us - self.center_pulse_us
        return [
            ("right_45", self.right_45_pulse_us),
            ("right_30", round(self.center_pulse_us - right_span * 2 / 3)),
            ("right_15", round(self.center_pulse_us - right_span / 3)),
            ("center", self.center_pulse_us),
            ("left_15", round(self.center_pulse_us + left_span / 3)),
            ("left_30", round(self.center_pulse_us + left_span * 2 / 3)),
            ("left_45", self.left_45_pulse_us),
        ]

    def on_scan_command(self, _msg):
        self.get_logger().info(
            "Starting stationary seven-angle front scan. Keep the robot still."
        )

        if self.servo_thread is None:
            self.servo_thread = FrontServoPulseThread(
                self.gpio_handle,
                self.front_servo_pin,
                self.center_pulse_us,
                self.servo_step_us,
            )
            self.servo_thread.start()
            time.sleep(self.settle_time_s)

        results = []
        for label, pulse_us in self.scan_positions():
            result = self.move_and_measure(pulse_us, label)
            if result is not None:
                results.append(result)

        self.servo_thread.set_target(self.center_pulse_us)
        if self.wait_until_target(self.center_pulse_us):
            time.sleep(self.settle_time_s)
            self.get_logger().info(
                f"SCAN COMPLETE. Returned to center at {self.center_pulse_us} us."
            )
        else:
            self.get_logger().error("Scan completed but servo failed to return to center.")

        summary_msg = String()
        summary_msg.data = json.dumps(
            {
                "right_45_pulse_us": self.right_45_pulse_us,
                "center_pulse_us": self.center_pulse_us,
                "left_45_pulse_us": self.left_45_pulse_us,
                "results": results,
            }
        )
        self.result_pub.publish(summary_msg)

    def destroy_node(self):
        if self.servo_thread is not None:
            self.servo_thread.running = False
            self.servo_thread.join(timeout=0.20)
        if hasattr(self, "gpio_handle"):
            lgpio.gpio_write(self.gpio_handle, self.front_servo_pin, 0)
            lgpio.gpiochip_close(self.gpio_handle)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = FrontServoCalibrationNode()
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
