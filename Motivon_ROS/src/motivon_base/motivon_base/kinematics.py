from typing import Iterable, Tuple


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
