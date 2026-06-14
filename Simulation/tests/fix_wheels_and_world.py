#!/usr/bin/env python3
"""Fix backward wheel rotation and remove human actor from world."""
import os

BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"

# ── 1. Fix mecanum_drive_node.py: negate FR and RR for axis direction ──
mdn = os.path.join(BASE, "scripts", "mecanum_drive_node.py")
with open(mdn, "r") as f:
    content = f.read()

old_kinematics = """        w_fl = (1.0 / r) * (vx - vy - k * wz)
        w_fr = (1.0 / r) * (vx + vy + k * wz)
        w_rl = (1.0 / r) * (vx + vy - k * wz)
        w_rr = (1.0 / r) * (vx - vy + k * wz)"""

new_kinematics = """        # NOTE: FR and RR are negated because in the URDF the right-side
        # wheel joints have axis [0,0,1] (maps to -Y in parent frame),
        # opposite to the left-side [0,0,-1] (maps to +Y).  A positive
        # velocity command on the right side therefore spins the wheel
        # backward; negating corrects for this.
        w_fl = (1.0 / r) * (vx - vy - k * wz)
        w_fr = -(1.0 / r) * (vx + vy + k * wz)
        w_rl = (1.0 / r) * (vx + vy - k * wz)
        w_rr = -(1.0 / r) * (vx - vy + k * wz)"""

if old_kinematics in content:
    content = content.replace(old_kinematics, new_kinematics)
    with open(mdn, "w") as f:
        f.write(content)
    print(f"[OK] mecanum_drive_node.py: negated FR and RR wheel velocities")
else:
    print(f"[SKIP] mecanum_drive_node.py: old kinematics block not found (maybe already patched?)")
    # Show current kinematics for debugging
    for i, line in enumerate(content.split('\n')):
        if 'w_fl' in line or 'w_fr' in line or 'w_rl' in line or 'w_rr' in line:
            print(f"  line {i+1}: {line}")

# ── 2. Remove human actor from world file ──
wf = os.path.join(BASE, "world", "my_world.sdf")
with open(wf, "r") as f:
    world = f.read()

# Find and remove the entire <actor> block
import re
actor_pattern = r'\s*<!-- Animated dynamic obstacle using waypoints -->\s*\n\s*<actor name="moving_obstacle_actor">.*?</actor>\s*'
new_world, n = re.subn(actor_pattern, '\n', world, flags=re.DOTALL)
if n > 0:
    with open(wf, "w") as f:
        f.write(new_world)
    print(f"[OK] my_world.sdf: removed moving_obstacle_actor (human)")
else:
    # Try without the comment
    actor_pattern2 = r'\s*<actor name="moving_obstacle_actor">.*?</actor>\s*'
    new_world, n = re.subn(actor_pattern2, '\n', world, flags=re.DOTALL)
    if n > 0:
        with open(wf, "w") as f:
            f.write(new_world)
        print(f"[OK] my_world.sdf: removed moving_obstacle_actor (human, no comment)")
    else:
        print(f"[SKIP] my_world.sdf: actor not found (maybe already removed?)")

print("\nDone. Rebuild and relaunch:")
print("  cd ~/design_ws")
print("  colcon build --symlink-install --packages-select mobile_robot_sim")
print("  source install/setup.bash")
print("  ros2 launch mobile_robot_sim robot_gazebo.launch.py")
