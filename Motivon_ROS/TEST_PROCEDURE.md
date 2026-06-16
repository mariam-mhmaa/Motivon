# Motivon Base and Navigation Test Procedure

Run the stages in order. Do not continue after a failed stage.

## 1. Copy the updated ROS files

Run in Windows PowerShell:

```powershell
scp -r `
  "D:\GitHub_Repos\Motivon_Repo\Motivon\Motivon_ROS\src" `
  "D:\GitHub_Repos\Motivon_Repo\Motivon\Motivon_ROS\tools" `
  "D:\GitHub_Repos\Motivon_Repo\Motivon\Motivon_ROS\firmware" `
  mohamed@192.168.1.111:~/Motivon_ROS/

scp `
  "D:\GitHub_Repos\Motivon_Repo\Motivon\Motivon_ROS\README.md" `
  "D:\GitHub_Repos\Motivon_Repo\Motivon\Motivon_ROS\TEST_PROCEDURE.md" `
  mohamed@192.168.1.111:~/Motivon_ROS/
```

## 2. Build and test on the Raspberry Pi

Still in Windows PowerShell:

```powershell
ssh mohamed@192.168.1.111
```

Then run inside the Pi SSH session:

```bash
cd ~/Motivon_ROS
source /opt/ros/jazzy/setup.bash

colcon build --symlink-install \
  --packages-select \
  motivon_interfaces motivon_base motivon_navigation motivon_bringup

source install/setup.bash

colcon test \
  --packages-select \
  motivon_interfaces motivon_base motivon_navigation motivon_bringup \
  --event-handlers console_cohesion+

colcon test-result --all --verbose

exit
```

The expected result is zero test failures.

## 3. Flash the ESP32

1. Turn off robot power.
2. Power the ESP32 from USB only.
3. Open the sketch from Windows PowerShell:

```powershell
& "C:\Program Files\Arduino IDE\Arduino IDE.exe" `
  "D:\GitHub_Repos\Motivon_Repo\Motivon\Motivon_ROS\firmware\esp32_base\esp32_base.ino"
```

4. In Arduino IDE select `DOIT ESP32 DEVKIT V1` and the ESP32 COM port.
5. Verify that the installed ESP32 board core is `2.0.2`.
6. Press Upload yourself and wait for `Done uploading`.
7. Disconnect USB before turning robot power on.

## 4. Start from a clean Pi session

Charge the robot battery using its correct charger before testing. Power the
ESP32 from the robot only and press the physical E-stop.

From Windows PowerShell, SSH to the Pi:

```powershell
ssh mohamed@192.168.1.111
```

Then reboot the Pi once to remove old agents and nodes:

```bash
sudo reboot
```

The SSH connection will close; this is expected.

After the Pi returns, open Windows PowerShell Terminal 1:

```powershell
ssh mohamed@192.168.1.111
```

Inside Pi Terminal 1:

```bash
source /opt/ros/jazzy/setup.bash
source ~/micro_ros_ws/install/local_setup.bash
source ~/Motivon_ROS/install/setup.bash

ros2 launch motivon_bringup base_system.launch.py
```

Leave Terminal 1 running.

## 5. Robot-power telemetry gate

Open a second Windows PowerShell window and SSH to the Pi:

```powershell
ssh mohamed@192.168.1.111
```

Inside Pi Terminal 2:

```bash
source /opt/ros/jazzy/setup.bash
source ~/micro_ros_ws/install/local_setup.bash
source ~/Motivon_ROS/install/setup.bash

ros2 node list

ESP_IP=$(ip neigh show | awk \
  'tolower($0) ~ /5c:01:3b:34:56:80/ {print $1; exit}')
echo "ESP IP: $ESP_IP"
```

Do not continue if `ESP IP` is empty. Otherwise run:

```bash
ping -c 100 -i 0.2 "$ESP_IP"
python3 ~/Motivon_ROS/tools/check_base_topics.py --duration 70
```

Required result:

- Ping has zero packet loss.
- `BASE TELEMETRY TEST: PASS`.

The E-stop remains pressed for this stage.

## 6. Wheels-lifted motion gate

Lift all four drive wheels completely off the floor. Keep the robot supported
securely, then release the E-stop.

In Pi Terminal 2 run:

```bash
python3 ~/Motivon_ROS/tools/check_base_command_path.py \
  --wheels-lifted

python3 ~/Motivon_ROS/tools/check_base_motion_directions.py \
  --wheels-lifted

python3 ~/Motivon_ROS/tools/check_motion_continuity.py \
  --wheels-lifted \
  --duration 45
```

All three tests must print `PASS`. Press the E-stop after they finish.

## 7. Start navigation

In Pi Terminal 1 press Ctrl+C. Then run:

```bash
ros2 launch motivon_bringup wp1_navigation_test.launch.py \
  command_topic:=/cmd_vel
```

Put the robot on the floor at the marked HOME center, facing WP1. Keep the
E-stop pressed.

In Pi Terminal 2:

```bash
python3 ~/Motivon_ROS/tools/check_navigation_preflight.py \
  --duration 20

ros2 service call /navigation/set_home \
  std_srvs/srv/Trigger "{}"
```

Both commands must pass, and `set_home` must return `success=True`.

## 8. Test HOME to WP1 only

Clear the HOME-to-WP1 floor area and release the E-stop.

In Pi Terminal 2:

```bash
ros2 topic pub --once --wait-matching-subscriptions 1 \
  /base/enable std_msgs/msg/Bool "{data: true}"

ros2 action send_goal \
  /navigation/navigate_to_target \
  motivon_interfaces/action/NavigateToTarget \
  "{target_name: 'WP1', hold_time_s: 10.0}" \
  --feedback

ros2 topic pub --once --wait-matching-subscriptions 1 \
  /base/enable std_msgs/msg/Bool "{data: false}"
```

The robot must begin with forward translation, without a separate initial
rotation. Stop the test with the E-stop if it moves in an unsafe direction.

## 9. Test HOME to WP1 to WP12 to WP2

Press the E-stop. Return the robot center to HOME and face it toward WP1.

In Pi Terminal 2:

```bash
ros2 service call /navigation/set_home \
  std_srvs/srv/Trigger "{}"
```

After `success=True`, clear the entire route and release the E-stop:

```bash
ros2 run motivon_navigation two_station_test --area-clear
```

The expected motion is:

```text
HOME -> WP1: forward
WP1 -> WP12: left strafe
WP12 -> WP2: forward
```

The runner disables the base after success or failure.
