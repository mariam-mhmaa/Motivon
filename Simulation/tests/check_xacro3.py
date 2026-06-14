#!/usr/bin/env python3
"""Check xacro output for ACTUAL ros2_control hardware block."""
import subprocess

result = subprocess.run(
    ['xacro', '/home/zeinazz/design_ws/src/mobile_robot_sim/urdf/DeliveryRobot_2.urdf'],
    capture_output=True, text=True, timeout=10
)
txt = result.stdout

# Find <ros2_control tag (not comment)
idx = txt.find('<ros2_control ')
if idx >= 0:
    end = txt.find('</ros2_control>', idx)
    if end >= 0:
        print(txt[idx:end+16])
    else:
        print(txt[idx:idx+500])
else:
    print("No <ros2_control> block found!")
    # Check if it's there as comment
    if 'ros2_control' in txt:
        print("Found 'ros2_control' in text but not as XML tag")
