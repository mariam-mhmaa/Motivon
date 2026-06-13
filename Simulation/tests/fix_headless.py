#!/usr/bin/env python3
"""Add -s (server-only) flag to Gazebo launch to avoid GUI crash in WSL."""
BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"
lf = BASE + "/launch/robot_gazebo.launch.py"

with open(lf, "r") as f:
    content = f.read()

old = "launch_arguments={'gz_args': f'-r -v 4 {world_file_path}'}.items()"
new = "launch_arguments={'gz_args': f'-r -s -v 4 {world_file_path}'}.items()"

if old in content:
    content = content.replace(old, new)
    with open(lf, "w") as f:
        f.write(content)
    print("[OK] Added -s flag for headless Gazebo (server only)")
elif '-s' in content:
    print("[SKIP] -s flag already present")
else:
    print("[ERROR] Could not find gz_args line to patch")

# Verify
import py_compile
py_compile.compile(lf, doraise=True)
print("[OK] Launch file syntax valid")
