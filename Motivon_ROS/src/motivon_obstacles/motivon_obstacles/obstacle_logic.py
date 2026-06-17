import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class DistanceSet:
    front: Optional[float] = None
    back: Optional[float] = None
    left: Optional[float] = None
    right: Optional[float] = None


@dataclass
class ObstacleDecision:
    state: str
    blocked: bool
    static_obstacle: bool
    blocked_direction: str
    recommended_detour_side: str
    blocked_duration_s: float
    detail: str


def finite_distance(value) -> Optional[float]:
    try:
        distance = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(distance) or distance <= 0.0:
        return None
    return distance


def command_direction(vx: float, vy: float, epsilon: float) -> str:
    if abs(vx) < epsilon and abs(vy) < epsilon:
        return ""
    if abs(vx) >= abs(vy):
        return "front" if vx > 0.0 else "back"
    return "left" if vy > 0.0 else "right"


def direction_distance(distances: DistanceSet, direction: str):
    return getattr(distances, direction, None)


def blocked_threshold(
    direction: str,
    front_blocked_cm: float,
    back_blocked_cm: float,
    side_blocked_cm: float,
) -> Optional[float]:
    if direction == "front":
        return front_blocked_cm
    if direction == "back":
        return back_blocked_cm
    if direction in ("left", "right"):
        return side_blocked_cm
    return None


def clear_threshold(
    direction: str,
    front_clear_cm: float,
    back_clear_cm: float,
    side_clear_cm: float,
) -> Optional[float]:
    if direction == "front":
        return front_clear_cm
    if direction == "back":
        return back_clear_cm
    if direction in ("left", "right"):
        return side_clear_cm
    return None


def recommend_detour_side(distances: DistanceSet, blocked_direction: str) -> str:
    if blocked_direction in ("front", "back"):
        left = finite_distance(distances.left)
        right = finite_distance(distances.right)
        if left is None and right is None:
            return ""
        if right is None or (left is not None and left >= right):
            return "left"
        return "right"
    if blocked_direction in ("left", "right"):
        front = finite_distance(distances.front)
        back = finite_distance(distances.back)
        if front is None and back is None:
            return ""
        if back is None or (front is not None and front >= back):
            return "front"
        return "back"
    return ""


def classify_obstacle(
    *,
    data_valid: bool,
    active_direction: str,
    distances: DistanceSet,
    currently_blocked: bool,
    blocked_direction: str,
    blocked_duration_s: float,
    release_ready: bool,
    static_wait_s: float,
    front_blocked_cm: float,
    front_clear_cm: float,
    back_blocked_cm: float,
    back_clear_cm: float,
    side_blocked_cm: float,
    side_clear_cm: float,
) -> ObstacleDecision:
    if not data_valid:
        return ObstacleDecision(
            "STALE",
            True,
            False,
            blocked_direction,
            "",
            blocked_duration_s,
            "Obstacle scan data is stale.",
        )

    direction = blocked_direction if currently_blocked else active_direction
    if not direction:
        return ObstacleDecision("CLEAR", False, False, "", "", 0.0, "No autonomous translation command.")

    value = direction_distance(distances, direction)
    if value is None:
        return ObstacleDecision(
            "STALE",
            True,
            False,
            direction,
            "",
            blocked_duration_s,
            f"No valid {direction} obstacle distance.",
        )

    if currently_blocked:
        clear_cm = clear_threshold(
            direction, front_clear_cm, back_clear_cm, side_clear_cm
        )
        if clear_cm is not None and value >= clear_cm and release_ready:
            return ObstacleDecision(
                "CLEAR",
                False,
                False,
                "",
                "",
                0.0,
                f"{direction} obstacle cleared at {value:.1f} cm.",
            )

        is_static = blocked_duration_s >= static_wait_s
        if is_static:
            return ObstacleDecision(
                "BLOCKED_STATIC",
                True,
                True,
                direction,
                recommend_detour_side(distances, direction),
                blocked_duration_s,
                (
                    f"{direction} obstacle treated as static after "
                    f"{blocked_duration_s:.1f} s."
                ),
            )

        return ObstacleDecision(
            "BLOCKED_DYNAMIC",
            True,
            False,
            direction,
            recommend_detour_side(distances, direction),
            blocked_duration_s,
            f"{direction} obstacle still present at {value:.1f} cm.",
        )

    threshold = blocked_threshold(
        direction, front_blocked_cm, back_blocked_cm, side_blocked_cm
    )
    if threshold is not None and value <= threshold:
        return ObstacleDecision(
            "BLOCKED_DYNAMIC",
            True,
            False,
            direction,
            recommend_detour_side(distances, direction),
            0.0,
            f"{direction} obstacle detected at {value:.1f} cm.",
        )

    return ObstacleDecision(
        "CLEAR",
        False,
        False,
        "",
        "",
        0.0,
        f"{direction} clear at {value:.1f} cm.",
    )
