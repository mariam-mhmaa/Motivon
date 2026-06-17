from pathlib import Path
import re


def firmware_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "firmware" / "esp32_base" / "esp32_base.ino"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not locate firmware/esp32_base.ino")


FIRMWARE = firmware_path()


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


def test_agent_discovery_failure_restarts_esp_after_sustained_outage():
    source = FIRMWARE.read_text(encoding="utf-8")

    restart_timeout_ms = constant_value(
        source, "AGENT_DISCOVERY_RESTART_TIMEOUT_MS"
    )
    restart_failure_limit = constant_value(
        source, "AGENT_DISCOVERY_RESTART_FAILURE_LIMIT"
    )
    micro_ros_task_start = source.index("void microRosTask")
    waiting_case_start = source.index(
        "case WAITING_FOR_AGENT:", micro_ros_task_start
    )
    waiting_case = source[
        waiting_case_start : source.index(
            "case AGENT_AVAILABLE:", micro_ros_task_start
        )
    ]
    restart_helper = source[
        source.index("void restartAfterAgentDiscoveryTimeout")
        : source.index("void microRosTask")
    ]
    connected_case = source[
        source.index("case AGENT_CONNECTED:", micro_ros_task_start)
        : source.index("case AGENT_DISCONNECTED:", micro_ros_task_start)
    ]

    assert restart_timeout_ms >= 60000
    assert restart_failure_limit == 30
    assert "Agent ping failed" in waiting_case
    assert "consecutive_discovery_failures" in waiting_case
    assert "restartAfterAgentDiscoveryTimeout(discovery_wait_ms);" in waiting_case
    assert "requestBaseStop();" in restart_helper
    assert "stopAllMotors();" in restart_helper
    assert "ESP.restart();" in restart_helper
    assert "restartAfterAgentDiscoveryTimeout" not in connected_case


def test_entity_creation_failures_restart_esp():
    source = FIRMWARE.read_text(encoding="utf-8")

    failure_limit = constant_value(source, "ENTITY_CREATION_FAILURE_LIMIT")
    micro_ros_task_start = source.index("void microRosTask")
    available_case = source[
        source.index("case AGENT_AVAILABLE:", micro_ros_task_start)
        : source.index("case AGENT_CONNECTED:", micro_ros_task_start)
    ]
    restart_helper = source[
        source.index("void restartAfterEntityCreationFailures")
        : source.index("void microRosTask")
    ]

    assert failure_limit == 5
    assert "consecutive_entity_failures" in available_case
    assert "restartAfterEntityCreationFailures" in available_case
    assert "requestBaseStop();" in restart_helper
    assert "stopAllMotors();" in restart_helper
    assert "ESP.restart();" in restart_helper


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


def test_esp_software_reset_requires_explicit_ros_request():
    source = FIRMWARE.read_text(encoding="utf-8")

    assert '"/base/software_reset"' in source
    assert "softwareResetCallback" in source
    assert "if (reset->data)" in source
    assert "ESP.restart();" in source


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
