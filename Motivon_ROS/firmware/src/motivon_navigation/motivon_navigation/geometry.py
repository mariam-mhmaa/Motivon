import math
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Pose2D:
    x: float
    y: float
    yaw: float


def normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def rotate_xy(x: float, y: float, yaw: float) -> Tuple[float, float]:
    cosine = math.cos(yaw)
    sine = math.sin(yaw)
    return cosine * x - sine * y, sine * x + cosine * y


@dataclass(frozen=True)
class HomeTransform:
    map_home: Pose2D
    odom_home: Pose2D

    @property
    def yaw_offset(self) -> float:
        return normalize_angle(self.map_home.yaw - self.odom_home.yaw)

    def odom_to_map(self, pose: Pose2D) -> Pose2D:
        delta_x = pose.x - self.odom_home.x
        delta_y = pose.y - self.odom_home.y
        map_dx, map_dy = rotate_xy(delta_x, delta_y, self.yaw_offset)
        return Pose2D(
            self.map_home.x + map_dx,
            self.map_home.y + map_dy,
            normalize_angle(pose.yaw + self.yaw_offset),
        )
