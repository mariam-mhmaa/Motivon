#!/usr/bin/env python3
"""
Switch Lid_Joint from position to velocity command interface in URDF + controllers.yaml,
and update lid_control_node.py to do position control via velocity commands.
"""
import re

BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"

# =====================================================
# 1. Update URDF: change Lid_Joint command interface from position to velocity
# =====================================================
urdf_path = BASE + "/urdf/DeliveryRobot_2.urdf"
with open(urdf_path, "r") as f:
    urdf = f.read()

old_lid_hw = """    <joint name="Lid_Joint">
      <command_interface name="position" />
      <state_interface name="position" />
      <state_interface name="velocity" />
    </joint>"""

new_lid_hw = """    <joint name="Lid_Joint">
      <command_interface name="velocity" />
      <state_interface name="position" />
      <state_interface name="velocity" />
    </joint>"""

if old_lid_hw in urdf:
    urdf = urdf.replace(old_lid_hw, new_lid_hw)
    with open(urdf_path, "w") as f:
        f.write(urdf)
    print("[OK] URDF: Lid_Joint command interface changed to velocity")
else:
    if 'name="Lid_Joint"' in urdf and 'command_interface name="velocity"' in urdf.split('Lid_Joint')[1][:200]:
        print("[SKIP] URDF: Lid_Joint already uses velocity command interface")
    else:
        print("[ERROR] Could not find Lid_Joint ros2_control block to patch")

# =====================================================
# 2. Update controllers.yaml: lid_controller → JointGroupVelocityController
# =====================================================
yaml_path = BASE + "/config/controllers.yaml"
with open(yaml_path, "r") as f:
    yaml = f.read()

old_lid_type = "    lid_controller:\n      type: position_controllers/JointGroupPositionController"
new_lid_type = "    lid_controller:\n      type: velocity_controllers/JointGroupVelocityController"

if old_lid_type in yaml:
    yaml = yaml.replace(old_lid_type, new_lid_type)
    print("[OK] YAML: lid_controller type changed to JointGroupVelocityController")
else:
    print("[SKIP/ERROR] Could not find lid_controller type to patch in YAML")

# Also change interface_name from position to velocity
old_iface = """lid_controller:
  ros__parameters:
    use_sim_time: true
    joints:
      - "Lid_Joint"
    interface_name: position"""

new_iface = """lid_controller:
  ros__parameters:
    use_sim_time: true
    joints:
      - "Lid_Joint"
    interface_name: velocity"""

if old_iface in yaml:
    yaml = yaml.replace(old_iface, new_iface)
    print("[OK] YAML: lid_controller interface_name changed to velocity")
else:
    print("[SKIP/ERROR] Could not find lid_controller interface_name to patch")

with open(yaml_path, "w") as f:
    f.write(yaml)

# =====================================================
# 3. Rewrite lid_control_node.py with velocity-based position control
# =====================================================
lid_node_path = BASE + "/scripts/lid_control_node.py"
lid_node_code = '''#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
from sensor_msgs.msg import JointState
from std_srvs.srv import SetBool


class LidControlNode(Node):
    """
    Controls the prismatic lid joint via velocity commands with P-control.
    - Publishes velocity commands to /lid_controller/commands
    - Subscribes to /joint_states for lid position feedback
    - Provides /lid_control service (SetBool: true=open, false=close)
    """

    LID_OPEN = 0.18      # meters
    LID_CLOSED = 0.0
    KP = 5.0              # proportional gain
    MAX_VEL = 1.0         # m/s clamp
    TOLERANCE = 0.002     # 2mm

    def __init__(self):
        super().__init__('lid_control_node')

        self.target_pos = self.LID_CLOSED
        self.current_pos = 0.0

        self.pub = self.create_publisher(
            Float64MultiArray, '/lid_controller/commands', 10)

        self.sub_js = self.create_subscription(
            JointState, '/joint_states', self.joint_state_cb, 10)

        self.srv = self.create_service(
            SetBool, '/lid_control', self.lid_service_cb)

        self.sub_cmd = self.create_subscription(
            Float64MultiArray, '/lid_command', self.lid_topic_cb, 10)

        # Control loop at 20 Hz
        self.timer = self.create_timer(0.05, self.control_loop)

        self.get_logger().info('Lid Control Node started. Service: /lid_control')

    def joint_state_cb(self, msg: JointState):
        try:
            idx = msg.name.index('Lid_Joint')
            self.current_pos = msg.position[idx]
        except (ValueError, IndexError):
            pass

    def lid_service_cb(self, request, response):
        if request.data:
            self.target_pos = self.LID_OPEN
            response.message = 'Lid opening'
            self.get_logger().info('Lid OPEN command received')
        else:
            self.target_pos = self.LID_CLOSED
            response.message = 'Lid closing'
            self.get_logger().info('Lid CLOSE command received')
        response.success = True
        return response

    def lid_topic_cb(self, msg: Float64MultiArray):
        if len(msg.data) > 0:
            self.target_pos = max(self.LID_CLOSED, min(msg.data[0], self.LID_OPEN))
            self.get_logger().info(f'Lid target set to {self.target_pos:.3f}')

    def control_loop(self):
        error = self.target_pos - self.current_pos
        if abs(error) < self.TOLERANCE:
            vel = 0.0
        else:
            vel = self.KP * error
            vel = max(-self.MAX_VEL, min(vel, self.MAX_VEL))

        cmd = Float64MultiArray()
        cmd.data = [vel]
        self.pub.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    node = LidControlNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
'''

with open(lid_node_path, "w") as f:
    f.write(lid_node_code)
print("[OK] lid_control_node.py rewritten with velocity-based position control")

print("\n[DONE] All files updated. Rebuild and relaunch needed.")
