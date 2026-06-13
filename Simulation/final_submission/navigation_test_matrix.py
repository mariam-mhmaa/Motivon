#!/usr/bin/env python3
"""Print the canonical navigation routes and unique segment coverage."""

from navigation_routes import ROUTES, iter_unique_segments


def main():
    print("Navigation routes:")
    for route in ROUTES.values():
        names = ["HOME"] + [step.name for step in route.steps]
        print(f"- {route.route_id}: {' -> '.join(names)}")

    print("\nUnique segments:")
    for start, end in iter_unique_segments():
        print(f"- {start} -> {end}")


if __name__ == "__main__":
    main()
