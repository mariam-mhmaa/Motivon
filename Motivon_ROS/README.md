# Motivon ROS 2 Base Integration

This workspace contains the integrated real-robot base stack for ROS 2 Jazzy.
The original standalone PID, simulation, obstacle, vision, and GUI files remain
unchanged outside this directory.

## Implemented components

- `esp32_base_node`: ESP32 micro-ROS firmware with the tested wheel PID,
  encoders, BMI160 gyroscope, automatic gyro calibration, Wi-Fi UDP transport,
  command timeout, measured IMU health, staggered sensor telemetry, and
  debounced reconnect handling.
- `wheel_odometry_node`: Raspberry Pi ROS 2 node that converts the four measured
  wheel velocities into mecanum odometry and publishes zero velocity when the
  ESP32 wheel-state stream becomes stale.
- `ekf_filter_node`: `robot_localization` EKF configured to fuse wheel velocity
  for X/Y translation and BMI160 yaw rate for heading. Encoder-derived yaw is
  deliberately excluded so wheel-speed imbalance cannot rotate the navigation
  frame. The ESP32 measures gyro bias and stationary noise during startup.
- `navigation_node`: Executes measured named routes using filtered odometry,
  conservative initial controller limits, stale-localization stopping with
  stable-data recovery, and typed action feedback.

## Navigation coordinate frame

The real 4.5 m by 4.5 m map uses the back-right arena corner nearest HOME as
`(0.0, 0.0)`. From that corner, positive X points toward WP1 and positive Y
points toward the robot's left at its starting pose. The robot center is the
reference point.

Configured HOME is `(0.65, 0.65)`, not map zero. This is intentional. Calling
`/navigation/set_home` records which live odometry pose corresponds to that
physical map coordinate and to starting yaw zero. It does not silently redefine
an arbitrary stopping position as HOME.

The route measurements are stored in
`motivon_navigation/config/routes.yaml`, so corrected floor measurements do not
require Python changes.

## First WP1 navigation test

The WP1 launch starts the base, EKF, micro-ROS agent, and navigation node. It
does not start robot motion automatically.

For inspection without motor output:

```bash
ros2 launch motivon_bringup wp1_navigation_test.launch.py
```

For the later supervised floor test, explicitly route navigation to the ESP32:

```bash
ros2 launch motivon_bringup wp1_navigation_test.launch.py \
  command_topic:=/cmd_vel
```

Place the robot center at the marked HOME point and face it toward WP1. After
fresh filtered odometry appears, set the map/odometry relationship:

```bash
ros2 service call /navigation/set_home std_srvs/srv/Trigger
```

Enable the base only when the test area is clear:

```bash
ros2 topic pub --once /base/enable std_msgs/msg/Bool "{data: true}"
```

Send only the first target with a ten-second stationary hold:

```bash
ros2 action send_goal /navigation/navigate_to_target \
  motivon_interfaces/action/NavigateToTarget \
  "{target_name: 'WP1', hold_time_s: 10.0}" --feedback
```

The action is rejected unless HOME has been set, no other goal is active, and
the requested segment is the configured next segment. Launching or setting
HOME never commands movement. HOME -> WP1, WP1 -> WP2, and WP2 -> WP3 begin
translation without a separate pre-rotation. The controller still corrects
heading continuously while travelling. WP3 -> HOME performs the required
180-degree turn, then aligns to the starting yaw after reaching HOME.

## Supervised WP1 then WP2 test

Do not change controller gains or odometry calibration for this test. Launch
the same stack with navigation explicitly connected to the ESP32:

```bash
ros2 launch motivon_bringup wp1_navigation_test.launch.py \
  command_topic:=/cmd_vel
```

Place the robot at HOME, face it toward WP1, wait for fresh localization, and
call `/navigation/set_home` exactly once. Then run:

```bash
ros2 run motivon_navigation two_station_test --area-clear
```

The runner enables the base, sends WP1, waits for a successful result, then
sends WP2. It stops and disables the base immediately if WP1 fails or either
goal times out. The WP1-to-WP2 path first strafes left to `WP12`, then drives
forward to `WP2`, while maintaining map yaw zero.

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
The ESP32 stops after 750 ms without a fresh command, starts disabled after
boot or micro-ROS reconnection, and never accepts pose targets directly. These
rules prevent old or competing commands from repeatedly taking control.

## Raspberry Pi setup

Install `robot_localization` from the Jazzy package repository:

```bash
sudo apt install ros-jazzy-robot-localization
```

On Ubuntu 24.04 ARM64, build the Jazzy micro-ROS agent with
`micro_ros_setup`; `ros-jazzy-micro-ros-agent` was not available from the
configured package repository on the Raspberry Pi used for this project.

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

The Raspberry Pi / micro-ROS agent is reserved at `192.168.1.111` on the home
network. The ESP32 uses DHCP because it initiates the connection to the agent
and does not require a fixed address. This avoids conflicts with other clients.

## ESP32 setup

1. Install the Jazzy release of `micro_ros_arduino`.
2. Open `firmware/esp32_base/esp32_base.ino`.
3. Confirm the ignored `wifi_config.h` values.
4. Flash the ESP32.
5. Keep the robot stationary during the six-second startup gyro calibration.

The firmware uses the physical constants and corrected pin mapping from
`PID/PID`. The old ESP32 HTTP GUI and outer pose controller are intentionally
not part of integrated operation.

Use ESP32 Arduino core `2.0.2` with `micro_ros_arduino 2.0.8-jazzy`. This is
the ESP32 core version supported by the official precompiled Jazzy library.
Do not use an Iron Arduino client with the Jazzy agent. The sketch supports
both core-2 and core-3 PWM APIs, but core `3.3.8` produced unusable Wi-Fi
telemetry timing during hardware testing.

Use only one ESP32 power source at a time. USB-only communication was stable;
the robot-supplied 5 V path showed packet loss and latency and requires
electrical investigation before autonomous operation.

Do not run floor navigation unless `tools/check_base_topics.py` and the
wheels-lifted `tools/check_motion_continuity.py` test both pass using the same
power source that will be used for navigation.

## Verification tools

`tools/check_base_topics.py` checks ESP32 node discovery, all four telemetry
topics, rates, maximum gaps, message contents, synchronized timestamps, and
heartbeat continuity. It is a telemetry test, not a motor test.

`tools/check_base_command_path.py` tests `/base/enable`, `/cmd_vel`, forward
wheel response, and the 750 ms command watchdog. It refuses to run unless
`--wheels-lifted` is supplied. Run it only after all drive wheels are physically
off the floor and the robot power system is stable.

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
