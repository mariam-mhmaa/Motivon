from pathlib import Path
import re


FIRMWARE = (
    Path(__file__).resolve().parents[3]
    / "firmware"
    / "esp32_base"
    / "esp32_base.ino"
)


def constant_value(source: str, name: str) -> int:
    match = re.search(
        rf"constexpr\s+\w+\s+{name}\s*=\s*(\d+)\s*;",
        source,
    )
    assert match is not None
    return int(match.group(1))


def test_command_watchdog_tolerates_short_wifi_jitter():
    source = FIRMWARE.read_text(encoding="utf-8")

    assert constant_value(source, "COMMAND_TIMEOUT_MS") == 750


def test_publish_failure_limit_requires_a_sustained_outage():
    source = FIRMWARE.read_text(encoding="utf-8")

    assert constant_value(source, "PUBLISH_FAILURE_LIMIT") == 20


def test_connected_micro_ros_loop_does_not_block_on_agent_ping():
    source = FIRMWARE.read_text(encoding="utf-8")

    discovery_period_ms = constant_value(
        source, "AGENT_DISCOVERY_PERIOD_MS"
    )
    discovery_timeout_ms = constant_value(
        source, "AGENT_DISCOVERY_PING_TIMEOUT_MS"
    )
    discovery_attempts = constant_value(
        source, "AGENT_DISCOVERY_PING_ATTEMPTS"
    )
    connected_case = source[
        source.index("case AGENT_CONNECTED:")
        : source.index("case AGENT_DISCONNECTED:")
    ]

    assert discovery_period_ms >= 2000
    assert discovery_timeout_ms * discovery_attempts <= 50
    assert "rmw_uros_ping_agent" not in connected_case
    assert "AGENT_HEALTH_PERIOD_MS" not in connected_case


def test_periodic_status_is_non_blocking_and_enable_is_reliable():
    source = FIRMWARE.read_text(encoding="utf-8")

    for publisher in (
        "wheel_states_publisher",
        "imu_publisher",
        "imu_ok_publisher",
        "heartbeat_publisher",
    ):
        assert (
            "rclc_publisher_init_best_effort(\n"
            f"          &{publisher}"
        ) in source
    assert (
        "rclc_subscription_init_default(\n"
        "          &enable_subscription"
    ) in source
    assert (
        "rclc_subscription_init_best_effort(\n"
        "          &cmd_vel_subscription"
    ) in source


def test_wifi_initialization_matches_verified_station_only_baseline():
    source = FIRMWARE.read_text(encoding="utf-8")

    expected_sequence = (
        "WiFi.disconnect(true);\n"
        "  delay(100);\n"
        "  WiFi.mode(WIFI_STA);\n"
        "  WiFi.persistent(false);\n"
        "  WiFi.setAutoReconnect(true);\n"
        "  WiFi.setSleep(false);"
    )
    assert expected_sequence in source
    assert "WiFi.begin(MOTIVON_WIFI_SSID, MOTIVON_WIFI_PASSWORD);" in source
    assert "WiFi.scanNetworks" not in source
    assert "WiFi.softAP" not in source


def test_wifi_loss_stops_motors_before_reconnecting():
    source = FIRMWARE.read_text(encoding="utf-8")

    wifi_loss_block = source.index(
        "if (WiFi.status() != WL_CONNECTED) {",
        source.index("void microRosTask"),
    )
    stop_request = source.index("requestBaseStop();", wifi_loss_block)
    reconnect = source.index("while (!connectWifi()) {", wifi_loss_block)
    micro_ros_task = source[
        source.index("void microRosTask") : source.index("void setup()")
    ]

    assert stop_request < reconnect
    assert "stopAllMotors();" not in micro_ros_task
    assert "getAgentState() == AGENT_CONNECTED" in source
    assert "setAgentState(AGENT_CONNECTED);" in source
