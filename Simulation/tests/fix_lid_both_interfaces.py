#!/usr/bin/env python3
"""Add both position and velocity command interfaces for Lid_Joint."""
BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"
urdf = BASE + "/urdf/DeliveryRobot_2.urdf"

with open(urdf, "r") as f:
    content = f.read()

# Current: only velocity command interface
old = """    <joint name="Lid_Joint">
      <command_interface name="velocity" />
      <state_interface name="position" />
      <state_interface name="velocity" />
    </joint>"""

new = """    <joint name="Lid_Joint">
      <command_interface name="position" />
      <command_interface name="velocity" />
      <state_interface name="position" />
      <state_interface name="velocity" />
    </joint>"""

if old in content:
    content = content.replace(old, new)
    with open(urdf, "w") as f:
        f.write(content)
    print("[OK] Added both position and velocity command interfaces for Lid_Joint")
elif 'command_interface name="position"' in content and 'command_interface name="velocity"' in content:
    # Check if both are already in the Lid_Joint section
    idx = content.find('name="Lid_Joint"', content.find('ros2_control'))
    if idx > 0:
        section = content[idx:idx+200]
        if 'position' in section and 'velocity' in section:
            print("[SKIP] Both interfaces already present")
        else:
            print("[ERROR] Interfaces found but not in Lid_Joint section")
    else:
        print("[ERROR] Lid_Joint not found in ros2_control block")
else:
    print("[ERROR] Could not find Lid_Joint block to patch")
    print("Looking for:", repr(old[:50]))
