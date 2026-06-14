#!/usr/bin/env python3
"""Wrapper for the canonical HOME -> WP2 -> HOME navigation test."""

from navigation_test_runner import main_for_route


def main():
    main_for_route("wp2_return", "test_wp2_return")


if __name__ == "__main__":
    main()
