import math
from pathlib import Path

from motivon_navigation.route_config import load_route_map


CONFIG = Path(__file__).resolve().parents[1] / "config" / "routes.yaml"


def test_corner_based_route_matches_confirmed_measurements():
    route_map = load_route_map(str(CONFIG))

    assert route_map.width_m == 4.5
    assert route_map.height_m == 4.5
    assert (route_map.home.x, route_map.home.y) == (0.65, 0.65)
    assert (
        route_map.waypoints["WP3"].x,
        route_map.waypoints["WP3"].y,
    ) == (3.85, 2.15)


def test_fixed_route_segments_and_return_rotations():
    route_map = load_route_map(str(CONFIG))

    assert route_map.path_between("HOME", "WP1").waypoint_names == ["WP1"]
    assert not route_map.path_between(
        "HOME", "WP1"
    ).align_before_travel
    wp1_to_wp2 = route_map.path_between("WP1", "WP2")
    assert not wp1_to_wp2.align_before_travel
    assert wp1_to_wp2.waypoint_names == [
        "WP12",
        "WP2",
    ]
    assert not route_map.path_between(
        "WP2", "WP3"
    ).align_before_travel
    assert math.isclose(
        route_map.path_between("WP2", "WP3").final_yaw, math.pi
    )
    return_path = route_map.path_between("WP3", "HOME")
    assert return_path.waypoint_names == [
        "WP3b_ret",
        "WP3a_ret",
        "HOME",
    ]
    assert return_path.align_before_travel
    assert math.isclose(return_path.travel_yaw, math.pi)
    assert math.isclose(return_path.final_yaw, 0.0)
