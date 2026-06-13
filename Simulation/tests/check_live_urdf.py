#!/usr/bin/env python3
"""Check the live URDF parameter for Lid_Joint command interface."""
import subprocess, os

# Get robot_description parameter
result = subprocess.run(
    ['ros2', 'param', 'get', '/robot_state_publisher', 'robot_description'],
    capture_output=True, text=True, timeout=10
)
txt = result.stdout

# Find all Lid_Joint mentions
idx = txt.find('Lid_Joint')
while idx >= 0:
    start = max(0, idx - 50)
    end = min(len(txt), idx + 100)
    snippet = txt[start:end]
    print(repr(snippet))
    print('---')
    idx = txt.find('Lid_Joint', idx + 1)

# Also check command_interface near Lid_Joint in ros2_control section
idx2 = txt.find('ros2_control')
if idx2 >= 0:
    section = txt[idx2:idx2+2000]
    lid_idx = section.find('Lid_Joint')
    if lid_idx >= 0:
        print("=== ros2_control Lid_Joint section ===")
        print(section[lid_idx:lid_idx+200])
