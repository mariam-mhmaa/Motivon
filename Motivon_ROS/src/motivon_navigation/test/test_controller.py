import math

from motivon_navigation.controller import (
    ControllerSettings,
    limit_vector,
    tracking_command,
)
from motivon_navigation.geometry import Pose2D
from motivon_navigation.route_config import Waypoint


SETTINGS = ControllerSettings(
    maximum_speed=0.08,
    maximum_cross_track_speed=0.05,
    maximum_turn_rate=0.30,
    along_track_gain=0.80,
    cross_track_gain=1.00,
    final_position_gain=0.80,
    yaw_hold_gain=1.50,
    final_approach_radius=0.30,
)


def point(name, x, y):
    return Waypoint(name=name, x=x, y=y, role="connector")


def test_forward_segment_commands_forward_motion():
    result = tracking_command(
        Pose2D(0.65, 0.65, 0.0),
        point("HOME", 0.65, 0.65),
        point("WP1", 1.75, 0.65),
        0.0,
        SETTINGS,
    )

    assert result.body_vx > 0.0
    assert math.isclose(result.body_vy, 0.0, abs_tol=1.0e-12)
    assert math.isclose(result.angular_z, 0.0, abs_tol=1.0e-12)


def test_cross_track_error_commands_back_to_route_line():
    result = tracking_command(
        Pose2D(1.0, 0.75, 0.0),
        point("HOME", 0.65, 0.65),
        point("WP1", 1.75, 0.65),
        0.0,
        SETTINGS,
    )

    assert result.cross_track_error > 0.0
    assert result.body_vy < 0.0


def test_vector_limit_prevents_faster_diagonal_command():
    x, y = limit_vector(0.08, 0.08, 0.08)

    assert math.isclose(math.hypot(x, y), 0.08)


def test_return_translation_uses_robot_forward_after_180_degree_turn():
    result = tracking_command(
        Pose2D(3.85, 2.15, math.pi),
        point("WP3", 3.85, 2.15),
        point("WP3b_ret", 3.15, 2.15),
        math.pi,
        SETTINGS,
    )

    assert result.body_vx > 0.0
    assert math.isclose(result.body_vy, 0.0, abs_tol=1.0e-12)


def test_near_target_controller_corrects_both_position_axes():
    result = tracking_command(
        Pose2D(1.72, 0.67, 0.0),
        point("HOME", 0.65, 0.65),
        point("WP1", 1.75, 0.65),
        0.0,
        SETTINGS,
    )

    assert result.body_vx > 0.0
    assert result.body_vy < 0.0
    assert result.distance < SETTINGS.final_approach_radius
