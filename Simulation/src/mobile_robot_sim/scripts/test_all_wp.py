#!/usr/bin/env python3
"""Wrapper for the canonical WP1 -> WP2 -> WP3 navigation test."""

from navigation_test_runner import main_for_route


def main():
    main_for_route("all_wp", "test_all_wp")


if __name__ == "__main__":
    main()
