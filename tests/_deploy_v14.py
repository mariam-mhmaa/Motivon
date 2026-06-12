#!/usr/bin/env python3
import os, stat
SRC = os.path.expanduser('~/design_ws/src/mobile_robot_sim/scripts/robot_navigator_node.py')
CONTENT_FILE = os.path.expanduser('~/design_ws/_v14_content.py')
content = open(CONTENT_FILE).read()
with open(SRC, 'w', newline='\n') as f:
    f.write(content)
st = os.stat(SRC)
os.chmod(SRC, st.st_mode | stat.S_IEXEC)
print(f'Written {len(content)} bytes to {SRC}')
