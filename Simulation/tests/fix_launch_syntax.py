#!/usr/bin/env python3
"""Fix the mangled launch file."""

BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"
lf = BASE + "/launch/robot_gazebo.launch.py"

with open(lf, "r") as f:
    content = f.read()

# Fix 1: obstacle_avoidance node block - remove the mangled TimerAction
content = content.replace(
    "    )_avoidance = TimerAction(period=20.0, actions=[obstacle_avoidance_node])",
    "    )"
)

# Fix 2: goal_sender node block - remove the mangled TimerAction  
content = content.replace(
    "    )_sender = TimerAction(period=22.0, actions=[goal_sender_node])",
    "    )"
)

# Fix 3: the return list - replace mangled combined name with just delay_mecanum_drive
content = content.replace(
    "delay_mecanum_drive_avoidance_sender,",
    "delay_mecanum_drive,"
)

with open(lf, "w") as f:
    f.write(content)

# Verify syntax
import py_compile
try:
    py_compile.compile(lf, doraise=True)
    print("[OK] Launch file syntax is valid")
except py_compile.PyCompileError as e:
    print(f"[ERROR] Still has syntax error: {e}")

# Show the key parts
with open(lf, "r") as f:
    lines = f.readlines()
print("\n=== Lines 126-130 (obstacle avoidance node) ===")
for i in range(125, min(130, len(lines))):
    print(f"  {i+1}: {lines[i].rstrip()}")
print("\n=== Lines 135-140 (goal sender node) ===")
for i in range(134, min(140, len(lines))):
    print(f"  {i+1}: {lines[i].rstrip()}")
print("\n=== Return block ===")
for i, line in enumerate(lines):
    if 'return LaunchDescription' in line:
        for j in range(i, min(i+15, len(lines))):
            print(f"  {j+1}: {lines[j].rstrip()}")
        break
