#!/usr/bin/env python3
"""Standalone HC-SR04 GPIO test for the Motivon ultrasonic sensors.

This script does not use ROS. Run it on the Raspberry Pi to verify the
trigger/echo wiring and sensor readings directly.
"""

import argparse
import math
import time

try:
    import lgpio
except ImportError as exc:
    raise SystemExit(
        "Missing lgpio. Install it on the Pi with: sudo apt install python3-lgpio"
    ) from exc


SPEED_OF_SOUND_CM_S = 34300.0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Standalone ultrasonic sensor GPIO test."
    )
    parser.add_argument("--chip", type=int, default=4, help="GPIO chip number.")
    parser.add_argument("--trigger", type=int, default=17, help="Trigger GPIO pin.")
    parser.add_argument("--left", type=int, default=27, help="Left echo GPIO pin.")
    parser.add_argument("--right", type=int, default=22, help="Right echo GPIO pin.")
    parser.add_argument("--front", type=int, default=23, help="Front echo GPIO pin.")
    parser.add_argument("--back", type=int, default=24, help="Back echo GPIO pin.")
    parser.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Number of measurement cycles. 0 means run forever.",
    )
    parser.add_argument(
        "--period",
        type=float,
        default=0.5,
        help="Seconds between measurement cycles.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.04,
        help="Echo wait timeout in seconds.",
    )
    return parser.parse_args()


def wait_all_low(handle, echo_pins, timeout_s=0.01):
    end_time = time.monotonic() + timeout_s
    while time.monotonic() < end_time:
        if all(lgpio.gpio_read(handle, pin) == 0 for pin in echo_pins.values()):
            return True
    return False


def trigger_pulse(handle, trigger_pin):
    lgpio.gpio_write(handle, trigger_pin, 0)
    time.sleep(0.000002)
    lgpio.gpio_write(handle, trigger_pin, 1)
    time.sleep(0.000010)
    lgpio.gpio_write(handle, trigger_pin, 0)


def read_echoes(handle, trigger_pin, echo_pins, timeout_s):
    if not wait_all_low(handle, echo_pins):
        return {
            name: {
                "distance_cm": None,
                "reason": "echo_stuck_high_before_trigger",
            }
            for name in echo_pins
        }

    trigger_pulse(handle, trigger_pin)

    started_at = {name: None for name in echo_pins}
    finished_at = {name: None for name in echo_pins}
    pending = set(echo_pins)
    end_time = time.monotonic() + timeout_s

    while pending and time.monotonic() <= end_time:
        now = time.monotonic()
        for name in tuple(pending):
            level = lgpio.gpio_read(handle, echo_pins[name])
            if started_at[name] is None:
                if level == 1:
                    started_at[name] = now
            elif level == 0:
                finished_at[name] = now
                pending.remove(name)

    results = {}
    for name in echo_pins:
        start = started_at[name]
        finish = finished_at[name]
        if start is None:
            results[name] = {"distance_cm": None, "reason": "no_rising_echo"}
        elif finish is None:
            results[name] = {"distance_cm": None, "reason": "no_falling_echo"}
        else:
            duration_s = finish - start
            distance_cm = duration_s * SPEED_OF_SOUND_CM_S / 2.0
            if math.isfinite(distance_cm) and distance_cm > 0.0:
                results[name] = {"distance_cm": distance_cm, "reason": "ok"}
            else:
                results[name] = {"distance_cm": None, "reason": "invalid_duration"}
    return results


def format_result(result):
    distance = result["distance_cm"]
    if distance is None:
        return f"---- ({result['reason']})"
    return f"{distance:6.1f} cm"


def main():
    args = parse_args()
    echo_pins = {
        "front": args.front,
        "left": args.left,
        "right": args.right,
        "back": args.back,
    }

    print("Motivon standalone ultrasonic GPIO test")
    print(f"GPIO chip: {args.chip}")
    print(f"Trigger GPIO: {args.trigger}")
    print(
        "Echo GPIOs: "
        + ", ".join(f"{name}={pin}" for name, pin in echo_pins.items())
    )
    print("Press Ctrl+C to stop.")

    handle = lgpio.gpiochip_open(args.chip)
    try:
        lgpio.gpio_claim_output(handle, args.trigger, 0)
        for pin in echo_pins.values():
            lgpio.gpio_claim_input(handle, pin)

        cycle = 0
        while args.cycles == 0 or cycle < args.cycles:
            cycle += 1
            results = read_echoes(handle, args.trigger, echo_pins, args.timeout)
            print(
                f"{cycle:04d} | "
                f"F={format_result(results['front'])} | "
                f"L={format_result(results['left'])} | "
                f"R={format_result(results['right'])} | "
                f"B={format_result(results['back'])}"
            )
            time.sleep(args.period)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        lgpio.gpio_write(handle, args.trigger, 0)
        lgpio.gpiochip_close(handle)


if __name__ == "__main__":
    main()
