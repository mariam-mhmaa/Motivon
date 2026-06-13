# Mobile Robot Sim — Mecanum Delivery Robot

A ROS 2 Jazzy / Gazebo Harmonic simulation of an autonomous mecanum-wheeled delivery robot that navigates through a structured environment, avoids static and dynamic obstacles, and performs delivery stops with a motorised lid mechanism.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [System Architecture](#system-architecture)
- [Package Structure](#package-structure)
- [Prerequisites](#prerequisites)
- [Build & Install](#build--install)
- [Launch](#launch)
- [Usage](#usage)
- [ROS Nodes](#ros-nodes)
- [Topics & Services](#topics--services)
- [Navigation Route](#navigation-route)
- [Obstacle Avoidance](#obstacle-avoidance)
- [Configuration](#configuration)

---

## Overview

The robot spawns at a home position (2.5, −1.46) facing North in a Gazebo world and, upon receiving a start signal, autonomously visits 5 delivery targets (T1–T5) connected by waypoints (WP0–WP4). At each delivery target the lid opens, waits 15 seconds, closes, and (at selected targets) the robot rotates 90° counter-clockwise before continuing. After completing all deliveries the robot returns home and aligns to its idle orientation.

Navigation goals are communicated from a dedicated **Goal Sender** node to the **Navigator** node via a ROS topic, and the robot is gated by a **Start/Stop** service that must be explicitly enabled before the mission begins.

---

## Features

| Feature | Description |
|---|---|
| **Mecanum omnidirectional drive** | Holonomic movement — forward, lateral, diagonal, and rotation in place |
| **Static obstacle avoidance** | 4 ultrasonic sensors (front, back, left, right) with graduated slowdown, full stop, backup, and lateral escape |
| **Dynamic obstacle avoidance** | Two timed obstacles spawn in the robot's path; the robot stops completely until the obstacle is removed |
| **Start / Stop signals** | `/robot_enable` service — robot does not move until explicitly enabled; can be stopped at any time |
| **Goal communication** | Goals published by `goal_sender_node` on `/navigation_goals` topic and received by the navigator |
| **Delivery lid mechanism** | Prismatic joint lid opens/closes via `/lid_control` service with a Gazebo JointPositionController |
| **Sensor fusion** | Extended Kalman Filter (`robot_localization`) fuses IMU and wheel odometry |
| **Per-target rotation** | 90° CCW rotation at T1, T3, and WP1 after delivery or waypoint arrival |

---

## System Architecture

```
┌──────────────┐    /navigation_goals     ┌────────────────────┐
│ goal_sender   │ ──────────────────────► │  robot_navigator    │
│ _node         │   (String/JSON)         │  _node              │
└──────────────┘                          │                     │
                                          │  /cmd_vel_input     │
┌──────────────┐   /robot_enabled_state   │◄── /odom            │
│ start_stop   │ ────────────────────────►│◄── /ultrasonic/*    │
│ _node        │                          │◄── /dynamic_obstacle│
│              │◄── /cmd_vel_input        └─────────┬───────────┘
│              │──► /cmd_vel                        │
└──────┬───────┘                          ┌─────────▼───────────┐
       │ /robot_enable (service)          │  lid_control_node   │
       │                                  │  /lid_control (srv) │
       │                                  └─────────────────────┘
┌──────▼───────┐
│  Gazebo      │◄── /lid_position
│  Harmonic    │──► /odom, /imu, /ultrasonic/*, /joint_states
└──────────────┘

┌──────────────┐
│ dynamic_     │──► /dynamic_obstacle (Bool)
│ obstacle_node│    spawns/removes red boxes via gz service
└──────────────┘
```

---

## Package Structure

```
mobile_robot_sim/
├── CMakeLists.txt
├── package.xml
├── README.md
├── config/
│   ├── controllers.yaml          # ros2_control controller config
│   └── ekf_config.yaml           # EKF sensor fusion config
├── launch/
│   └── robot_gazebo.launch.py    # Main launch file (all nodes)
├── meshes/
│   ├── RobotBody.STL
│   ├── FL_Wheel.STL / FR_Wheel.STL / RL_Wheel.STL / RR_Wheel.STL
│   └── Lid.STL
├── urdf/
│   └── DeliveryRobot_2.urdf      # Robot description
├── world/
│   └── my_world.sdf              # Gazebo world with static obstacles
├── scripts/
│   ├── robot_navigator_node.py   # Main navigation state machine
│   ├── goal_sender_node.py       # Publishes navigation goals
│   ├── start_stop_node.py        # Start/stop gate service
│   ├── lid_control_node.py       # Lid open/close service
│   ├── dynamic_obstacle_node.py  # Spawns dynamic obstacles
│   └── obstacle_avoidance.py     # (legacy) standalone avoidance
└── rviz/
    └── config.rviz               # RViz visualisation config
```

---

## Prerequisites

- **Ubuntu 24.04** (WSL2 or native)
- **ROS 2 Jazzy**
- **Gazebo Harmonic** (`ros-jazzy-ros-gz`)
- Required ROS packages:
  ```
  ros-jazzy-robot-state-publisher
  ros-jazzy-ros-gz-sim
  ros-jazzy-ros-gz-bridge
  ros-jazzy-robot-localization
  ros-jazzy-xacro
  ros-jazzy-controller-manager
  ros-jazzy-joint-state-broadcaster
  ros-jazzy-velocity-controllers
  ros-jazzy-position-controllers
  ```

---

## Build & Install

```bash
cd ~/design_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select mobile_robot_sim --symlink-install
source install/setup.bash
```

---

## Launch

### 1. Start the simulation

```bash
ros2 launch mobile_robot_sim robot_gazebo.launch.py
```

This launches (in timed sequence):

| Time | Node |
|------|------|
| t=0s | Kill stale Gazebo processes |
| t=2s | Gazebo Harmonic with world |
| t=0s | ROS–Gazebo bridge, Robot State Publisher |
| t=7s | Spawn robot at (2.5, −1.46, yaw=90°) |
| t=10s | EKF, Lid Control, Start/Stop gate |
| t=12s | Dynamic Obstacle spawner |
| t=13s | Goal Sender (publishes targets) |
| t=14s | Navigator (waits for goals + enable) |

### 2. Enable the robot (new terminal)

```bash
source /opt/ros/jazzy/setup.bash
source ~/design_ws/install/setup.bash
ros2 service call /robot_enable std_srvs/srv/SetBool "{data: true}"
```

The robot begins its delivery mission.

### 3. Stop the robot at any time

```bash
ros2 service call /robot_enable std_srvs/srv/SetBool "{data: false}"
```

### 4. Re-enable

```bash
ros2 service call /robot_enable std_srvs/srv/SetBool "{data: true}"
```

---

## Usage

Once enabled, the robot autonomously:

1. Navigates to each target in sequence: T1 → T2 → WP0 → T3 → T4 → WP1 → WP2 → T5 → WP3 → WP4
2. At delivery targets (T1–T5): opens lid → waits 15s → closes lid
3. At rotation points (T1, T3, WP1): rotates 90° CCW after lid cycle / arrival
4. Avoids static obstacles using ultrasonic sensors (decelerate → stop → back up → escape)
5. Stops completely when a dynamic obstacle appears, resumes when removed
6. Returns home and aligns to idle orientation

---

## ROS Nodes

| Node | Script | Purpose |
|------|--------|---------|
| `robot_navigator_node` | `robot_navigator_node.py` | Main navigation state machine with sensor-based obstacle avoidance |
| `goal_sender_node` | `goal_sender_node.py` | Publishes mission targets as JSON on `/navigation_goals` |
| `start_stop_node` | `start_stop_node.py` | Gates `/cmd_vel_input` → `/cmd_vel`; provides `/robot_enable` service |
| `lid_control_node` | `lid_control_node.py` | Provides `/lid_control` service to open/close the delivery lid |
| `dynamic_obstacle_node` | `dynamic_obstacle_node.py` | Spawns/removes timed obstacles; publishes `/dynamic_obstacle` |
| `ekf_filter_node` | `robot_localization` | Fuses IMU + wheel odometry via EKF |

---

## Topics & Services

### Topics

| Topic | Type | Direction | Description |
|-------|------|-----------|-------------|
| `/navigation_goals` | `std_msgs/String` | goal_sender → navigator | JSON-encoded mission (targets, indices, home) |
| `/cmd_vel_input` | `geometry_msgs/Twist` | navigator → start_stop | Velocity commands (before gate) |
| `/cmd_vel` | `geometry_msgs/Twist` | start_stop → Gazebo | Gated velocity commands |
| `/odom` | `nav_msgs/Odometry` | Gazebo → nodes | Wheel odometry |
| `/imu` | `sensor_msgs/Imu` | Gazebo → EKF | IMU data |
| `/ultrasonic/front` | `sensor_msgs/LaserScan` | Gazebo → navigator | Front distance sensor |
| `/ultrasonic/back` | `sensor_msgs/LaserScan` | Gazebo → navigator | Rear distance sensor |
| `/ultrasonic/left` | `sensor_msgs/LaserScan` | Gazebo → navigator | Left distance sensor |
| `/ultrasonic/right` | `sensor_msgs/LaserScan` | Gazebo → navigator | Right distance sensor |
| `/dynamic_obstacle` | `std_msgs/Bool` | obstacle_node → navigator | True = obstacle blocking path |
| `/robot_enabled_state` | `std_msgs/Bool` | start_stop → navigator | Current enable state (10 Hz) |
| `/lid_position` | `std_msgs/Float64` | lid_control → Gazebo | Lid joint position command |

### Services

| Service | Type | Description |
|---------|------|-------------|
| `/robot_enable` | `std_srvs/SetBool` | `true` = start, `false` = stop |
| `/lid_control` | `std_srvs/SetBool` | `true` = open lid, `false` = close lid |

---

## Navigation Route

```
HOME (2.5, -1.46)
  │
  ▼
T1 (2.5, 0.5)        ← Delivery + 90° CCW rotation
  │
  ▼
T2 (0.04, 1.01)      ← Delivery
  │
  ▼
WP0 (-0.86, 1.60)    ← Waypoint (forced drive)
  │
  ▼
T3 (-1.75, 1.45)     ← Delivery + 90° CCW rotation
  │
  ▼
T4 (-2.76, 0.65)     ← Delivery
  │
  ▼
WP1 (-2.76, 0.22)    ← Waypoint + 90° CCW rotation
  │
  ▼
WP2 (-1.45, 0.22)    ← Waypoint (forced drive)
  │
  ▼
T5 (-0.55, -0.39)    ← Delivery
  │
  ▼
WP3 (0.17, -1.17)    ← Waypoint (forced drive)
  │
  ▼
WP4 (1.50, -1.20)    ← Waypoint (forced drive)
  │
  ▼
HOME → Align 90° CCW → IDLE
```

---

## Obstacle Avoidance

### Static Obstacles

The robot uses 4 ultrasonic sensors with a graduated response:

| Zone | Distance | Behaviour |
|------|----------|-----------|
| Safe | > 0.80 m | Full speed |
| Warn | 0.55–0.80 m | Proportional slowdown |
| Critical | 0.40–0.55 m | Full stop in that direction |
| Backup | < 0.40 m | Reverse away from obstacle |
| Escape | All blocked | Drive toward most open direction |

### Dynamic Obstacles

Two red boxes are spawned in the robot's path during the mission:

| Obstacle | World Position | Trigger Leg | Duration |
|----------|---------------|-------------|----------|
| Obstacle 1 | (0.87, 0.53) | T1 → T2 | 6 seconds |
| Obstacle 2 | (0.83, −1.26) | Return leg | 6 seconds |

The robot stops completely (`vx=0, vy=0`) while `/dynamic_obstacle` is `True` and resumes when the obstacle is removed.

---

## Configuration

| File | Purpose |
|------|---------|
| `config/ekf_config.yaml` | EKF parameters — fuses `/imu` and `/odom` |
| `config/controllers.yaml` | ros2_control velocity/position controllers |
| `world/my_world.sdf` | Gazebo world with walls and static obstacles |
| `urdf/DeliveryRobot_2.urdf` | Robot model (body, 4 mecanum wheels, prismatic lid, 4 ultrasonic sensors, IMU) |

---

## License

Apache-2.0
