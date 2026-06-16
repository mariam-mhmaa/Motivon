import math

from motivon_base.kinematics import (
    classify_sample_period,
    data_is_stale,
    mecanum_body_displacement,
    mecanum_forward_kinematics,
)


RADIUS = 0.0485
K = (0.395 / 2.0) + (0.4545 / 2.0)


def test_forward_motion():
    vx, vy, wz = mecanum_forward_kinematics(
        [2.0, 2.0, 2.0, 2.0], RADIUS, K
    )
    assert math.isclose(vx, 2.0 * RADIUS)
    assert math.isclose(vy, 0.0, abs_tol=1.0e-12)
    assert math.isclose(wz, 0.0, abs_tol=1.0e-12)


def test_left_strafe_motion():
    vx, vy, wz = mecanum_forward_kinematics(
        [-2.0, 2.0, 2.0, -2.0], RADIUS, K
    )
    assert math.isclose(vx, 0.0, abs_tol=1.0e-12)
    assert math.isclose(vy, 2.0 * RADIUS)
    assert math.isclose(wz, 0.0, abs_tol=1.0e-12)


def test_counterclockwise_rotation():
    vx, vy, wz = mecanum_forward_kinematics(
        [-2.0, 2.0, -2.0, 2.0], RADIUS, K
    )
    assert math.isclose(vx, 0.0, abs_tol=1.0e-12)
    assert math.isclose(vy, 0.0, abs_tol=1.0e-12)
    assert wz > 0.0


def test_calibration_scales_apply_per_axis():
    vx, vy, wz = mecanum_forward_kinematics(
        [-2.0, 2.0, 2.0, -2.0],
        RADIUS,
        K,
        x_scale=1.0,
        y_scale=0.948,
        yaw_scale=1.0,
    )
    assert math.isclose(vx, 0.0, abs_tol=1.0e-12)
    assert math.isclose(vy, 2.0 * RADIUS * 0.948)
    assert math.isclose(wz, 0.0, abs_tol=1.0e-12)


def test_sample_period_policy():
    assert classify_sample_period(0.04, 0.25) == "integrate"
    assert classify_sample_period(0.50, 0.25) == "skip"
    assert classify_sample_period(0.0, 0.25) == "reset"
    assert classify_sample_period(-0.01, 0.25) == "reset"


def test_stale_data_policy():
    assert not data_is_stale(1_199_999_999, 1_000_000_000, 200_000_000)
    assert data_is_stale(1_200_000_000, 1_000_000_000, 200_000_000)


def test_encoder_position_deltas_recover_displacement():
    dx, dy, dyaw = mecanum_body_displacement(
        [2.0, 2.0, 2.0, 2.0], RADIUS, K
    )
    assert math.isclose(dx, 2.0 * RADIUS)
    assert math.isclose(dy, 0.0, abs_tol=1.0e-12)
    assert math.isclose(dyaw, 0.0, abs_tol=1.0e-12)
