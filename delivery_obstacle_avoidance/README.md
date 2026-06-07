# Delivery Obstacle Avoidance ROS2 Package

This package is the first ROS2 version of the delivery robot obstacle layer.
It keeps the existing ESP Arduino PID sketch as the motor controller and uses
the ESP web endpoints from `Pose_Cascaded_GUI.ino`.

## Nodes

`ultrasonic_scan_node`

- Runs on the Raspberry Pi 5.
- Reads HC-SR04 sensors through `lgpio`.
- Uses the shared trigger pin and the four echo pins from the test script.
- Leaves servo GPIO output disabled for the first test, so the front/back
  sensors must be positioned manually at center. Servo output and scanning can
  be enabled later with `enable_servo_output: true` and
  `enable_servo_scan: true`.
- Sends one shared trigger pulse and captures all four echo lines from that
  measurement cycle. The default cycle is `80 ms`, above the HC-SR04 minimum
  recommended interval.
- Publishes filtered JSON on `/obstacle/scan`.
- Publishes every unfiltered measurement on `/obstacle/raw_scan`.

`esp_http_bridge_node`

- Runs on the Raspberry Pi 5.
- Polls `http://192.168.1.112/data`.
- Polls at 4 Hz, serializes every ESP request, and skips telemetry whenever a
  motion command is active so the synchronous ESP web server is not flooded.
- Keeps only the newest queued ROS motion command and limits repeated STOP
  attempts to one per second, including when the ESP is unavailable.
- Identifies every request as ROS traffic. While ROS heartbeats are present,
  the ESP makes the GUI observer-only except for its emergency STOP button.
- Uses a versioned controller token, so commands from an accidentally surviving
  older bridge process are rejected by the ESP instead of competing with the
  current supervisor.
- The ESP stops locally if the ROS heartbeat or Wi-Fi connection is lost, so
  communication failure does not depend on another HTTP STOP succeeding.
- Publishes ESP pose/status JSON on `/esp/data`.
- Subscribes to the actuator-only `/robot/motion_command` topic.
- Converts ROS commands into ESP HTTP calls such as `/stop` and `/pose`.

`obstacle_decision_node`

- Subscribes to `/obstacle/scan`, `/obstacle/raw_scan`, and `/esp/data`.
- Accepts operator requests on `/operator/motion_command`, clears any previous
  avoidance trial only after an explicit reset, and is the only normal
  publisher to the actuator topic. Do not publish test commands directly to
  `/robot/motion_command`.
- Detects a GUI STOP counter reported by the ESP and cancels the autonomous
  trial, preventing obstacle removal from automatically restarting motion
  after a human emergency stop.
- Stops at `22 cm` when the sensor in the active translation direction detects
  an obstacle. The front, back, left, and right movement thresholds are equal.
- Uses fresh raw readings for the immediate stop path instead of waiting for
  the five-sample median filter.
- Stops if the ultrasonic message stream becomes stale.
- Uses ESP chassis commands, pose targets, and wheel targets to determine the
  active movement direction. This covers pose mode and GUI manual movement.
- Applies directional safety to front, back, left, and right movement.
- Waits `static_wait_s`, currently 10 seconds.
- If the obstacle clears before then and remains beyond `front_clear_cm` for
  the configured confirmation time, it resumes the saved ESP pose target.
- For a static obstacle encountered while moving forward, it chooses the
  larger valid left/right reading and uses continuous pose-controlled motion
  with sensor events rather than fixed obstacle dimensions:
  - strafe toward a maximum safety cap until the centered front sensor clears;
  - continue sideways by the calibrated `0.34 m` body-clearance margin;
  - move forward until the inner side sensor sees and then clears the obstacle;
  - continue forward by the calibrated `0.38 m` body-clearance margin;
  - strafe back to the saved original path line;
  - resume the saved destination.
- For a static obstacle encountered while strafing left or right, the same
  sequence is mirrored:
  - choose whichever of the centered front/back sensors reports more space;
  - move front or back until the blocked side sensor clears the first edge;
  - add a `0.38 m` front/back body-clearance margin;
  - continue the original strafe until the obstacle-facing front/back sensor
    sees and then clears the obstacle's far edge;
  - add a `0.34 m` sideways body-clearance margin;
  - move in the opposite front/back direction to return to the original
    sideways path, then resume the saved destination.
