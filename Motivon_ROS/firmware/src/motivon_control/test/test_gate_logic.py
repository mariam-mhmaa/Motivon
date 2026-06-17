from motivon_control.gate_logic import choose_gate_state


def test_auto_uses_navigation_when_clear_and_fresh():
    result = choose_gate_state(
        mode="AUTO",
        safety_stop=False,
        obstacle_blocks_auto=False,
        navigation_fresh=True,
        manual_fresh=True,
    )

    assert result.source == "navigation"


def test_auto_stops_for_obstacle():
    result = choose_gate_state(
        mode="AUTO",
        safety_stop=False,
        obstacle_blocks_auto=True,
        navigation_fresh=True,
        manual_fresh=True,
    )

    assert result.source == "zero"
    assert result.reason == "obstacle_blocking_auto"


def test_manual_bypasses_obstacle_blocking():
    result = choose_gate_state(
        mode="MANUAL",
        safety_stop=False,
        obstacle_blocks_auto=True,
        navigation_fresh=True,
        manual_fresh=True,
    )

    assert result.source == "manual"


def test_safety_stop_overrides_manual():
    result = choose_gate_state(
        mode="MANUAL",
        safety_stop=True,
        obstacle_blocks_auto=False,
        navigation_fresh=True,
        manual_fresh=True,
    )

    assert result.source == "zero"
    assert result.reason == "safety_stop"
