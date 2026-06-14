#!/usr/bin/env python3
"""Add controller spawner nodes back to the launch file.
gz_ros2_control sets up the hardware but spawners are needed to load+activate controllers."""
BASE = "/home/zeinazz/design_ws/src/mobile_robot_sim"
lf = BASE + "/launch/robot_gazebo.launch.py"

with open(lf, "r") as f:
    content = f.read()

# Check if spawners already exist
if 'jsb_spawner' in content or 'mecanum_spawner' in content or 'lid_spawner' in content:
    print("[SKIP] Spawner nodes already exist in launch file")
else:
    # Insert spawner definitions before "# Mecanum Drive Node"
    spawner_block = """    # Controller Spawners (staggered to let gz_ros2_control init first)
    jsb_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['joint_state_broadcaster'],
        output='screen'
    )
    delay_jsb = TimerAction(period=5.0, actions=[jsb_spawner])

    mecanum_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['wheel_velocity_controller'],
        output='screen'
    )
    delay_mecanum_spawner = TimerAction(period=6.0, actions=[mecanum_spawner])

    lid_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['lid_controller'],
        output='screen'
    )
    delay_lid_spawner = TimerAction(period=7.0, actions=[lid_spawner])

"""
    marker = "    # Mecanum Drive Node"
    if marker in content:
        content = content.replace(marker, spawner_block + marker)
        print("[OK] Added spawner nodes before Mecanum Drive Node section")
    else:
        print("[ERROR] Could not find marker to insert spawners")
        exit(1)

    # Also add spawner delays to the return block
    old_return = """    return LaunchDescription([
        gazebo,
        bridge_gz,
        node_gz_spawn_entity,
        robot_state_publisher_node,
        robot_localization_node,
        delay_mecanum_drive,
        delay_lid_control,
        delay_start_stop
    ])"""
    new_return = """    return LaunchDescription([
        gazebo,
        bridge_gz,
        node_gz_spawn_entity,
        robot_state_publisher_node,
        robot_localization_node,
        delay_jsb,
        delay_mecanum_spawner,
        delay_lid_spawner,
        delay_mecanum_drive,
        delay_lid_control,
        delay_start_stop
    ])"""
    if old_return in content:
        content = content.replace(old_return, new_return)
        print("[OK] Updated return block with spawner delays")
    else:
        print("[ERROR] Could not find return block to update")
        exit(1)

    with open(lf, "w") as f:
        f.write(content)

# Verify syntax
import py_compile
py_compile.compile(lf, doraise=True)
print("[OK] Launch file syntax valid")
