#!/usr/bin/env python3
"""Fix Lid_Joint dynamics and JointPositionController gains."""
import re

BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"
urdf_path = BASE + "/urdf/DeliveryRobot_2.urdf"

with open(urdf_path, "r") as f:
    content = f.read()

# 1. Fix the joint: remove duplicate dynamics, fix effort limit
# Current:
#   <limit lower="0" upper="0.18" effort="2" velocity="2" />
#   <dynamics damping="0.1" friction="0.0" />
#   <dynamics damping="50.0" friction="20.0" />

# Remove the high-friction dynamics line
content = content.replace(
    '  <dynamics damping="50.0" friction="20.0" />\n', ''
)
print("[OK] Removed high-friction dynamics tag")

# Fix the low-friction dynamics to have some reasonable values
content = content.replace(
    '<dynamics\n      damping="0.1"\n      friction="0.0" />',
    '<dynamics damping="0.5" friction="0.1" />'
)
print("[OK] Set dynamics: damping=0.5, friction=0.1")

# Increase effort limit
content = content.replace(
    'effort="2"\n      velocity="2"',
    'effort="100"\n      velocity="2"'
)
print("[OK] Increased effort limit to 100")

# 2. Fix JointPositionController gains and cmd_max
content = re.sub(
    r'<p_gain>50</p_gain>',
    '<p_gain>500</p_gain>',
    content
)
content = re.sub(
    r'<i_gain>0\.5</i_gain>',
    '<i_gain>5.0</i_gain>',
    content
)
content = re.sub(
    r'<d_gain>2\.0</d_gain>',
    '<d_gain>10.0</d_gain>',
    content
)
content = re.sub(
    r'<cmd_max>2</cmd_max>',
    '<cmd_max>100</cmd_max>',
    content
)
content = re.sub(
    r'<i_max>1</i_max>',
    '<i_max>50</i_max>',
    content
)
content = re.sub(
    r'<i_min>-1</i_min>',
    '<i_min>-50</i_min>',
    content
)
content = re.sub(
    r'<cmd_min>-2</cmd_min>',
    '<cmd_min>-100</cmd_min>',
    content
)
print("[OK] Updated PID gains: p=500, i=5, d=10, cmd_max=100")

with open(urdf_path, "w") as f:
    f.write(content)
print("[OK] URDF saved")

# Verify
with open(urdf_path, "r") as f:
    v = f.read()
    
# Check no duplicate dynamics
count = v.count("<dynamics")
lid_section = re.search(r'name="Lid_Joint".*?</joint>', v, re.DOTALL)
if lid_section:
    dyn_count = lid_section.group().count("<dynamics")
    print(f"[CHECK] Lid_Joint has {dyn_count} dynamics tag(s)")
    
if "effort=\"100\"" in v:
    print("[CHECK] effort=100 confirmed")
if "cmd_max>100<" in v:
    print("[CHECK] cmd_max=100 confirmed")
if "p_gain>500<" in v:
    print("[CHECK] p_gain=500 confirmed")
