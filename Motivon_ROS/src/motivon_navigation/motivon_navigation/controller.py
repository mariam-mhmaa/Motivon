import math
from dataclasses import dataclass
from typing import Tuple

from motivon_navigation.geometry import Pose2D, normalize_angle, rotate_xy
from motivon_navigation.route_config import Waypoint


@dataclass(frozen=True)
class ControllerSettings:
    maximum_speed: float
    maximum_cross_track_speed: float
    maximum_turn_rate: float
    along_track_gain: float
    cross_track_gain: float
    final_position_gain: float
    yaw_hold_gain: float
    final_approach_radius: float


@dataclass(frozen=True)
class TrackingResult:
    body_vx: float
    body_vy: float
    angular_z: float
    distance: float
    cross_track_error: float
    yaw_error: float


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def limit_vector(x: float, y: float, maximum: float) -> Tuple[float, float]:
    magnitude = math.hypot(x, y)
    if magnitude <= maximum or magnitude == 0.0:
        return x, y
    scale = maximum / magnitude
    return x * scale, y * scale


def cross_track_error(
    pose: Pose2D, start: Waypoint, target: Waypoint
) -> float:
    segment_x = target.x - start.x
    segment_y = target.y - start.y
    length = math.hypot(segment_x, segment_y)
    if length == 0.0:
        return 0.0
    normal_x = -segment_y / length
    normal_y = segment_x / length
    return (
        (pose.x - start.x) * normal_x
        + (pose.y - start.y) * normal_y
    )


def tracking_command(
    pose: Pose2D,
    start: Waypoint,
    target: Waypoint,
    travel_yaw: float,
    settings: ControllerSettings,
) -> TrackingResult:
    error_x = target.x - pose.x
    error_y = target.y - pose.y
    distance = math.hypot(error_x, error_y)
    cross_error = cross_track_error(pose, start, target)

    if distance <= settings.final_approach_radius:
        map_vx = settings.final_position_gain * error_x
        map_vy = settings.final_position_gain * error_y
    else:
        segment_x = target.x - start.x
        segment_y = target.y - start.y
        segment_length = math.hypot(segment_x, segment_y)
        if segment_length == 0.0:
            map_vx = settings.final_position_gain * error_x
            map_vy = settings.final_position_gain * error_y
        else:
            unit_x = segment_x / segment_length
            unit_y = segment_y / segment_length
            normal_x = -unit_y
            normal_y = unit_x
            along_error = error_x * unit_x + error_y * unit_y
            along_speed = settings.along_track_gain * along_error
            cross_speed = clamp(
                -settings.cross_track_gain * cross_error,
                -settings.maximum_cross_track_speed,
                settings.maximum_cross_track_speed,
            )
            map_vx = along_speed * unit_x + cross_speed * normal_x
            map_vy = along_speed * unit_y + cross_speed * normal_y

    map_vx, map_vy = limit_vector(
        map_vx, map_vy, settings.maximum_speed
    )
    body_vx, body_vy = rotate_xy(map_vx, map_vy, -pose.yaw)
    yaw_error = normalize_angle(travel_yaw - pose.yaw)
    angular_z = clamp(
        settings.yaw_hold_gain * yaw_error,
        -settings.maximum_turn_rate,
        settings.maximum_turn_rate,
    )
    return TrackingResult(
        body_vx=body_vx,
        body_vy=body_vy,
        angular_z=angular_z,
        distance=distance,
        cross_track_error=cross_error,
        yaw_error=yaw_error,
    )
