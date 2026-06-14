#!/usr/bin/env python3
"""Check xacro output for Lid_Joint command interface."""
import subprocess, re, os
os.environ.setdefault('ROS_DISTRO', 'jazzy')

result = subprocess.run(
    ['xacro', '/home/zeinazz/design_ws/src/mobile_robot_sim/urdf/DeliveryRobot_2.urdf'],
    capture_output=True, text=True, timeout=10
)
txt = result.stdout
if result.returncode != 0:
    print("Xacro error:", result.stderr)
else:
    # Find all Lid_Joint references
    for m in re.finditer(r'Lid_Joint.{0,200}', txt):
        print(m.group())
        print('---')
