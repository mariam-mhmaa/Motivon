from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bridge_exposes_http_and_websocket_routes():
    source = (ROOT / "motivon_gui_bridge" / "gui_bridge_node.py").read_text()

    assert '"/api/status"' in source
    assert '"/api/mission/start"' in source
    assert '"/api/mission/confirm-user-verified"' in source
    assert '"/ws/status"' in source
