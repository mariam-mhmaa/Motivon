#!/usr/bin/env python3
"""Fix ALL files on disk that VS Code failed to sync."""
import os

BASE = '/home/zeinazz/design_ws/src/mobile_robot_sim'

def fix_file(relpath, replacements):
    path = os.path.join(BASE, relpath)
    with open(path, 'r') as f:
        content = f.read()
    changed = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            changed = True
            print(f"  FIXED: {relpath}: '{old[:60]}...' -> '{new[:60]}...'")
    if changed:
        with open(path, 'w') as f:
            f.write(content)
    else:
        # Check if already correct
        for old, new in replacements:
            if new in content:
                print(f"  OK: {relpath} already has '{new[:60]}...'")
            else:
                print(f"  WARN: {relpath} - neither old nor new pattern found for '{old[:40]}...'")

# 1. controllers.yaml
print("=== controllers.yaml ===")
with open(os.path.join(BASE, 'config/controllers.yaml'), 'r') as f:
    c = f.read()
if 'mecanum_drive_controller' in c and 'MecanumDriveController' in c:
    new_yaml = """controller_manager:
  ros__parameters:
    update_rate: 50
    use_sim_time: true

    joint_state_broadcaster:
      type: joint_state_broadcaster/JointStateBroadcaster

    wheel_velocity_controller:
      type: velocity_controllers/JointGroupVelocityController

    lid_controller:
      type: position_controllers/JointGroupPositionController

# -----------------------------------------------------
# WHEEL VELOCITY CONTROLLER (replaces mecanum_drive_controller)
# -----------------------------------------------------
wheel_velocity_controller:
  ros__parameters:
    use_sim_time: true
    joints:
      - "FL_Joint"
      - "FR_Joint"
      - "RL_Joint"
      - "RR_Joint"
    interface_name: velocity

# -----------------------------------------------------
# LID POSITION CONTROLLER
# -----------------------------------------------------
lid_controller:
  ros__parameters:
    use_sim_time: true
    joints:
      - "Lid_Joint"
    interface_name: position
"""
    with open(os.path.join(BASE, 'config/controllers.yaml'), 'w') as f:
        f.write(new_yaml)
    print("  FIXED: Rewrote controllers.yaml completely")
elif 'wheel_velocity_controller' in c:
    print("  OK: Already updated")
else:
    print("  WARN: Unexpected content")

# 2. ekf_config.yaml
print("=== ekf_config.yaml ===")
fix_file('config/ekf_config.yaml', [
    ('/mecanum_drive_controller/odom', '/odom'),
])

# 3. mecanum_drive_node.py
print("=== mecanum_drive_node.py ===")
with open(os.path.join(BASE, 'scripts/mecanum_drive_node.py'), 'r') as f:
    c = f.read()
if '/mecanum_drive_controller/cmd_vel' in c or 'TwistStamped' in c:
    new_content = """#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Float64MultiArray


class MecanumDriveNode(Node):
    \"\"\"
    Subscribes to /cmd_vel (Twist).
    Converts (vx, vy, wz) to 4 individual wheel velocities using mecanum kinematics.
    Publishes as Float64MultiArray to /wheel_velocity_controller/commands.
    \"\"\"

    def __init__(self):
        super().__init__('mecanum_drive_node')

        # Robot parameters
        self.wheel_radius = 0.06  # meters
        # lx + ly = half-wheelbase-x + half-wheelbase-y = 0.1975 + 0.236 = 0.4335
        self.lx_plus_ly = 0.4335

        # Subscribe to plain Twist on /cmd_vel
        self.sub_twist = self.create_subscription(
            Twist, '/cmd_vel', self.cmd_vel_callback, 10)

        # Publish wheel velocities to JointGroupVelocityController
        # Order must match joints list in controllers.yaml: FL, FR, RL, RR
        self.pub_wheels = self.create_publisher(
            Float64MultiArray, '/wheel_velocity_controller/commands', 10)

        self.get_logger().info('Mecanum Drive Node started.')

    def cmd_vel_callback(self, msg: Twist):
        self._compute_and_publish(msg.linear.x, msg.linear.y, msg.angular.z)

    def _compute_and_publish(self, vx: float, vy: float, wz: float):
        \"\"\"
        Mecanum inverse kinematics:
          w_fl = (1/r) * (vx - vy - (lx+ly)*wz)
          w_fr = (1/r) * (vx + vy + (lx+ly)*wz)
          w_rl = (1/r) * (vx + vy - (lx+ly)*wz)
          w_rr = (1/r) * (vx - vy + (lx+ly)*wz)
        \"\"\"
        r = self.wheel_radius
        k = self.lx_plus_ly

        w_fl = (1.0 / r) * (vx - vy - k * wz)
        w_fr = (1.0 / r) * (vx + vy + k * wz)
        w_rl = (1.0 / r) * (vx + vy - k * wz)
        w_rr = (1.0 / r) * (vx - vy + k * wz)

        cmd = Float64MultiArray()
        cmd.data = [w_fl, w_fr, w_rl, w_rr]
        self.pub_wheels.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    node = MecanumDriveNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
"""
    with open(os.path.join(BASE, 'scripts/mecanum_drive_node.py'), 'w') as f:
        f.write(new_content)
    print("  FIXED: Rewrote mecanum_drive_node.py")
