#!/usr/bin/env python3
"""
Comprehensive fix for:
1. Rewrite world file - ONLY static obstacles, no dynamic anything
2. Fix obstacle_avoidance.py - wrong Twist attribute + auto-forward
3. Fix spawn height to exact wheel contact
4. Move front/back sensors further out to avoid self-detection
5. Remove obstacle_avoidance and goal_sender from auto-launch
"""
import os, re

BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. REWRITE WORLD FILE - clean, no dynamic obstacles
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
world_content = """<?xml version="1.0" ?>
<sdf version="1.8">
  <world name="my_world">

    <!-- Physics -->
    <physics name="1ms" type="ignored">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>

    <!-- Required plugins -->
    <plugin filename="gz-sim-physics-system"
            name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-user-commands-system"
            name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system"
            name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-sensors-system"
            name="gz::sim::systems::Sensors">
      <render_engine>ogre2</render_engine>
    </plugin>
    <plugin filename="gz-sim-imu-system"
            name="gz::sim::systems::Imu"/>
    <plugin filename="gz-sim-contact-system"
            name="gz::sim::systems::Contact"/>

    <!-- Lighting -->
    <light type="directional" name="sun">
      <cast_shadows>true</cast_shadows>
      <pose>0 0 10 0 0 0</pose>
      <diffuse>0.8 0.8 0.8 1</diffuse>
      <specular>0.2 0.2 0.2 1</specular>
      <direction>-0.5 0.1 -0.9</direction>
    </light>

    <!-- Ground Plane -->
    <model name="ground_plane">
      <static>true</static>
      <link name="link">
        <collision name="collision">
          <geometry>
            <plane>
              <normal>0 0 1</normal>
              <size>50 50</size>
            </plane>
          </geometry>
        </collision>
        <visual name="visual">
          <geometry>
            <plane>
              <normal>0 0 1</normal>
              <size>50 50</size>
            </plane>
          </geometry>
          <material>
            <ambient>0.8 0.8 0.8 1</ambient>
            <diffuse>0.8 0.8 0.8 1</diffuse>
          </material>
        </visual>
      </link>
    </model>

    <!-- ==================== WALLS (enclosure) ==================== -->
    <model name="wall_north">
      <static>true</static>
      <pose>0 6 0.5 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry><box><size>12 0.2 1.0</size></box></geometry>
        </collision>
        <visual name="visual">
          <geometry><box><size>12 0.2 1.0</size></box></geometry>
          <material><ambient>0.5 0.5 0.5 1</ambient><diffuse>0.5 0.5 0.5 1</diffuse></material>
        </visual>
      </link>
    </model>

    <model name="wall_south">
      <static>true</static>
      <pose>0 -6 0.5 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry><box><size>12 0.2 1.0</size></box></geometry>
        </collision>
        <visual name="visual">
          <geometry><box><size>12 0.2 1.0</size></box></geometry>
          <material><ambient>0.5 0.5 0.5 1</ambient><diffuse>0.5 0.5 0.5 1</diffuse></material>
        </visual>
      </link>
    </model>

    <model name="wall_east">
      <static>true</static>
      <pose>6 0 0.5 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry><box><size>0.2 12 1.0</size></box></geometry>
        </collision>
        <visual name="visual">
          <geometry><box><size>0.2 12 1.0</size></box></geometry>
          <material><ambient>0.5 0.5 0.5 1</ambient><diffuse>0.5 0.5 0.5 1</diffuse></material>
        </visual>
      </link>
    </model>

    <model name="wall_west">
      <static>true</static>
      <pose>-6 0 0.5 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry><box><size>0.2 12 1.0</size></box></geometry>
        </collision>
        <visual name="visual">
          <geometry><box><size>0.2 12 1.0</size></box></geometry>
          <material><ambient>0.5 0.5 0.5 1</ambient><diffuse>0.5 0.5 0.5 1</diffuse></material>
        </visual>
      </link>
    </model>

    <!-- ==================== STATIC OBSTACLES ==================== -->
    <model name="static_obstacle_1">
      <static>true</static>
      <pose>2.5 2.0 0.25 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry><box><size>0.5 0.5 0.5</size></box></geometry>
        </collision>
        <visual name="visual">
          <geometry><box><size>0.5 0.5 0.5</size></box></geometry>
          <material><ambient>0.8 0.2 0.2 1</ambient><diffuse>0.8 0.2 0.2 1</diffuse></material>
        </visual>
      </link>
    </model>

    <model name="static_obstacle_2">
      <static>true</static>
      <pose>-2.0 -1.5 0.3 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry><cylinder><radius>0.3</radius><length>0.6</length></cylinder></geometry>
        </collision>
        <visual name="visual">
          <geometry><cylinder><radius>0.3</radius><length>0.6</length></cylinder></geometry>
          <material><ambient>0.2 0.6 0.2 1</ambient><diffuse>0.2 0.6 0.2 1</diffuse></material>
        </visual>
      </link>
    </model>

  </world>
</sdf>
"""

with open(os.path.join(BASE, "world", "my_world.sdf"), "w") as f:
    f.write(world_content)
print("[OK] my_world.sdf: rewritten clean - walls + 2 static obstacles only")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. FIX SPAWN HEIGHT — z=0.085 (exact wheel contact)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
lf = os.path.join(BASE, "launch", "robot_gazebo.launch.py")
with open(lf, "r") as f:
    launch = f.read()

