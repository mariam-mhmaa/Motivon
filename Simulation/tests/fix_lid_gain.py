#!/usr/bin/env python3
"""Fix the lid motion: increase position_proportional_gain and add dynamics to Lid_Joint."""
import re

BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"
urdf = BASE + "/urdf/DeliveryRobot_2.urdf"

with open(urdf, "r") as f:
    content = f.read()

# 1. Add position_proportional_gain to gz_ros2_control plugin
old_plugin = """    <plugin filename="gz_ros2_control-system"
            name="gz_ros2_control::GazeboSimROS2ControlPlugin">
      <parameters>$(find mobile_robot_sim)/config/controllers.yaml</parameters>
    </plugin>"""

new_plugin = """    <plugin filename="gz_ros2_control-system"
            name="gz_ros2_control::GazeboSimROS2ControlPlugin">
      <parameters>$(find mobile_robot_sim)/config/controllers.yaml</parameters>
      <position_proportional_gain>100.0</position_proportional_gain>
    </plugin>"""

if old_plugin in content:
    content = content.replace(old_plugin, new_plugin)
    print("[OK] Set position_proportional_gain to 100.0")
elif 'position_proportional_gain' in content:
    print("[SKIP] position_proportional_gain already set")
else:
    print("[ERROR] Could not find gz_ros2_control plugin block")

# 2. Add dynamics to Lid_Joint if not already present
# Find the Lid_Joint and add dynamics before </joint>
lid_pattern = r'(name="Lid_Joint"\s+type="prismatic">.*?<limit[^/]*/>\s*)'
lid_match = re.search(lid_pattern, content, re.DOTALL)
if lid_match:
    lid_section = lid_match.group(1)
    if '<dynamics' not in lid_section:
        new_lid = lid_section + '    <dynamics\n      damping="0.1"\n      friction="0.0" />\n  '
        content = content.replace(lid_section, new_lid)
        print("[OK] Added dynamics (damping=0.1, friction=0.0) to Lid_Joint")
    else:
        print("[SKIP] Lid_Joint already has dynamics")
else:
    print("[WARN] Could not find Lid_Joint limit section")

with open(urdf, "w") as f:
    f.write(content)

print("[OK] URDF updated")