elif '/wheel_velocity_controller/commands' in c:
    print("  OK: Already updated")

# 4. obstacle_avoidance.py
print("=== obstacle_avoidance.py ===")
fix_file('scripts/obstacle_avoidance.py', [
    ('from geometry_msgs.msg import TwistStamped', 'from geometry_msgs.msg import Twist'),
    ("self.publisher = self.create_publisher(TwistStamped, '/mecanum_drive_controller/cmd_vel', 10)",
     "self.publisher = self.create_publisher(Twist, '/cmd_vel', 10)"),
    ("TwistStamped, '/cmd_vel_nav'", "Twist, '/cmd_vel_nav'"),
    ("def nav_cmd_callback(self, msg: TwistStamped):", "def nav_cmd_callback(self, msg: Twist):"),
    ("self.nav_cmd.twist.linear.x", "self.nav_cmd.linear.x"),
    ("self.nav_cmd.twist.linear.y", "self.nav_cmd.linear.y"),
    ("self.nav_cmd.twist.angular.z", "self.nav_cmd.angular.z"),
])
# Also fix the TwistStamped() constructor calls in control_loop
with open(os.path.join(BASE, 'scripts/obstacle_avoidance.py'), 'r') as f:
    c = f.read()
if 'TwistStamped()' in c:
    # Replace the cmd creation block
    c = c.replace('        cmd = TwistStamped()\n        cmd.header.stamp = self.get_clock().now().to_msg()\n        cmd.header.frame_id = "RobotBody"',
                   '        cmd = Twist()')
    with open(os.path.join(BASE, 'scripts/obstacle_avoidance.py'), 'w') as f:
        f.write(c)
    print("  FIXED: TwistStamped() -> Twist() in control_loop")

# 5. goal_sender_node.py
print("=== goal_sender_node.py ===")
fix_file('scripts/goal_sender_node.py', [
    ('from geometry_msgs.msg import TwistStamped, PoseStamped', 'from geometry_msgs.msg import Twist, PoseStamped'),
    ("Odometry, '/mecanum_drive_controller/odom', self.odom_callback, 10)", "Odometry, '/odom', self.odom_callback, 10)"),
    ("TwistStamped, '/mecanum_drive_controller/cmd_vel', 10)", "Twist, '/cmd_vel', 10)"),
])
with open(os.path.join(BASE, 'scripts/goal_sender_node.py'), 'r') as f:
    c = f.read()
if 'TwistStamped()' in c:
    c = c.replace('        cmd = TwistStamped()\n        cmd.header.stamp = self.get_clock().now().to_msg()\n        cmd.header.frame_id = \'RobotBody\'\n        cmd.twist.linear.x = vx\n        cmd.twist.linear.y = vy\n        cmd.twist.angular.z = wz',
                   '        cmd = Twist()\n        cmd.linear.x = vx\n        cmd.linear.y = vy\n        cmd.angular.z = wz')
    c = c.replace('        cmd = TwistStamped()\n        cmd.header.stamp = self.get_clock().now().to_msg()\n        cmd.header.frame_id = \'RobotBody\'\n        self.cmd_pub.publish(cmd)',
                   '        cmd = Twist()\n        self.cmd_pub.publish(cmd)')
    with open(os.path.join(BASE, 'scripts/goal_sender_node.py'), 'w') as f:
        f.write(c)
    print("  FIXED: TwistStamped -> Twist in goal_sender")

