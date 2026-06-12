#!/usr/bin/env python3
"""Fix wheel joint velocity limits in the URDF.
Changes velocity="2" to velocity="20" only for the 4 wheel joints (not the lid).
"""
import re

URDF = "/home/zeinazz/design_ws/src/mobile_robot_sim/urdf/DeliveryRobot_2.urdf"

with open(URDF, "r") as f:
    content = f.read()

# Match wheel joint limit blocks (FL, FR, RL, RR) — they have effort="2" velocity="2"
# but NO lower/upper attributes (unlike the lid which has lower="0" upper="0.18")
# Strategy: replace velocity="2" only in <limit> tags that do NOT have lower/upper
count = 0
def fix_wheel_velocity(m):
    global count
    text = m.group(0)
    # Only fix wheel joints (no lower= or upper= in the limit tag)
    if 'lower=' not in text and 'upper=' not in text:
        count += 1
        return text.replace('velocity="2"', 'velocity="20"')
    return text

# Match <limit ... /> tags
content = re.sub(r'<limit[^/]*/>', fix_wheel_velocity, content)

with open(URDF, "w") as f:
    f.write(content)

print(f"Fixed {count} wheel joint velocity limits: 2 -> 20 rad/s")

# Verify
for i, line in enumerate(content.split('\n')):
    if 'velocity=' in line and 'limit' not in line.lower():
        continue
    if 'velocity="' in line:
        print(f"  line {i+1}: {line.strip()}")
