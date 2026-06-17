from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_vision_node_exposes_agreed_interfaces():
    source = (ROOT / "motivon_vision" / "vision_node.py").read_text()

    assert '"/vision/verify_identity"' in source
    assert '"/vision/status"' in source
    assert '"/vision/detection"' in source


def test_vision_node_uses_existing_realtime_camera_script():
    source = (ROOT / "motivon_vision" / "vision_node.py").read_text()

    assert "06_real_time_camera.py" in source
    assert "FaceRecognitionSystem" in source
