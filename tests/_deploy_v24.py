#!/usr/bin/env python3
"""Patch v23 -> v24: add /dynamic_obstacle subscription to navigator."""
import os, stat

dst = os.path.expanduser(
    '~/design_ws/src/mobile_robot_sim/scripts/robot_navigator_node.py')

with open(dst) as f:
    src = f.read()

# 1. Add Bool import
src = src.replace(
    "from std_srvs.srv import SetBool",
    "from std_msgs.msg import Bool\nfrom std_srvs.srv import SetBool"
)

# 2. Bump version
src = src.replace("VERSION = 'v23'", "VERSION = 'v24'")

# 3. Add obstacle_active flag in __init__ (after _wall_override)
src = src.replace(
    "self._wall_override = False\n"
    "        self._stop_count = 0",
    "self._wall_override = False\n"
    "        self._stop_count = 0\n"
    "        self.obstacle_active = False"
)

# 4. Add subscription (after enable_client line)
src = src.replace(
    "self.enable_client = self.create_client(SetBool, '/robot_enable')\n"
    "        self.create_timer(0.1, self._control_loop)",
    "self.enable_client = self.create_client(SetBool, '/robot_enable')\n"
    "        self.create_subscription(Bool, '/dynamic_obstacle', self._obstacle_cb, 10)\n"
    "        self.create_timer(0.1, self._control_loop)"
)

# 5. Add callback (before _obs_scale)
src = src.replace(
    "    def _obs_scale(self, d):",
    "    def _obstacle_cb(self, msg):\n"
    "        self.obstacle_active = msg.data\n"
    "        if msg.data:\n"
    "            self.get_logger().info('Dynamic obstacle detected - STOPPING', throttle_duration_sec=2.0)\n"
    "        else:\n"
    "            self.get_logger().info('Dynamic obstacle cleared - RESUMING')\n"
    "\n"
    "    def _obs_scale(self, d):"
)

# 6. Add obstacle check at top of _do_navigate (after the method def and first lines)
src = src.replace(
    "    def _do_navigate(self):\n"
    "        if self.state == self.STATE_RETURNING:\n"
    "            tx, ty = self.home_pos\n"
    "        else:\n"
    "            tx, ty = self.targets[self.target_idx]",
    "    def _do_navigate(self):\n"
    "        # Freeze while dynamic obstacle is active\n"
    "        if self.obstacle_active:\n"
    "            self._stop()\n"
    "            return\n"
    "\n"
    "        if self.state == self.STATE_RETURNING:\n"
    "            tx, ty = self.home_pos\n"
    "        else:\n"
    "            tx, ty = self.targets[self.target_idx]"
)

with open(dst, 'w', newline='\n') as f:
    f.write(src)

st = os.stat(dst)
os.chmod(dst, st.st_mode | stat.S_IEXEC)
print(f'Patched to v24 ({len(src)} bytes)')
