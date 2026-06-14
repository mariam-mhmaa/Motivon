from pathlib import Path

import yaml


CONFIG = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "navigation_params.yaml"
)


def test_initial_navigation_limits_are_conservative():
    with CONFIG.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    parameters = document["navigation_node"]["ros__parameters"]

    assert parameters["maximum_speed_mps"] == 0.08
    assert parameters["maximum_speed_mps"] <= 0.20
    assert parameters["station_tolerance_m"] == 0.05
    assert parameters["connector_tolerance_m"] == 0.10
    assert parameters["arrival_settle_samples"] == 10
    assert parameters["odometry_topic"] == "/odometry/filtered"
    assert parameters["command_topic"] == "/navigation/cmd_vel_raw"
