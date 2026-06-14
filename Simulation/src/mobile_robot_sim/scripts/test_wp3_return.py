#!/usr/bin/env python3
"""Wrapper for the canonical HOME -> WP3 -> HOME navigation test."""

from navigation_test_runner import main_for_route


def main():
    main_for_route("wp3_return", "test_wp3_return")


if __name__ == "__main__":
    main()