# 6. start_stop_node.py 
print("=== start_stop_node.py ===")
fix_file('scripts/start_stop_node.py', [
    ('from geometry_msgs.msg import TwistStamped', 'from geometry_msgs.msg import Twist'),
    ("TwistStamped, '/cmd_vel_input'", "Twist, '/cmd_vel_input'"),
    ("TwistStamped, '/mecanum_drive_controller/cmd_vel', 10)", "Twist, '/cmd_vel', 10)"),
    ("def cmd_vel_callback(self, msg: TwistStamped):", "def cmd_vel_callback(self, msg: Twist):"),
    ("/mecanum_drive_controller/cmd_vel", "/cmd_vel"),
])
with open(os.path.join(BASE, 'scripts/start_stop_node.py'), 'r') as f:
    c = f.read()
if 'TwistStamped()' in c:
    c = c.replace('        cmd = TwistStamped()\n        cmd.header.stamp = self.get_clock().now().to_msg()\n        cmd.header.frame_id = \'RobotBody\'\n        self.pub.publish(cmd)',
                   '        cmd = Twist()\n        self.pub.publish(cmd)')
    with open(os.path.join(BASE, 'scripts/start_stop_node.py'), 'w') as f:
        f.write(c)
    print("  FIXED: TwistStamped -> Twist in start_stop")

# 7. test_cmd_vel.py
print("=== test_cmd_vel.py ===")
fix_file('scripts/test_cmd_vel.py', [
    ('from geometry_msgs.msg import TwistStamped', 'from geometry_msgs.msg import Twist'),
    ("TwistStamped, '/mecanum_drive_controller/cmd_vel', 10)", "Twist, '/cmd_vel', 10)"),
])
with open(os.path.join(BASE, 'scripts/test_cmd_vel.py'), 'r') as f:
    c = f.read()
if 'TwistStamped()' in c:
    c = c.replace('        cmd = TwistStamped()\n        cmd.header.stamp = self.get_clock().now().to_msg()\n        cmd.header.frame_id = \'RobotBody\'\n        cmd.twist.linear.x = vx\n        cmd.twist.linear.y = vy\n        cmd.twist.angular.z = wz',
                   '        cmd = Twist()\n        cmd.linear.x = vx\n        cmd.linear.y = vy\n        cmd.angular.z = wz')
    with open(os.path.join(BASE, 'scripts/test_cmd_vel.py'), 'w') as f:
        f.write(c)
    print("  FIXED: TwistStamped -> Twist in test_cmd_vel")

# 8. test_obstacle.py
print("=== test_obstacle.py ===")
fix_file('scripts/test_obstacle.py', [
    ('from geometry_msgs.msg import TwistStamped', 'from geometry_msgs.msg import Twist'),
    ("TwistStamped, '/mecanum_drive_controller/cmd_vel', 10)", "Twist, '/cmd_vel', 10)"),
])
with open(os.path.join(BASE, 'scripts/test_obstacle.py'), 'r') as f:
    c = f.read()
if 'TwistStamped()' in c:
    c = c.replace('TwistStamped()', 'Twist()')
    # Fix field access
    c = c.replace('cmd.twist.linear.x', 'cmd.linear.x')
    # Remove header lines in test_obstacle
    lines = c.split('\n')
    new_lines = []
    for line in lines:
        if 'cmd.header.stamp' in line or 'cmd.header.frame_id' in line:
            continue
        new_lines.append(line)
    c = '\n'.join(new_lines)
    with open(os.path.join(BASE, 'scripts/test_obstacle.py'), 'w') as f:
        f.write(c)
    print("  FIXED: TwistStamped -> Twist in test_obstacle")

# 9. package.xml
print("=== package.xml ===")
fix_file('package.xml', [
    ('<exec_depend>mecanum_drive_controller</exec_depend>', '<exec_depend>velocity_controllers</exec_depend>'),
])

# Strip CRLF from all files
print("\n=== Stripping CRLF ===")
for f in ['config/controllers.yaml', 'config/ekf_config.yaml',
          'scripts/mecanum_drive_node.py', 'scripts/obstacle_avoidance.py',
          'scripts/goal_sender_node.py', 'scripts/start_stop_node.py',
          'scripts/test_cmd_vel.py', 'scripts/test_obstacle.py',
          'launch/robot_gazebo.launch.py', 'package.xml']:
    path = os.path.join(BASE, f)
    with open(path, 'rb') as fh:
        data = fh.read()
    if b'\r\n' in data:
        data = data.replace(b'\r\n', b'\n')
        with open(path, 'wb') as fh:
            fh.write(data)
        print(f"  FIXED CRLF: {f}")
    else:
        print(f"  OK: {f}")

print("\n=== ALL DONE ===")
