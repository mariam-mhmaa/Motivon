import math

from motivon_navigation.geometry import HomeTransform, Pose2D


def test_home_transform_maps_odom_home_to_corner_based_home():
    transform = HomeTransform(
        map_home=Pose2D(0.65, 0.65, 0.0),
        odom_home=Pose2D(4.0, -2.0, 0.4),
    )

    mapped = transform.odom_to_map(Pose2D(4.0, -2.0, 0.4))

    assert math.isclose(mapped.x, 0.65)
    assert math.isclose(mapped.y, 0.65)
    assert math.isclose(mapped.yaw, 0.0, abs_tol=1.0e-12)


def test_home_transform_rotates_odom_displacement_into_map_frame():
    transform = HomeTransform(
        map_home=Pose2D(0.65, 0.65, 0.0),
        odom_home=Pose2D(0.0, 0.0, math.pi / 2.0),
    )

    mapped = transform.odom_to_map(Pose2D(0.0, 1.0, math.pi / 2.0))

    assert math.isclose(mapped.x, 1.65, abs_tol=1.0e-12)
    assert math.isclose(mapped.y, 0.65, abs_tol=1.0e-12)
    assert math.isclose(mapped.yaw, 0.0, abs_tol=1.0e-12)
