# Delivery Obstacle Avoidance ROS2 Package

This package is the first ROS2 version of the delivery robot obstacle layer.
It keeps the existing ESP Arduino PID sketch as the motor controller and uses
the ESP web endpoints from `Pose_Cascaded_GUI.ino`.

## Nodes

`ultrasonic_scan_node`

- Runs on the Raspberry Pi 5.
- Reads HC-SR04 sensors through `lgpio`.
- Uses the shared trigger pin and the four echo pins from the test script.
- Holds the front/back servos at center for the first test. Servo scanning can
  be enabled later with `enable_servo_scan: true`.
- Publishes filtered JSON on `/obstacle/scan`.

`esp_http_bridge_node`

- Runs on the Raspberry Pi 5.
- Polls `http://172.20.10.3/data`.
- Publishes ESP pose/status JSON on `/esp/data`.
- Subscribes to `/obstacle/motion_command`.
- Converts ROS commands into ESP HTTP calls such as `/stop` and `/pose`.

`obstacle_decision_node`

- Subscribes to `/obstacle/scan` and `/esp/data`.
- Stops immediately when the front obstacle is closer than `front_blocked_cm`.
- Waits `static_wait_s`, currently 10 seconds.
- If the obstacle clears before then, it resumes the saved ESP pose target.
- If it stays blocked, it chooses left/right mainly from side clearance. Angled
  front readings are only a small tie breaker when both sides are open.
- Generates pose waypoints using ESP odometry:
  strafe sideways, move forward past the obstacle, strafe back to the original
  path line.
- Keeps supervising sensors during the maneuver and stops if unsafe.

## Topic Schemas

`/obstacle/scan` uses `std_msgs/String` with JSON:

```json
{
  "stamp": 123.4,
  "active_scan": {"front": "center", "back": "center"},
  "distances_cm": {
    "left": 100.0,
    "right": 95.0,
    "front_left": 82.0,
    "front_center": 40.0,
    "front_right": 76.0
  }
}
```

`/obstacle/motion_command` uses `std_msgs/String` with JSON:

```json
{"type": "stop", "reason": "front_obstacle"}
```

or:

```json
{"type": "pose", "x": 1.2, "y": 0.7, "yaw": 0.0}
```

## Build

From `ros2_ws`:

```bash
colcon build --symlink-install
source install/setup.bash
```

## Run

On the Raspberry Pi, with the ESP and Pi connected to the same hotspot:

```bash
ros2 launch delivery_obstacle_avoidance obstacle_avoidance.launch.py
```

Make sure the ESP is reachable at:

```text
http://172.20.10.3
```

## First Tuning Values

- Front blocked: `30 cm`
- Front clear: `40 cm`
- Side clear: `75 cm`
- Side emergency during avoidance: `15 cm`
- Dynamic/static threshold: `10 s`
- Side offset: `0.70 m`
- Pass distance: `0.90 m`

These are intentionally conservative because the robot is about `59.7 cm` long
and `48.2 cm` wide.
