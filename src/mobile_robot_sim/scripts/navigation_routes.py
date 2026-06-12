#!/usr/bin/env python3
"""Canonical navigation route table and coverage helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

HOME = (1.30, -1.50)
SPAWN_X = 1.30
SPAWN_Y = -1.50
SPAWN_YAW = math.pi / 2.0


@dataclass(frozen=True)
class RouteStep:
    name: str
    pose: Tuple[float, float]
    is_station: bool = False
    target_yaw: Optional[float] = None


@dataclass(frozen=True)
class RouteDefinition:
    route_id: str
    display_name: str
    steps: Tuple[RouteStep, ...]

    def segments(self) -> Tuple[Tuple[str, str], ...]:
        names = ["HOME"] + [step.name for step in self.steps]
        return tuple((names[idx], names[idx + 1]) for idx in range(len(names) - 1))


ROUTES: Dict[str, RouteDefinition] = {
    "wp1_return": RouteDefinition(
        route_id="wp1_return",
        display_name="HOME -> WP1 -> HOME",
        steps=(
            RouteStep("WP1", (1.30, -0.40), True),
            RouteStep("HOME", HOME),
        ),
    ),
    "wp2_return": RouteDefinition(
        route_id="wp2_return",
        display_name="HOME -> WP2a -> WP2b -> WP2 -> WP2b_ret -> WP2a_ret -> HOME",
        steps=(
            RouteStep("WP2a", (0.06, -1.50)),
            RouteStep("WP2b", (0.06, 0.20)),
            RouteStep("WP2", (-1.35, 0.20), True, 0.0),
            RouteStep("WP2b_ret", (0.06, 0.20)),
            RouteStep("WP2a_ret", (0.06, -1.50)),
            RouteStep("HOME", HOME, False, math.pi / 2.0),
        ),
    ),
    "wp3_return": RouteDefinition(
        route_id="wp3_return",
        display_name="HOME -> WP3a -> WP3 -> WP3b_ret -> WP3a_ret -> HOME",
        steps=(
            RouteStep("WP3a", (-0.20, -1.50)),
            RouteStep("WP3", (-0.20, 1.70), True, 0.0),
            RouteStep("WP3b_ret", (-0.20, 1.00)),
            RouteStep("WP3a_ret", (-0.20, -1.50)),
            RouteStep("HOME", HOME, False, math.pi / 2.0),
        ),
    ),
    "wp1_to_wp2": RouteDefinition(
        route_id="wp1_to_wp2",
        display_name="HOME -> WP1 -> WP12 -> WP2 -> WP2b_ret -> WP2a_ret -> HOME",
        steps=(
            RouteStep("WP1", (1.30, -0.40)),
            RouteStep("WP12", (-1.35, -0.40)),
            RouteStep("WP2", (-1.35, 0.20), True, 0.0),
            RouteStep("WP2b_ret", (0.06, 0.20)),
            RouteStep("WP2a_ret", (0.06, -1.50)),
            RouteStep("HOME", HOME, False, math.pi / 2.0),
        ),
    ),
    "wp1_to_wp3": RouteDefinition(
        route_id="wp1_to_wp3",
        display_name="HOME -> WP1 -> WP13 -> WP3 -> WP3b_ret -> WP3a_ret -> HOME",
        steps=(
            RouteStep("WP1", (1.30, -0.40)),
            RouteStep("WP13", (-0.20, -0.40)),
            RouteStep("WP3", (-0.20, 1.70), True, 0.0),
            RouteStep("WP3b_ret", (-0.20, 1.00)),
            RouteStep("WP3a_ret", (-0.20, -1.50)),
            RouteStep("HOME", HOME, False, math.pi / 2.0),
        ),
    ),
    "wp2_to_wp3": RouteDefinition(
        route_id="wp2_to_wp3",
        display_name="HOME -> WP2a -> WP2b -> WP2 -> WP23 -> WP3 -> WP3b_ret -> WP3a_ret -> HOME",
        steps=(
            RouteStep("WP2a", (0.06, -1.50)),
            RouteStep("WP2b", (0.06, 0.20)),
            RouteStep("WP2", (-1.35, 0.20)),
            RouteStep("WP23", (-0.20, 0.20)),
            RouteStep("WP3", (-0.20, 1.70), True, 0.0),
            RouteStep("WP3b_ret", (-0.20, 1.00)),
            RouteStep("WP3a_ret", (-0.20, -1.50)),
            RouteStep("HOME", HOME, False, math.pi / 2.0),
        ),
    ),
    "all_wp": RouteDefinition(
        route_id="all_wp",
        display_name="HOME -> WP1 -> WP12 -> WP2 -> WP23 -> WP3 -> WP3b_ret -> WP3a_ret -> HOME",
        steps=(
            RouteStep("WP1", (1.30, -0.40), True),
            RouteStep("WP12", (-1.35, -0.40)),
            RouteStep("WP2", (-1.35, 0.20), True),
            RouteStep("WP23", (-0.20, 0.20)),
            RouteStep("WP3", (-0.20, 1.70), True, 0.0),
            RouteStep("WP3b_ret", (-0.20, 1.00)),
            RouteStep("WP3a_ret", (-0.20, -1.50)),
            RouteStep("HOME", HOME, False, math.pi / 2.0),
        ),
    ),
}


def get_route(route_id: str) -> RouteDefinition:
    return ROUTES[route_id]


def iter_unique_segments() -> Iterable[Tuple[str, str]]:
    seen = set()
    for route in ROUTES.values():
        for segment in route.segments():
            if segment not in seen:
                seen.add(segment)
                yield segment