launch = launch.replace("'-z', '0.1'", "'-z', '0.085'")
if "'-z', '0.085'" not in launch:
    launch = launch.replace("'-z', '0.3'", "'-z', '0.085'")

with open(lf, "w") as f:
    f.write(launch)
print("[OK] launch: spawn z=0.085 (exact wheel contact, no drop)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. REMOVE obstacle_avoidance + goal_sender FROM AUTO-LAUNCH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with open(lf, "r") as f:
    launch = f.read()

# Comment out (remove) the obstacle_avoidance and goal_sender launch actions
# Find and remove delay_obstacle, delay_goal, and their TimerAction lines
# Also remove them from the return list

# Remove the TimerAction lines for obstacle_avoidance and goal_sender
launch = re.sub(
    r'\n\s*delay_obstacle\s*=\s*TimerAction\(.*?\)\s*\n',
    '\n',
    launch
)
launch = re.sub(
    r'\n\s*delay_goal\s*=\s*TimerAction\(.*?\)\s*\n',
    '\n',
    launch
)

# Remove from the return list
launch = re.sub(r',?\s*delay_obstacle\s*,?', '', launch)
launch = re.sub(r',?\s*delay_goal\s*,?', '', launch)

# Clean up any trailing commas before ]
launch = re.sub(r',\s*\]', '\n    ]', launch)

with open(lf, "w") as f:
    f.write(launch)
print("[OK] launch: removed obstacle_avoidance + goal_sender from auto-launch")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. FIX obstacle_avoidance.py — broken Twist attribute + default forward
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
oa = os.path.join(BASE, "scripts", "obstacle_avoidance.py")
with open(oa, "r") as f:
    oa_content = f.read()

fixes = 0

# Fix cmd.twist.linear.x → cmd.linear.x (Twist, not TwistStamped)
oa_content, n = re.subn(r'cmd\.twist\.linear\.x', 'cmd.linear.x', oa_content)
fixes += n
oa_content, n = re.subn(r'cmd\.twist\.linear\.y', 'cmd.linear.y', oa_content)
fixes += n
oa_content, n = re.subn(r'cmd\.twist\.angular\.z', 'cmd.angular.z', oa_content)
fixes += n

# Remove the default forward speed (linear_x = 0.3) when no nav_cmd
# Replace: else:\n                linear_x = 0.3
oa_content = oa_content.replace(
    """            else:
                linear_x = 0.3""",
    """            else:
                linear_x = 0.0  # Stay still unless commanded"""
)
fixes += 1

with open(oa, "w") as f:
    f.write(oa_content)
print(f"[OK] obstacle_avoidance.py: {fixes} fixes (Twist attrs + no auto-forward)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. MOVE FRONT SENSOR FURTHER OUT to avoid self-detection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
uf = os.path.join(BASE, "urdf", "DeliveryRobot_2.urdf")
with open(uf, "r") as f:
    urdf = f.read()

# Front sensor: move from x=0.20 to x=0.25 (further from body)
urdf = urdf.replace(
    '<origin xyz="0.20 0.0 0.07" rpy="0 0 0"/>',
    '<origin xyz="0.25 0.0 0.07" rpy="0 0 0"/>'
)

# Back sensor: move from x=-0.20 to x=-0.25
urdf = urdf.replace(
    '<origin xyz="-0.20 0.0 0.07" rpy="0 0 3.14159"/>',
    '<origin xyz="-0.25 0.0 0.07" rpy="0 0 3.14159"/>'
)

# Also increase lidar min_range from 0.08 to 0.12 to reject body self-hits
urdf = urdf.replace('<min>0.08</min>', '<min>0.12</min>')

with open(uf, "w") as f:
    f.write(urdf)
print("[OK] URDF: moved front/back sensors out to 0.25m, min_range=0.12m")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VERIFY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("\n=== Verification ===")

with open(os.path.join(BASE, "world", "my_world.sdf"), "r") as f:
    w = f.read()
print(f"World: dynamic_obstacle={'YES' if 'dynamic_obstacle' in w else 'NO'}, "
      f"actor={'YES' if '<actor' in w else 'NO'}, "
      f"static_obstacles={w.count('static_obstacle')}")

with open(lf, "r") as f:
    l = f.read()
print(f"Launch: obstacle_avoidance in launch={'YES' if 'delay_obstacle' in l else 'NO'}, "
      f"goal_sender in launch={'YES' if 'delay_goal' in l else 'NO'}, "
      f"spawn_z={'0.085' if '0.085' in l else 'OTHER'}")

with open(oa, "r") as f:
    o = f.read()
has_twist_dot = 'cmd.twist.' in o
has_auto_fwd = "linear_x = 0.3" in o and "Stay still" not in o
print(f"Obstacle avoidance: cmd.twist bug={'YES' if has_twist_dot else 'NO'}, "
      f"auto-forward={'YES' if has_auto_fwd else 'NO'}")

with open(uf, "r") as f:
    u = f.read()
print(f"URDF: front sensor at 0.25={'YES' if '0.25 0.0 0.07' in u else 'NO'}, "
      f"min_range=0.12={'YES' if '<min>0.12</min>' in u else 'NO'}")

print("\nDone. Rebuild:")
print("  cd ~/design_ws")
print("  rm -rf build/mobile_robot_sim install/mobile_robot_sim")
print("  colcon build --symlink-install --packages-select mobile_robot_sim")
print("  source install/setup.bash")
print("  ros2 launch mobile_robot_sim robot_gazebo.launch.py")