- The temporary pose targets are maximum travel guards, not the condition for
  finding an obstacle edge. Front and side sensor events end the search stages;
  reaching a guard without the expected event aborts the maneuver.
- Edge transitions use the unfiltered ultrasonic stream for low delay. The
  detector first observes the nearby obstacle (`<=45 cm`), then requires a jump
  of at least `25 cm` to a reading of at least `60 cm`, followed by one more far
  reading. With the `80 ms` scan period this normally confirms an edge in two
  samples instead of waiting for the five-reading median and another `0.4 s`.
  The slower filtered-clear test remains as a fallback if an edge changes too
  gradually to satisfy the jump test.
- The same transition detector is used on the inner side sensor when finding
  the obstacle's rear edge, reducing unnecessary forward travel before the
  configured forward body margin is added.
- Before starting an avoidance leg, the chosen direction must initially be
  farther than `22 cm`. During movement, a new obstacle is handled using the
  normal directional stop distance of `22 cm`: the robot stops, waits, and continues
  the unfinished leg after that direction clears beyond `40 cm`.
- If a temporary obstacle blocks the active movement direction during
  avoidance, the robot stops and waits without a time limit. This applies to
  front, back, left, and right movement. Once that same direction remains
  clear beyond its release distance, the exact unfinished avoidance target is
  sent again and the maneuver continues.
- Aborts on stale sensor/ESP data, an active movement-stage timeout, missing
  pose data, or missing odometry progress. Waiting for a temporary directional
  obstacle does not consume the movement-stage timeout.
- After one avoidance completes and the original destination resumes, the same
  detection sequence remains active for later obstacles on the route.
- Version 1 does not build a second avoidance maneuver inside an unfinished
  first maneuver. A new obstacle pauses the current step and the robot waits
  for it to move away. If it is actually another static obstacle, the robot
  safely remains stopped because nested avoidance is intentionally deferred.

The launch terminal prints plain state changes beginning with `STATUS:`, and
the ESP GUI shows the same text, current state code, front/left/right readings,
reason, and whether a reset is required.

During the sideways part of static avoidance, the launch terminal also keeps
two diagnostic lines in its history:

- `STRAFE MEASURE 1/2` is printed at the exact moment the centered front sensor
  confirms that the obstacle edge has cleared. It includes the lateral travel,
  ESP pose, filtered/raw front readings, side clearance, and the next commanded
  margin.
- `STRAFE MEASURE 2/2` is printed when that extra sideways margin finishes. It
  includes total lateral travel, ESP pose, commanded margin, encoder-estimated
  margin, encoder error, and the inner side-sensor gap.

These lines remove the need to watch or mark the robot while it is moving.
The encoder distance is useful for checking command execution, but it is not an
independent physical measurement because the ESP pose controller uses the same
wheel encoders. Compare it with the ultrasonic gap and one tape measurement
after the robot has safely stopped.

For distance diagnosis, `avoidance_measurement_mode` first stops before any
sideways movement to provide a floor-mark reference, then stops at five
checkpoints:

1. The front sensor declares the obstacle edge clear.
2. The extra lateral margin finishes.
3. The inner side sensor first sees the obstacle during forward movement.
4. The inner side sensor declares the rear edge clear.
5. The extra forward margin finishes.

At every checkpoint, measure while the robot remains stopped. Continue to the
next piece from a sourced Pi terminal:

```bash
ros2 topic pub --once /operator/motion_command std_msgs/msg/String \
  "data: '{\"type\":\"continue_measurement\"}'"
```

Normal configuration uses `avoidance_measurement_mode: false`, so avoidance is
continuous. Temporarily set it to `true` only when stopped checkpoints are
needed for another distance investigation.

The checkpoint sends one STOP when entered. After Continue Measurement, ROS
retries the next pose command until fresh ESP telemetry confirms that the exact
avoidance target is active. The bridge keeps an ordered command queue so an
older STOP cannot silently replace the continuation pose.

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

`/operator/motion_command` uses `std_msgs/String` with JSON for terminal or
navigation requests:

