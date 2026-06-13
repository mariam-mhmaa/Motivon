#!/usr/bin/env python3
"""
NEW APPROACH: Remove lid from ros2_control entirely.
Use Gazebo's native JointPositionController plugin instead.
This does proper PID at physics rate — no interface mismatch issues.

Changes:
  1. URDF: Remove Lid_Joint from ros2_control, add Gazebo JointPositionController plugin
  2. controllers.yaml: Remove lid_controller
  3. Launch file: Remove lid_spawner, add /lid_position bridge
  4. lid_control_node.py: Publish Float64 to /lid_position
"""
import re

BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"

# ===================== 1. URDF =====================
urdf_path = BASE + "/urdf/DeliveryRobot_2.urdf"
with open(urdf_path, "r") as f:
    urdf = f.read()

# Remove Lid_Joint from ros2_control block (handle both single and dual command interface variants)
for pattern in [
    r'\s*<joint name="Lid_Joint">\s*<command_interface name="position"\s*/>\s*<command_interface name="velocity"\s*/>\s*<state_interface name="position"\s*/>\s*<state_interface name="velocity"\s*/>\s*</joint>',
    r'\s*<joint name="Lid_Joint">\s*<command_interface name="velocity"\s*/>\s*<state_interface name="position"\s*/>\s*<state_interface name="velocity"\s*/>\s*</joint>',
    r'\s*<joint name="Lid_Joint">\s*<command_interface name="position"\s*/>\s*<state_interface name="position"\s*/>\s*<state_interface name="velocity"\s*/>\s*</joint>',
]:
    urdf_new = re.sub(pattern, '', urdf)
    if urdf_new != urdf:
        urdf = urdf_new
        print("[OK] URDF: Removed Lid_Joint from ros2_control block")
        break
else:
    if 'Lid_Joint' not in urdf[urdf.find('<ros2_control'):urdf.find('</ros2_control>')]:
        print("[SKIP] URDF: Lid_Joint already not in ros2_control block")
    else:
        print("[WARN] URDF: Could not remove Lid_Joint from ros2_control (unknown format)")
        # Show what's there
        rc_start = urdf.find('<ros2_control')
        rc_end = urdf.find('</ros2_control>')
        print("  Current:", urdf[rc_start:rc_end+16])

# Add Gazebo JointPositionController plugin (if not already there)
if 'JointPositionController' not in urdf:
    # Insert before the closing </robot> tag
    gz_plugin = """
  <!-- ==================== Gazebo Native Lid Position Controller ==================== -->
  <gazebo>
    <plugin filename="gz-sim-joint-position-controller-system"
            name="gz::sim::systems::JointPositionController">
      <joint_name>Lid_Joint</joint_name>
      <topic>/lid_position</topic>
      <p_gain>50</p_gain>
      <i_gain>0.5</i_gain>
      <d_gain>2.0</d_gain>
      <i_max>1</i_max>
      <i_min>-1</i_min>
      <cmd_max>2</cmd_max>
      <cmd_min>-2</cmd_min>
    </plugin>
  </gazebo>

"""
    urdf = urdf.replace('</robot>', gz_plugin + '</robot>')
    print("[OK] URDF: Added Gazebo JointPositionController plugin for Lid_Joint")
else:
    print("[SKIP] URDF: JointPositionController already present")

# Also remove position_proportional_gain if it exists (no longer needed)
urdf = re.sub(r'\s*<position_proportional_gain>[^<]*</position_proportional_gain>', '', urdf)

with open(urdf_path, "w") as f:
    f.write(urdf)
print("[OK] URDF saved")

# ===================== 2. controllers.yaml =====================
yaml_path = BASE + "/config/controllers.yaml"
with open(yaml_path, "r") as f:
    yaml_content = f.read()

# Remove lid_controller from controller_manager section
yaml_content = re.sub(
    r'\n    lid_controller:\n      type: [^\n]+\n', '\n', yaml_content
)

# Remove entire lid_controller parameter block
yaml_content = re.sub(
    r'# -+\n# LID.*?interface_name: \w+\n',
    '', yaml_content, flags=re.DOTALL
)

with open(yaml_path, "w") as f:
    f.write(yaml_content)
print("[OK] controllers.yaml: Removed lid_controller")

# ===================== 3. Launch file =====================
launch_path = BASE + "/launch/robot_gazebo.launch.py"
with open(launch_path, "r") as f:
    launch = f.read()

# Remove lid_spawner Node + TimerAction
launch = re.sub(
    r'\n    lid_spawner = Node\([^)]+\)\n    delay_lid_spawner = TimerAction\([^)]+\)\n',
    '\n', launch
)

# Remove delay_lid_spawner from return list
launch = launch.replace('        delay_lid_spawner,\n', '')

# Add /lid_position bridge topic (ROS Float64 -> Gazebo Double)
if '/lid_position' not in launch:
    # Add after the last ultrasonic bridge line
    launch = launch.replace(
        "            '/ultrasonic/right@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan'",
        "            '/ultrasonic/right@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',\n"
        "            '/lid_position@std_msgs/msg/Float64]gz.msgs.Double'"
    )
    print("[OK] Launch: Added /lid_position bridge")
else:
    print("[SKIP] Launch: /lid_position bridge already present")

with open(launch_path, "w") as f:
    f.write(launch)

# Verify syntax
import py_compile
py_compile.compile(launch_path, doraise=True)
print("[OK] Launch file syntax valid")

# ===================== 4. lid_control_node.py =====================
lid_node_path = BASE + "/scripts/lid_control_node.py"
lid_code = '''#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64
from std_srvs.srv import SetBool


class LidControlNode(Node):
    """
    Controls the prismatic lid joint via Gazebo\'s native JointPositionController.
    Publishes desired position as Float64 to /lid_position (bridged to Gazebo).
    Provides /lid_control service (SetBool: true=open, false=close).
    """

    LID_OPEN = 0.18      # meters (URDF upper limit)
    LID_CLOSED = 0.0     # meters (URDF lower limit)

    def __init__(self):
        super().__init__(\'lid_control_node\')

        # Publisher to Gazebo JointPositionController via bridge
        self.pub = self.create_publisher(Float64, \'/lid_position\', 10)

        # Service: SetBool (true = open, false = close)
        self.srv = self.create_service(
            SetBool, \'/lid_control\', self.lid_service_cb)

        # Publish closed position initially, keep publishing at 2 Hz
        self.target = self.LID_CLOSED
        self.timer = self.create_timer(0.5, self.publish_position)

        self.get_logger().info(\'Lid Control Node started. Service: /lid_control\')

    def lid_service_cb(self, request, response):
        if request.data:
            self.target = self.LID_OPEN
            response.message = \'Lid opened\'
            self.get_logger().info(\'Lid OPENED via service\')
        else:
            self.target = self.LID_CLOSED
            response.message = \'Lid closed\'
            self.get_logger().info(\'Lid CLOSED via service\')
        response.success = True
        return response

    def publish_position(self):
        msg = Float64()
        msg.data = self.target
        self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = LidControlNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == \'__main__\':
    main()
'''

with open(lid_node_path, "w") as f:
    f.write(lid_code)
print("[OK] lid_control_node.py rewritten (Gazebo native approach)")

print("\n=== DONE === All 4 files updated. Rebuild and relaunch needed.")
