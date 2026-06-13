import math

from motivon_base.kinematics import mecanum_forward_kinematics


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
