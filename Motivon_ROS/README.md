# Motivon ROS 2 Base Integration

This workspace contains the integrated real-robot base stack for ROS 2 Jazzy.
The original standalone PID, simulation, obstacle, vision, and GUI files remain
unchanged outside this directory.

## Implemented components

- `esp32_base_node`: ESP32 micro-ROS firmware with the tested wheel PID,
  encoders, BMI160 gyroscope, automatic gyro calibration, Wi-Fi UDP transport,
  command timeout, measured IMU health, and rate-limited reconnect handling.
- `wheel_odometry_node`: Raspberry Pi ROS 2 node that converts the four measured
  wheel velocities into mecanum odometry.
- `ekf_filter_node`: `robot_localization` EKF configured to fuse wheel velocity
  and BMI160 yaw rate. The ESP32 measures gyro bias and stationary noise during
  every startup calibration and publishes that measured angular covariance.

## ROS interface

The ESP32 subscribes to:

| Topic | Type |
|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` |
| `/base/enable` | `std_msgs/msg/Bool` |

The ESP32 publishes:

| Topic | Type |
|---|---|
| `/base/wheel_states` | `sensor_msgs/msg/JointState` |
| `/imu/data_raw` | `sensor_msgs/msg/Imu` |
| `/base/imu_ok` | `std_msgs/msg/Bool` |
| `/base/heartbeat` | `std_msgs/msg/UInt32` |

The Raspberry Pi publishes:

| Topic | Type |
|---|---|
| `/wheel/odometry` | `nav_msgs/msg/Odometry` |
| `/odometry/filtered` | `nav_msgs/msg/Odometry` |

Only the future `cmd_vel_gate_node` may publish `/cmd_vel` in the complete
system. During base testing, publish test commands from one terminal only.
The ESP32 stops after 500 ms without a fresh command, starts disabled after
boot or micro-ROS reconnection, and never accepts pose targets directly. These
rules prevent old or competing commands from repeatedly taking control.

## Raspberry Pi setup

Install the required Jazzy packages:

```bash
sudo apt install ros-jazzy-robot-localization ros-jazzy-micro-ros-agent
```

Build from this directory:

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

Start the base stack and UDP micro-ROS agent:

```bash
ros2 launch motivon_bringup base_system.launch.py
```

The agent listens on UDP port `8888`.

## ESP32 setup

1. Install the Jazzy release of `micro_ros_arduino`.
2. Open `firmware/esp32_base/esp32_base.ino`.
3. Confirm the ignored `wifi_config.h` values.
4. Flash the ESP32.
5. Keep the robot stationary during the six-second startup gyro calibration.

The firmware uses the physical constants and corrected pin mapping from
`PID/PID`. The old ESP32 HTTP GUI and outer pose controller are intentionally
not part of integrated operation.

The official Jazzy `micro_ros_arduino` documentation lists ESP32 Arduino core
`2.0.2` as its supported ESP32 target. This sketch supports both PWM APIs and
was compile-verified with `micro_ros_arduino 2.0.8-jazzy` on ESP32 core `3.3.8`.
Hardware communication and timing still need to be verified on the robot.

## First safe communication test

Lift the wheels clear of the floor, then enable the base:

```bash
ros2 topic pub --once /base/enable std_msgs/msg/Bool "{data: true}"
```

Publish a low forward command continuously:

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.05, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

Stopping that publisher makes the ESP32 stop the wheels after the configured
command timeout. Disable the base explicitly after testing:

```bash
ros2 topic pub --once /base/enable std_msgs/msg/Bool "{data: false}"
```

## Odometry reset

Place the robot at HOME and call:

```bash
ros2 service call /wheel_odometry/reset std_srvs/srv/Trigger
```

The EKF should also be restarted or reset before starting a new mission so both
odometry sources share the same HOME origin.
