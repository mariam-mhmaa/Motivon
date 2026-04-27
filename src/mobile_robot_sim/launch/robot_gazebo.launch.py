from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction, SetEnvironmentVariable, ExecuteProcess
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import Command
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_share = FindPackageShare(package='mobile_robot_sim').find('mobile_robot_sim')
    default_model_path = os.path.join(pkg_share, 'urdf', 'DeliveryRobot_2.urdf')
    world_file_path = os.path.join(pkg_share, 'world', 'arena_world.sdf')
    ekf_config_path = os.path.join(pkg_share, 'config', 'ekf_config.yaml')

    # Model paths for workshop_example world
    # pkg_share is install/.../share/mobile_robot_sim — workspace root is 4 levels up
    ws_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(pkg_share))))
    collection_models = os.path.join(ws_root, 'src', 'mobile_robot_sim', 'worldd',
                                     'gazebo_models_worlds_collection', 'models')
    osrf_models = os.path.expanduser('~/.gz/models')
    gz_resource_path = f'{collection_models}:{osrf_models}'

    # Robot State Publisher
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[
            {
                'robot_description': ParameterValue(Command(['xacro ', default_model_path]), value_type=str),
                'use_sim_time': True
            }
        ]
    )

    # Gazebo Sim Launch
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [os.path.join(get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')]
        ),
        launch_arguments={'gz_args': f'-r -v 4 {world_file_path}'}.items()
    )

    # ROS-Gazebo Bridge
    # /cmd_vel on ROS side -> /model/DeliveryRobot_Sim/cmd_vel on Gazebo side (MecanumDrive listens here)
    # /model/DeliveryRobot_Sim/odometry on Gazebo side -> /odom on ROS side
    bridge_gz = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        output='screen',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/model/DeliveryRobot_Sim/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
            '/model/DeliveryRobot_Sim/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry',
            '/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model',
            '/imu@sensor_msgs/msg/Imu[gz.msgs.IMU',
            '/ultrasonic/front@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            '/ultrasonic/back@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            '/ultrasonic/left@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            '/ultrasonic/right@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            '/lid_position@std_msgs/msg/Float64]gz.msgs.Double',
        ],
        remappings=[
            ('/model/DeliveryRobot_Sim/cmd_vel', '/cmd_vel'),
            ('/model/DeliveryRobot_Sim/odometry', '/odom'),
        ]
    )

    # Spawn robot
    node_gz_spawn_entity = Node(
        package='ros_gz_sim',
        executable='create',
        output='screen',
        arguments=[
            '-topic', 'robot_description',
            '-name', 'DeliveryRobot_Sim',
            '-x', '1.55', '-y', '-3.43', '-z', '0.3',
            '-R', '0.0', '-P', '0.0', '-Y', '1.5708'
        ],
        parameters=[{'use_sim_time': True}]
    )

    # ── Kill stale Gazebo processes from any previous run ────────────────
    # If a previous gz sim is still running, launching again would attach to
    # the old world where the robot is at its last position and the entity
    # 'DeliveryRobot_Sim' already exists, causing the respawn to fail silently.
    kill_stale = ExecuteProcess(
        cmd=['bash', '-c',
             'pkill -9 -f "gz sim"   2>/dev/null; '
             'pkill -9 -f "ruby.*gz" 2>/dev/null; '
             'pkill -9 -x gz         2>/dev/null; '
             'sleep 0.5; true'],
        output='log')

    # Delay Gazebo start by 2 s so the kill above finishes first
    delay_gazebo = TimerAction(period=2.0, actions=[gazebo])

    # Spawn at t=7 s — Gazebo starts at t=2 and needs ~5 s to fully load
    delay_spawn = TimerAction(period=7.0, actions=[node_gz_spawn_entity])

    # EKF, lid control, start-stop all start at t=10 s so the robot is
    # physically in place and the bridge is delivering real odometry
    robot_localization_node = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[ekf_config_path, {'use_sim_time': True}]
    )
    delay_ekf = TimerAction(period=10.0, actions=[robot_localization_node])

    # Lid Control Node (Gazebo-native JointPositionController handles the physics)
    lid_control_node = Node(
        package='mobile_robot_sim',
        executable='lid_control_node.py',
        name='lid_control_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )
    delay_lid_control = TimerAction(period=10.0, actions=[lid_control_node])

    # Start/Stop Node (gates /cmd_vel_input -> /cmd_vel)
    start_stop_node = Node(
        package='mobile_robot_sim',
        executable='start_stop_node.py',
        name='start_stop_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )
    delay_start_stop = TimerAction(period=10.0, actions=[start_stop_node])

    set_gz_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=gz_resource_path
    )

    # Arena Navigator Node – delivery route for the 4.5x4.5m arena
    navigator_node = Node(
        package='mobile_robot_sim',
        executable='arena_navigator_node.py',
        name='arena_navigator_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )
    delay_navigator = TimerAction(period=13.0, actions=[navigator_node])

    return LaunchDescription([
        set_gz_resource_path,
        kill_stale,                  # t=0: kill any stale gz sim
        delay_gazebo,                # t=2: fresh Gazebo world
        bridge_gz,                   # starts immediately (retries until Gazebo ready)
        robot_state_publisher_node,
        delay_spawn,                 # t=7: spawn robot
        delay_ekf,                   # t=10: EKF after robot is spawned
        delay_lid_control,           # t=10: lid control
        delay_start_stop,            # t=10: start-stop gate
        delay_navigator,             # t=13: arena navigation controller
    ])