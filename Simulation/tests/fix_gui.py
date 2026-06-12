#!/usr/bin/env python3
"""Remove -s flag from launch file to enable Gazebo GUI."""
path = "/home/zeinazz/design_ws/src/mobile_robot_sim/launch/robot_gazebo.launch.py"
with open(path, "r") as f:
    content = f.read()
content = content.replace("-r -s -v 4", "-r -v 4")
with open(path, "w") as f:
    f.write(content)
print("[OK] Removed -s flag — Gazebo GUI will now launch")
