#!/usr/bin/env python3
"""Reduce delay timers since no spawners to wait for."""
BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"
lf = BASE + "/launch/robot_gazebo.launch.py"

with open(lf, "r") as f:
    content = f.read()

# Reduce delays - controllers auto-load, just need Gazebo to start (~5s)
content = content.replace("period=18.0, actions=[mecanum_drive_node]", 
                          "period=8.0, actions=[mecanum_drive_node]")
content = content.replace("period=18.0, actions=[lid_control_node]",
                          "period=8.0, actions=[lid_control_node]")
content = content.replace("period=18.0, actions=[start_stop_node]",
                          "period=8.0, actions=[start_stop_node]")

with open(lf, "w") as f:
    f.write(content)

print("[OK] Reduced node delays to 8s")
