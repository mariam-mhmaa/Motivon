from pathlib import Path

import yaml


CONFIG = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "navigation_params.yaml"
)
NODE_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "motivon_navigation"
    / "navigation_node.py"
)


def test_initial_navigation_limits_match_confirmed_configuration():
    with CONFIG.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    parameters = document["navigation_node"]["ros__parameters"]

    assert parameters["maximum_speed_mps"] == 0.12
    assert parameters["maximum_cross_track_speed_mps"] == 0.08
    assert parameters["maximum_turn_rate_rad_s"] == 0.30
    assert parameters["maximum_linear_acceleration_mps2"] == 0.25
    assert parameters["maximum_angular_acceleration_rad_s2"] == 0.60
    assert parameters["along_track_gain"] == 0.80
    assert parameters["cross_track_gain"] == 1.0
    assert parameters["final_position_gain"] == 0.80
    assert parameters["yaw_hold_gain"] == 1.50
    assert parameters["yaw_alignment_gain"] == 1.20
    assert parameters["final_approach_radius_m"] == 0.30
    assert parameters["station_tolerance_m"] == 0.05
    assert parameters["home_tolerance_m"] == 0.05
    assert parameters["yaw_tolerance_rad"] == 0.035
    assert parameters["connector_tolerance_m"] == 0.10
    assert parameters["arrival_settle_samples"] == 10
    assert parameters["yaw_settle_samples"] == 18
    assert parameters["odometry_topic"] == "/odometry/filtered"
    assert parameters["odometry_stale_timeout_s"] == 0.30
    assert parameters["odometry_abort_timeout_s"] == 5.00
    assert parameters["localization_recovery_samples"] == 5
    assert parameters["progress_timeout_s"] == 5.0
    assert parameters["enable_static_avoidance"] is True
    assert parameters["avoidance_lateral_m"] == 0.65
    assert parameters["avoidance_forward_m"] == 1.00
    assert parameters["side_avoidance_longitudinal_search_m"] == 1.20
    assert parameters["side_avoidance_longitudinal_margin_m"] == 0.38
    assert parameters["side_avoidance_lateral_search_m"] == 0.90
    assert parameters["side_avoidance_lateral_margin_m"] == 0.34
    assert parameters["side_avoidance_edge_seen_cm"] == 45.0
    assert parameters["side_avoidance_edge_clear_cm"] == 60.0
    assert parameters["front_avoidance_lateral_search_m"] == 0.90
    assert parameters["front_avoidance_lateral_margin_m"] == 0.34
    assert parameters["front_avoidance_longitudinal_search_m"] == 1.20
    assert parameters["front_avoidance_longitudinal_margin_m"] == 0.38
    assert parameters["front_avoidance_edge_seen_cm"] == 45.0
    assert parameters["front_avoidance_edge_clear_cm"] == 60.0
    assert parameters["command_topic"] == "/navigation/cmd_vel_raw"


def test_navigation_does_not_subscribe_to_raw_esp_telemetry():
    with CONFIG.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    parameters = document["navigation_node"]["ros__parameters"]
    source = NODE_SOURCE.read_text(encoding="utf-8")

    assert "wheel_states_topic" not in parameters
    assert "imu_topic" not in parameters
    assert "base_stream_stale_timeout_s" not in parameters
    assert "base_stream_abort_timeout_s" not in parameters
    assert "_wheel_states_callback" not in source
    assert "_imu_callback" not in source
