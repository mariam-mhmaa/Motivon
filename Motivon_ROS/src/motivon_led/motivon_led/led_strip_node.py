#!/usr/bin/env python3

import time
from typing import Dict, Tuple

import rclpy
from motivon_interfaces.msg import MissionEvent, MissionStatus
from rclpy.node import Node

try:
    import spidev
except ImportError:  # pragma: no cover - only available on Raspberry Pi
    spidev = None


Color = Tuple[int, int, int]


class LedStripNode(Node):
    """Drive the WS2811 strip from mission state and mission events."""

    BASE_STATE_COLORS = {
        "IDLE": "yellow",
        "REQUESTS_RECEIVED": "yellow",
        "MANAGER_VERIFYING": "orange",
        "OPENING_LID_FOR_LOADING": "orange",
        "WAITING_FOR_MANAGER_LOAD": "orange",
        "SETTING_HOME": "orange",
        "CLOSING_LID_AFTER_LOADING": "orange",
        "NAVIGATING_TO_WP1": "blue",
        "NAVIGATING_TO_WP2": "blue",
        "NAVIGATING_TO_WP3": "blue",
        "RETURNING_HOME": "blue",
        "HANDLING_WP1": "purple",
        "HANDLING_WP2": "purple",
        "HANDLING_WP3": "purple",
        "USER_VERIFYING": "purple",
        "OPENING_LID_FOR_USER": "purple",
        "WAITING_FOR_USER_RECEIPT": "purple",
        "CLOSING_LID_AFTER_USER": "purple",
        "NO_REQUEST_HOLDING_3S": "purple",
        "COMPLETE": "green",
        "ABORTING": "red",
        "ABORTED": "red",
        "FAULTED": "red",
    }
    GREEN_OVERRIDE_EVENTS = {"VISION_VERIFIED"}
    RED_OVERRIDE_EVENTS = {
        "VISION_VERIFY_ATTEMPT_FAILED",
        "REQUEST_SKIPPED_UNVERIFIED",
        "MISSION_FAULTED",
        "MISSION_CANCELLED",
    }

    def __init__(self):
        super().__init__("led_strip_node")
        self._declare_parameters()

        self.num_pixels = int(self.get_parameter("num_pixels").value)
        self.spi_bus = int(self.get_parameter("spi_bus").value)
        self.spi_device = int(self.get_parameter("spi_device").value)
        self.spi_speed_hz = int(self.get_parameter("spi_speed_hz").value)
        self.color_order = str(self.get_parameter("color_order").value).upper()
        self.status_timeout_s = float(
            self.get_parameter("status_timeout_s").value
        )
        self.override_duration_s = float(
            self.get_parameter("override_duration_s").value
        )
        self.flash_period_s = float(self.get_parameter("flash_period_s").value)
        self.allow_off_during_flash = bool(
            self.get_parameter("allow_off_during_flash").value
        )
        self.startup_color = str(self.get_parameter("startup_color").value)
        self.colors = self._load_colors()

        self.spi = self._open_spi()
        self.last_status = None
        self.last_status_time_s = 0.0
        self.override_color_name = ""
        self.override_until_s = 0.0
        self.last_color = None

        self.create_subscription(
            MissionStatus,
            "/mission/status",
            self.on_mission_status,
            10,
        )
        self.create_subscription(
            MissionEvent,
            "/mission/events",
            self.on_mission_event,
            10,
        )
        self.create_timer(0.10, self.update_leds)
        self.get_logger().info(
            "LED strip ready: pixels=%d, spi=/dev/spidev%d.%d, order=%s."
            % (
                self.num_pixels,
                self.spi_bus,
                self.spi_device,
                self.color_order,
            )
        )

    def _declare_parameters(self):
        self.declare_parameter("num_pixels", 20)
        self.declare_parameter("spi_bus", 0)
        self.declare_parameter("spi_device", 0)
        self.declare_parameter("spi_speed_hz", 2400000)
        self.declare_parameter("color_order", "GRB")
        self.declare_parameter("status_timeout_s", 2.0)
        self.declare_parameter("override_duration_s", 2.0)
        self.declare_parameter("flash_period_s", 0.50)
        self.declare_parameter("allow_off_during_flash", True)
        self.declare_parameter("startup_color", "yellow")
        self.declare_parameter("colors.yellow", [80, 80, 0])
        self.declare_parameter("colors.orange", [90, 35, 0])
        self.declare_parameter("colors.green", [0, 80, 0])
        self.declare_parameter("colors.red", [90, 0, 0])
        self.declare_parameter("colors.blue", [0, 0, 80])
        self.declare_parameter("colors.purple", [80, 0, 80])
        self.declare_parameter("colors.off", [0, 0, 0])

    def _load_colors(self) -> Dict[str, Color]:
        colors = {}
        for name in ("yellow", "orange", "green", "red", "blue", "purple", "off"):
            values = list(self.get_parameter(f"colors.{name}").value)
            if len(values) != 3:
                raise ValueError(f"Color {name} must have three RGB values.")
            colors[name] = tuple(
                max(0, min(255, int(value))) for value in values
            )
        return colors

    def _open_spi(self):
        if spidev is None:
            raise RuntimeError(
                "spidev is not installed. Run led_strip_node on the Raspberry Pi."
            )
        spi = spidev.SpiDev()
        spi.open(self.spi_bus, self.spi_device)
        spi.max_speed_hz = self.spi_speed_hz
        spi.mode = 0
        return spi

    def on_mission_status(self, msg: MissionStatus) -> None:
        self.last_status = msg
        self.last_status_time_s = time.monotonic()

    def on_mission_event(self, msg: MissionEvent) -> None:
        if msg.event_type in self.GREEN_OVERRIDE_EVENTS:
            self._start_override("green")
        elif msg.event_type in self.RED_OVERRIDE_EVENTS:
            self._start_override("red")

    def _start_override(self, color_name: str) -> None:
        self.override_color_name = color_name
        self.override_until_s = time.monotonic() + self.override_duration_s

    def update_leds(self) -> None:
        color_name, flashing = self._desired_output()
        color = self._resolve_flash_color(color_name, flashing)
        if color != self.last_color:
            self.set_all(*color)
            self.last_color = color

    def _desired_output(self):
        now_s = time.monotonic()
        if now_s < self.override_until_s and self.override_color_name:
            return self.override_color_name, False

        if (
            self.last_status is None
            or now_s - self.last_status_time_s > self.status_timeout_s
        ):
            return self.startup_color, False

        if self.last_status.safety_paused:
            return "red", True

        state = self.last_status.state
        if state == "FAULTED":
            return "red", True

        return self.BASE_STATE_COLORS.get(state, self.startup_color), False

    def _resolve_flash_color(self, color_name: str, flashing: bool) -> Color:
        if not flashing:
            return self.colors[color_name]

        phase = int(time.monotonic() / max(self.flash_period_s, 0.05)) % 2
        if phase == 0:
            return self.colors[color_name]
        if self.allow_off_during_flash:
            return self.colors["off"]
        red = self.colors[color_name]
        return tuple(max(1, int(value * 0.20)) for value in red)

    @staticmethod
    def encode_byte(byte: int):
        bits = ""
        for index in range(7, -1, -1):
            bits += "110" if byte & (1 << index) else "100"

        output = []
        for index in range(0, len(bits), 8):
            chunk = bits[index : index + 8]
            if len(chunk) < 8:
                chunk += "0" * (8 - len(chunk))
            output.append(int(chunk, 2))
        return output

    def make_frame(self, red: int, green: int, blue: int):
        data = []
        if self.color_order == "RGB":
            ordered = (red, green, blue)
        elif self.color_order == "BRG":
            ordered = (blue, red, green)
        else:
            ordered = (green, red, blue)

        for _ in range(self.num_pixels):
            for value in ordered:
                data.extend(self.encode_byte(value))
        data.extend([0x00] * 100)
        return data

    def set_all(self, red: int, green: int, blue: int) -> None:
        self.spi.xfer3(self.make_frame(red, green, blue))

    def destroy_node(self):
        try:
            self.set_all(*self.colors["off"])
            self.spi.close()
        except Exception:
            pass
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = LedStripNode()
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
