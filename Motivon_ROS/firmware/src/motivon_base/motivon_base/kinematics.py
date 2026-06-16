from typing import Iterable, Tuple


def classify_sample_period(dt: float, maximum_sample_period: float) -> str:
    if dt <= 0.0:
        return "reset"
    if dt > maximum_sample_period:
        return "skip"
    return "integrate"


def data_is_stale(
    now_ns: int, last_receive_time_ns: int, stale_timeout_ns: int
) -> bool:
    return now_ns - last_receive_time_ns >= stale_timeout_ns


def mecanum_forward_kinematics(
    wheel_velocities: Iterable[float],
    wheel_radius: float,
    lx_plus_ly: float,
    x_scale: float = 1.0,
    y_scale: float = 1.0,
    yaw_scale: float = 1.0,
) -> Tuple[float, float, float]:
    fl, fr, rl, rr = wheel_velocities
    vx = wheel_radius * (fl + fr + rl + rr) / 4.0
    vy = wheel_radius * (-fl + fr + rl - rr) / 4.0
    wz = (
        wheel_radius
        * (-fl + fr - rl + rr)
        / (4.0 * lx_plus_ly)
    )
    return vx * x_scale, vy * y_scale, wz * yaw_scale


def mecanum_body_displacement(
    wheel_position_deltas: Iterable[float],
    wheel_radius: float,
    lx_plus_ly: float,
    x_scale: float = 1.0,
    y_scale: float = 1.0,
    yaw_scale: float = 1.0,
) -> Tuple[float, float, float]:
    return mecanum_forward_kinematics(
        wheel_position_deltas,
        wheel_radius,
        lx_plus_ly,
        x_scale,
        y_scale,
        yaw_scale,
    )
