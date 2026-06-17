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


def test_mission_manager_uses_fixed_route_targets():
    source = (ROOT / "motivon_mission" / "mission_manager_node.py").read_text()

    assert '"Station A"' in source
    assert '"Station B"' in source
    assert '"Station C"' in source
    assert '"WP1"' in source
    assert '"WP2"' in source
    assert '"WP3"' in source
