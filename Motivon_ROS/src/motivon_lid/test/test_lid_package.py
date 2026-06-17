from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_lid_parameters_match_verified_gpio_test_script():
    params = yaml.safe_load((ROOT / "config" / "lid_params.yaml").read_text())
    values = params["lid_control_node"]["ros__parameters"]

    assert values["gpio_chip"] == 4
    assert values["dir1_pin"] == 5
    assert values["dir2_pin"] == 6
    assert values["pwm_pin"] == 12
    assert values["enc_a_pin"] == 16
    assert values["enc_b_pin"] == 20
    assert values["pwm_frequency_hz"] == 1000
    assert values["pwm_duty_percent"] == 40.0
    assert values["open_target_ticks"] == 42000
    assert values["close_target_ticks"] == 42000
    assert values["move_timeout_s"] == 60.0
    assert values["encoder_poll_period_s"] == 0.0


def test_lid_node_exposes_open_close_stop_services():
    source = (ROOT / "motivon_lid" / "lid_control_node.py").read_text()

    assert '"/lid/open"' in source
    assert '"/lid/close"' in source
    assert '"/lid/stop"' in source
    assert '"/lid/status"' in source
