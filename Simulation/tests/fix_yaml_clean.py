#!/usr/bin/env python3
"""Remove leftover lid_controller params from controllers.yaml."""
BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"
yaml_path = BASE + "/config/controllers.yaml"

# Write the clean version directly
content = """---
controller_manager:
  ros__parameters:
    update_rate: 50
    use_sim_time: true

    joint_state_broadcaster:
      type: joint_state_broadcaster/JointStateBroadcaster

    wheel_velocity_controller:
      type: velocity_controllers/JointGroupVelocityController

# -----------------------------------------------------
# WHEEL VELOCITY CONTROLLER
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
"""

with open(yaml_path, "w") as f:
    f.write(content)
print("[OK] controllers.yaml cleaned — no lid_controller")
