from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "motivon_control"
    / "cmd_vel_gate_node.py"
)


def test_gate_allows_static_obstacle_only_during_navigation_detour():
    source = SOURCE.read_text(encoding="utf-8")

    assert '"/navigation/status"' in source
    assert "self.navigation_state == \"DETOURING\"" in source
    assert "self.obstacle_static" in source
    assert "self.obstacle_blocks_auto" in source