```json
{"type": "stop", "reason": "front_obstacle"}
```

or:

```json
{"type": "pose", "x": 1.2, "y": 0.7, "yaw": 0.0}
```

`stop` cancels all saved avoidance state and keeps the robot stopped.
`reset_trial` verifies fresh ultrasonic and ESP data, changes the state to
`READY`, and still does not move. A new pose is rejected after an avoidance
failure, operator STOP, or data fault until `reset_trial` succeeds.
`/robot/motion_command` has the same internal schema but is reserved for the
decision node and bridge.

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

Use either the ESP GUI or a second sourced terminal for test commands. While
ROS is active, the GUI `Go To Pose`, `Reset Trial`, `Zero Pose`, and `IMU Cal`
buttons are relayed through the same ROS supervisor used by terminal commands.
The GUI also displays the current obstacle state and distance readings.

After an operator STOP or unsuccessful avoidance, reset explicitly before
starting the next trial:

```bash
ros2 topic pub --once /operator/motion_command std_msgs/msg/String \
  "data: '{\"type\":\"zero_pose\"}'"
ros2 topic pub --once /operator/motion_command std_msgs/msg/String \
  "data: '{\"type\":\"reset_trial\"}'"
ros2 topic pub --once /operator/motion_command std_msgs/msg/String \
  "data: '{\"type\":\"pose\",\"x\":2.0,\"y\":0.0,\"yaw\":0.0}'"
```

Emergency terminal stop:

```bash
ros2 topic pub --once /operator/motion_command std_msgs/msg/String \
  "data: '{\"type\":\"stop\"}'"
```

Before launching another copy, stop the existing launch with `Ctrl+C` and
confirm `ros2 node list` no longer contains these nodes. Multiple launch
copies would create multiple decision nodes commanding the same robot.

Make sure the ESP is reachable at:

```text
http://192.168.1.112
```

## First Tuning Values

- Front blocked: `22 cm`
- Front clear: `40 cm`
- Back blocked while reversing: `22 cm`
- Back clear before resuming: `40 cm`
- Avoidance side choice: larger valid side reading
- Side-obstacle detour choice: larger valid front/back reading
- Minimum initial clearance in the chosen avoidance direction: `22 cm`
- Left/right blocked during ordinary motion: `22 cm`
- Left/right clear before resuming: `40 cm`
- Sensor scan period: `0.08 s`
- Sensor stream stale timeout: `0.35 s`
- Front clear confirmation: `0.40 s`
- Dynamic/static threshold: `10 s`
- Extra lateral travel after front edge: `0.34 m`
- Extra forward travel after rear edge: `0.38 m`
- For an obstacle encountered while strafing: extra front/back travel after
  the first edge is `0.38 m`, and extra sideways travel after the far edge is
  `0.34 m`.
- Maximum total lateral excursion: `0.90 m`; a live side obstacle pauses motion
  at the normal `22 cm` directional stop distance
- Maximum forward rear-edge search: `1.20 m`
- Avoidance stage timeout: `15 s`
- Odometry no-progress timeout: `3 s`

These are intentionally conservative because the robot is about `59.7 cm` long
and `48.2 cm` wide. The first physical static-obstacle test uses a flat
`40 cm` wide, `20 cm` deep obstacle.

All four HC-SR04 modules still share one trigger wire, so they transmit at the
same time and cross-talk remains a hardware limitation. Separate trigger lines
or sensors designed for multi-sensor operation would provide stronger
independence for a final safety system.

## Front Servo Calibration

Run `front_servo_calibration_node` by itself while the normal obstacle launch is
stopped. Send one pulse command at a time on
`/calibration/front_servo_pulse`. The node waits `0.5 s`, takes three front
ultrasonic samples, and prints/publishes their median. Start at `1500 us`, move
in small steps, and record which pulse physically points left, center, and
right.

The calibrated front values are currently:

```text
1100 us = approximately 45 degrees right
1500 us = center
1900 us = approximately 45 degrees left
```

Publishing an empty message on `/calibration/front_servo_scan` runs a stationary
seven-position scan from right 45 degrees through center to left 45 degrees,
then returns the sensor to center.
