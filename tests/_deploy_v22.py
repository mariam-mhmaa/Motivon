#!/usr/bin/env python3
"""Deploy v22 navigator from _v14_content.py base."""
import os, stat

src = os.path.expanduser('~/design_ws/_v14_content.py')
dst = os.path.expanduser('~/design_ws/src/mobile_robot_sim/scripts/robot_navigator_node.py')

content = open(src).read()
content = content.replace("VERSION = 'v14'", "VERSION = 'v22'")
content = content.replace('LID_WAIT_SEC = 15.0', 'LID_WAIT_SEC = 10.0')

with open(dst, 'w', newline='\n') as f:
    f.write(content)

st = os.stat(dst)
os.chmod(dst, st.st_mode | stat.S_IEXEC)
print(f'Written {len(content)} bytes to {dst} -> v22')
