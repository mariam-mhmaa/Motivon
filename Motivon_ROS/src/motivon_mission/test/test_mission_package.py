from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mission_manager_exposes_agreed_services():
    source = (ROOT / "motivon_mission" / "mission_manager_node.py").read_text()

    assert '"/mission/start"' in source
    assert '"/mission/cancel"' in source
    assert '"/mission/confirm_manager_verified"' in source
    assert '"/mission/confirm_manager_loaded"' in source
    assert '"/mission/confirm_user_verified"' in source
    assert '"/mission/confirm_user_received"' in source


def test_mission_manager_uses_vision_action_for_identity():
    source = (ROOT / "motivon_mission" / "mission_manager_node.py").read_text()

    assert '"/vision/verify_identity"' in source
    assert "VerifyIdentity" in source
    assert "USER_VERIFYING_PLACEHOLDER" not in source


def test_mission_manager_uses_role_specific_vision_attempts():
    source = (ROOT / "motivon_mission" / "mission_manager_node.py").read_text()
    params = (ROOT / "config" / "mission_params.yaml").read_text()

    assert "manager_vision_max_attempts" in source
    assert "user_vision_max_attempts" in source
    assert "manager_vision_max_attempts: 0" in params
    assert "user_vision_max_attempts: 5" in params
    assert "manager_vision_attempt_timeout_s: 60.0" in params
    assert "user_vision_attempt_timeout_s: 60.0" in params


def test_mission_manager_uses_fixed_route_targets():
    source = (ROOT / "motivon_mission" / "mission_manager_node.py").read_text()

    assert '"Station A"' in source
    assert '"Station B"' in source
    assert '"Station C"' in source
    assert '"WP1"' in source
    assert '"WP2"' in source
    assert '"WP3"' in source
