#!/usr/bin/env python3
"""Fix launch file on disk."""
import re

path = '/home/zeinazz/design_ws/src/mobile_robot_sim/launch/robot_gazebo.launch.py'
with open(path, 'r') as f:
    content = f.read()

# Replace controller name
content = content.replace("arguments=['mecanum_drive_controller']", "arguments=['wheel_velocity_controller']")

# Fix timer delays
content = content.replace("period=3.0, actions=[jsb_spawner]", "period=8.0, actions=[jsb_spawner]")
content = content.replace("period=6.0, actions=[mecanum_spawner]", "period=12.0, actions=[mecanum_spawner]")
content = content.replace("period=9.0, actions=[lid_spawner]", "period=15.0, actions=[lid_spawner]")
content = content.replace("period=10.0, actions=[mecanum_drive_node]", "period=18.0, actions=[mecanum_drive_node]")
content = content.replace("period=12.0, actions=[obstacle_avoidance_node]", "period=20.0, actions=[obstacle_avoidance_node]")
content = content.replace("period=14.0, actions=[goal_sender_node]", "period=22.0, actions=[goal_sender_node]")
content = content.replace("period=10.0, actions=[lid_control_node]", "period=18.0, actions=[lid_control_node]")
content = content.replace("period=10.0, actions=[start_stop_node]", "period=18.0, actions=[start_stop_node]")

with open(path, 'w') as f:
    f.write(content)

print("Launch file fixed!")

# Verify
with open(path, 'r') as f:
    for i, line in enumerate(f, 1):
        if 'wheel_velocity' in line or ('period=' in line and 'actions=' in line):
            print(f"  Line {i}: {line.rstrip()}")
