#!/usr/bin/env python3
"""
Fix: tilted spawn, remove dynamic_obstacle, narrow ultrasonic FOV, lower spawn height.
"""
import re

BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"

# ── 1. Remove dynamic_obstacle from world file ──
wf = BASE + "/world/my_world.sdf"
with open(wf, "r") as f:
    world = f.read()

# Remove the entire dynamic_obstacle model block (includes TriggeredPublisher)
pattern = r'\s*<!-- =+ DYNAMIC OBSTACLE[^>]*-->.*?</model>\s*'
new_world, n = re.subn(pattern, '\n', world, flags=re.DOTALL)
if n == 0:
    # Try without fancy comment
    pattern2 = r'\s*<model name="dynamic_obstacle">.*?</model>\s*'
    new_world, n = re.subn(pattern2, '\n', world, flags=re.DOTALL)

with open(wf, "w") as f:
    f.write(new_world)
print(f"[OK] my_world.sdf: removed dynamic_obstacle model ({n} block(s))")

# Verify no actor or dynamic obstacle remaining
with open(wf, "r") as f:
    check = f.read()
for term in ['dynamic_obstacle', 'moving_obstacle_actor', 'TriggeredPublisher']:
    if term in check:
        print(f"  [WARN] '{term}' still found in world file!")
    else:
        print(f"  [OK] '{term}' not found")

# ── 2. Fix spawn height in launch file ──
lf = BASE + "/launch/robot_gazebo.launch.py"
with open(lf, "r") as f:
    launch = f.read()

# Change z from 0.3 to 0.1 (wheels at z=0.085, so 0.1 = 1.5cm gentle drop)
launch = launch.replace("'-z', '0.3'", "'-z', '0.1'")
with open(lf, "w") as f:
    f.write(launch)

if "'-z', '0.1'" in launch:
    print("[OK] robot_gazebo.launch.py: spawn z changed to 0.1")
else:
    print("[WARN] robot_gazebo.launch.py: could not find z spawn param")

# ── 3. Fix ultrasonic sensor FOV in URDF (±80° → ±15° = ±0.2618 rad) ──
#    Also reduce samples from 640 to 5 (realistic for ultrasonic)
uf = BASE + "/urdf/DeliveryRobot_2.urdf"
with open(uf, "r") as f:
    urdf = f.read()

# Replace all ultrasonic sensor horizontal scan parameters
# Old: 640 samples, ±1.396263 rad (±80°)
# New: 5 samples, ±0.2618 rad (±15°) — realistic ultrasonic cone
count = 0
old_scan = """<samples>640</samples>
            <resolution>1</resolution>
            <min_angle>-1.396263</min_angle>
            <max_angle>1.396263</max_angle>"""
new_scan = """<samples>5</samples>
            <resolution>1</resolution>
            <min_angle>-0.2618</min_angle>
            <max_angle>0.2618</max_angle>"""

count = urdf.count(old_scan)
urdf = urdf.replace(old_scan, new_scan)
with open(uf, "w") as f:
    f.write(urdf)

print(f"[OK] DeliveryRobot_2.urdf: narrowed {count} ultrasonic sensor(s) from ±80° to ±15° (5 samples)")

# ── Verify ──
with open(uf, "r") as f:
    check_urdf = f.read()
wide_count = check_urdf.count("1.396263")
narrow_count = check_urdf.count("0.2618")
print(f"  Remaining wide (±80°): {wide_count}, narrow (±15°): {narrow_count}")

print("\nDone. Rebuild and relaunch:")
print("  cd ~/design_ws")
print("  rm -rf build/mobile_robot_sim install/mobile_robot_sim")
print("  colcon build --symlink-install --packages-select mobile_robot_sim")
print("  source install/setup.bash")
print("  ros2 launch mobile_robot_sim robot_gazebo.launch.py")
