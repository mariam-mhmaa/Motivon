#!/usr/bin/env python3
"""
Fix the controller spawning issue.
gz_ros2_control auto-loads AND auto-activates controllers.
The spawner then tries to re-configure and fails.
Solution: Remove all spawner nodes from launch. gz_ros2_control handles it.
"""

BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"
lf = BASE + "/launch/robot_gazebo.launch.py"

with open(lf, "r") as f:
    content = f.read()

# Remove the three controller spawner Node blocks and their TimerAction delays
import re

# Remove jsb_spawner Node block
content = re.sub(
    r'\n\s*# Controller Spawners\n\s*jsb_spawner = Node\(.*?\)\n',
    '\n',
    content, flags=re.DOTALL
)

# Remove mecanum_spawner Node block  
content = re.sub(
    r'\n\s*mecanum_spawner = Node\(.*?\)\n',
    '\n',
    content, flags=re.DOTALL
)

# Remove lid_spawner Node block
content = re.sub(
    r'\n\s*lid_spawner = Node\(.*?\)\n',
    '\n',
    content, flags=re.DOTALL
)

# Remove the stagger delay lines
content = re.sub(r'\n\s*# Stagger controller loading\n', '\n', content)
content = re.sub(r'\n\s*delay_jsb = TimerAction\(.*?\)\n', '\n', content)
content = re.sub(r'\n\s*delay_mecanum = TimerAction\(.*?\)\n', '\n', content)
content = re.sub(r'\n\s*delay_lid = TimerAction\(.*?\)\n', '\n', content)

# Remove from return list
content = content.replace('        delay_jsb,\n', '')
content = content.replace('        delay_mecanum,\n', '')
content = content.replace('        delay_lid,\n', '')

with open(lf, "w") as f:
    f.write(content)

# Verify
import py_compile
try:
    py_compile.compile(lf, doraise=True)
    print("[OK] Launch file syntax is valid")
except py_compile.PyCompileError as e:
    print(f"[ERROR] Syntax error: {e}")

with open(lf, "r") as f:
    final = f.read()

# Check no spawner references remain
if 'spawner' in final.lower():
    print("[WARN] 'spawner' still found in launch file!")
    for i, line in enumerate(final.split('\n')):
        if 'spawner' in line.lower():
            print(f"  line {i+1}: {line.rstrip()}")
else:
    print("[OK] No spawner references in launch file")

if 'delay_jsb' in final or 'delay_mecanum' in final or 'delay_lid' in final:
    print("[WARN] delay_jsb/mecanum/lid still in file")
else:
    print("[OK] No controller delay references")

# Show the return block
for i, line in enumerate(final.split('\n')):
    if 'return LaunchDescription' in line:
        for j in range(i, min(i+15, len(final.split('\n')))):
            print(f"  {j+1}: {final.split(chr(10))[j].rstrip()}")
        break
