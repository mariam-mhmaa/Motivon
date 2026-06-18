from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_led_node_maps_all_mission_state_groups():
    source = (ROOT / "motivon_led" / "led_strip_node.py").read_text()

    for state in (
        "IDLE",
        "REQUESTS_RECEIVED",
        "MANAGER_VERIFYING",
        "SETTING_HOME",
        "NAVIGATING_TO_WP1",
        "HANDLING_WP1",
        "USER_VERIFYING",
        "NO_REQUEST_HOLDING_3S",
        "RETURNING_HOME",
        "COMPLETE",
        "ABORTING",
        "ABORTED",
        "FAULTED",
    ):
        assert state in source


def test_led_params_match_verified_strip_test_defaults():
    params = yaml.safe_load((ROOT / "config" / "led_params.yaml").read_text())
    values = params["led_strip_node"]["ros__parameters"]

    assert values["num_pixels"] == 20
    assert values["spi_bus"] == 0
    assert values["spi_device"] == 0
    assert values["spi_speed_hz"] == 2400000
    assert values["color_order"] == "BRG"
