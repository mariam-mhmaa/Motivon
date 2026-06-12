#!/usr/bin/env python3
"""Wrapper for the canonical HOME -> WP1 -> HOME navigation test."""

from navigation_test_runner import main_for_route


def main():
    main_for_route("wp1_return", "test_wp1_return")


if __name__ == "__main__":
    main()
