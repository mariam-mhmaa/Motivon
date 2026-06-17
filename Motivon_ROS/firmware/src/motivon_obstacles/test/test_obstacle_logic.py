from motivon_obstacles.obstacle_logic import (
    DistanceSet,
    classify_obstacle,
    command_direction,
    recommend_detour_side,
)


THRESHOLDS = {
    "static_wait_s": 10.0,
    "front_blocked_cm": 22.0,
    "front_clear_cm": 40.0,
    "back_blocked_cm": 22.0,
    "back_clear_cm": 40.0,
    "side_blocked_cm": 22.0,
    "side_clear_cm": 40.0,
}


def decision(**kwargs):
    defaults = {
        "data_valid": True,
        "active_direction": "front",
        "distances": DistanceSet(front=100.0, back=100.0, left=80.0, right=60.0),
        "currently_blocked": False,
        "blocked_direction": "",
        "blocked_duration_s": 0.0,
        "release_ready": False,
    }
    defaults.update(kwargs)
    return classify_obstacle(**defaults, **THRESHOLDS)


def test_command_direction_uses_largest_translation_component():
    assert command_direction(0.10, 0.02, 0.02) == "front"
    assert command_direction(-0.10, 0.02, 0.02) == "back"
    assert command_direction(0.02, 0.10, 0.02) == "left"
    assert command_direction(0.02, -0.10, 0.02) == "right"
    assert command_direction(0.0, 0.0, 0.02) == ""


def test_front_obstacle_stops_as_dynamic_first():
    result = decision(distances=DistanceSet(front=18.0, left=80.0, right=60.0))

    assert result.state == "BLOCKED_DYNAMIC"
    assert result.blocked
    assert not result.static_obstacle
    assert result.blocked_direction == "front"
    assert result.recommended_detour_side == "left"


def test_persistent_obstacle_becomes_static():
    result = decision(
        distances=DistanceSet(front=18.0, left=50.0, right=90.0),
        currently_blocked=True,
        blocked_direction="front",
        blocked_duration_s=10.5,
    )

    assert result.state == "BLOCKED_STATIC"
    assert result.static_obstacle
    assert result.recommended_detour_side == "right"


def test_blocked_obstacle_resumes_after_confirmed_clear():
    result = decision(
        distances=DistanceSet(front=45.0, left=50.0, right=90.0),
        currently_blocked=True,
        blocked_direction="front",
        blocked_duration_s=2.0,
        release_ready=True,
    )

    assert result.state == "CLEAR"
    assert not result.blocked


def test_static_obstacle_clears_after_confirmed_release():
    result = decision(
        distances=DistanceSet(front=80.0, left=50.0, right=90.0),
        currently_blocked=True,
        blocked_direction="front",
        blocked_duration_s=12.0,
        release_ready=True,
    )

    assert result.state == "CLEAR"
    assert not result.blocked


def test_stale_scan_blocks_autonomous_motion():
    result = decision(data_valid=False)

    assert result.state == "STALE"
    assert result.blocked


def test_side_obstacle_recommends_front_or_back_detour():
    distances = DistanceSet(front=120.0, back=70.0, left=15.0, right=90.0)

    assert recommend_detour_side(distances, "left") == "front"
