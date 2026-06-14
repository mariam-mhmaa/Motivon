#!/usr/bin/env python3
"""Wrapper for the canonical WP1 -> WP3 navigation test."""

from navigation_test_runner import main_for_route


def main():
    main_for_route("wp1_to_wp3", "test_wp1_to_wp3")


if __name__ == "__main__":
    main()
