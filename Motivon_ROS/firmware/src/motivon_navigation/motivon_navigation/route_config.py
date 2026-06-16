import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Waypoint:
    name: str
    x: float
    y: float
    role: str


@dataclass(frozen=True)
class RoutePath:
    name: str
    start: str
    target: str
    travel_yaw: float
    align_before_travel: bool
    final_yaw: Optional[float]
    waypoint_names: List[str]


@dataclass(frozen=True)
class RouteMap:
    frame_id: str
    width_m: float
    height_m: float
    waypoints: Dict[str, Waypoint]
    paths: Dict[str, RoutePath]

    @property
    def home(self) -> Waypoint:
        return self.waypoints["HOME"]

    def path_between(self, start: str, target: str) -> RoutePath:
        matches = [
            path
            for path in self.paths.values()
            if path.start == start and path.target == target
        ]
        if len(matches) != 1:
            raise KeyError(f"No unique route from {start} to {target}.")
        return matches[0]


def _degrees_or_none(value) -> Optional[float]:
    if value is None:
        return None
    return math.radians(float(value))


def load_route_map(path: str) -> RouteMap:
    import yaml

    route_path = Path(path)
    with route_path.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)

    map_data = document["map"]
    width = float(map_data["width_m"])
    height = float(map_data["height_m"])
    if width <= 0.0 or height <= 0.0:
        raise ValueError("Map dimensions must be positive.")

    waypoints = {}
    for name, data in document["waypoints"].items():
        waypoint = Waypoint(
            name=name,
            x=float(data["x"]),
            y=float(data["y"]),
            role=str(data["role"]),
        )
        if not (0.0 <= waypoint.x <= width and 0.0 <= waypoint.y <= height):
            raise ValueError(f"Waypoint {name} is outside the map.")
        waypoints[name] = waypoint

    if "HOME" not in waypoints or waypoints["HOME"].role != "home":
        raise ValueError("A HOME waypoint with role 'home' is required.")

    paths = {}
    for name, data in document["paths"].items():
        start = str(data["from"])
        target = str(data["to"])
        names = [str(value) for value in data["via"]]
        align_before_travel = data.get("align_before_travel", True)
        if not isinstance(align_before_travel, bool):
            raise ValueError(
                f"Path {name} align_before_travel must be boolean."
            )
        referenced = [start, target] + names
        missing = [value for value in referenced if value not in waypoints]
        if missing:
            raise ValueError(f"Path {name} references {missing}.")
        if not names or names[-1] != target:
            raise ValueError(f"Path {name} must end at {target}.")
        paths[name] = RoutePath(
            name=name,
            start=start,
            target=target,
            travel_yaw=math.radians(float(data["travel_yaw_deg"])),
            align_before_travel=align_before_travel,
            final_yaw=_degrees_or_none(data.get("final_yaw_deg")),
            waypoint_names=names,
        )

    return RouteMap(
        frame_id=str(map_data["frame_id"]),
        width_m=width,
        height_m=height,
        waypoints=waypoints,
        paths=paths,
    )
