#!/usr/bin/env python3
"""Check xacro output for ros2_control section."""
import subprocess

result = subprocess.run(
    ['xacro', '/home/zeinazz/design_ws/src/mobile_robot_sim/urdf/DeliveryRobot_2.urdf'],
    capture_output=True, text=True, timeout=10
)
txt = result.stdout

# Extract ros2_control section
idx = txt.find('ros2_control')
if idx >= 0:
    end = txt.find('/ros2_control', idx)
    if end >= 0:
        print(txt[idx-5:end+20])
    else:
        print(txt[idx-5:idx+500])
else:
    print("No ros2_control found in xacro output")
    print("Full output length:", len(txt))
    if len(txt) < 100:
        print(txt)
