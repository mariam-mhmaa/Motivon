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

    ws_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(pkg_share))))
    collection_models = os.path.join(ws_root, 'src', 'mobile_robot_sim', 'worldd',
                                     'gazebo_models_worlds_collection', 'models')
    osrf_models = os.path.expanduser('~/.gz/models')
    gz_resource_path = f'{collection_models}:{osrf_models}'

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

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [os.path.join(get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')]
        ),
        launch_arguments={'gz_args': f'-r -v 4 {world_file_path}'}.items()
    )

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

    node_gz_spawn_entity = Node(
        package='ros_gz_sim',
        executable='create',
        output='screen',
        arguments=[
            '-topic', 'robot_description',
            '-name', 'DeliveryRobot_Sim',
            '-x', '1.30', '-y', '-1.50', '-z', '0.3',
            '-R', '0.0', '-P', '0.0', '-Y', '1.5708'
        ],
        parameters=[{'use_sim_time': True}]
    )

    kill_stale = ExecuteProcess(
        cmd=['bash', '-c',
             'pkill -9 -f "gz sim"   2>/dev/null; '
             'pkill -9 -f "ruby.*gz" 2>/dev/null; '
             'pkill -9 -x gz         2>/dev/null; '
             'sleep 0.5; true'],
        output='log')

    delay_gazebo = TimerAction(period=2.0, actions=[gazebo])
    delay_spawn  = TimerAction(period=7.0, actions=[node_gz_spawn_entity])

    robot_localization_node = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[ekf_config_path, {'use_sim_time': True}]
    )
    delay_ekf = TimerAction(period=10.0, actions=[robot_localization_node])

    lid_control_node = Node(
        package='mobile_robot_sim',
        executable='lid_control_node.py',
        name='lid_control_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )
    delay_lid_control = TimerAction(period=10.0, actions=[lid_control_node])

    encoder_odometry_node = Node(
        package='mobile_robot_sim',
        executable='encoder_odometry_node.py',
        name='encoder_odometry_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )
    delay_encoder_odometry = TimerAction(period=10.5, actions=[encoder_odometry_node])

    imu_node = Node(
        package='mobile_robot_sim',
        executable='imu_node.py',
        name='imu_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )
    delay_imu = TimerAction(period=10.5, actions=[imu_node])

    ultrasonic_node = Node(
        package='mobile_robot_sim',
        executable='ultrasonic_node.py',
        name='ultrasonic_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )
    delay_ultrasonic = TimerAction(period=10.5, actions=[ultrasonic_node])

    start_stop_node = Node(
        package='mobile_robot_sim',
        executable='start_stop_node.py',
        name='start_stop_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )
    delay_start_stop = TimerAction(period=10.0, actions=[start_stop_node])

    pid_interface_node = Node(
        package='mobile_robot_sim',
        executable='pid_interface_node.py',
        name='pid_interface_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )
    delay_pid_interface = TimerAction(period=10.5, actions=[pid_interface_node])

    state_led_node = Node(
        package='mobile_robot_sim',
        executable='state_led_node.py',
        name='state_led_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )
    delay_state_led = TimerAction(period=10.5, actions=[state_led_node])

    vision_auth_node = Node(
        package='mobile_robot_sim',
        executable='vision_auth_node.py',
        name='vision_auth_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )
    delay_vision_auth = TimerAction(period=10.5, actions=[vision_auth_node])

    mecanum_drive_node = Node(
        package='mobile_robot_sim',
        executable='mecanum_drive_node.py',
        name='mecanum_drive_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )
    delay_mecanum = TimerAction(period=10.0, actions=[mecanum_drive_node])

    set_gz_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=gz_resource_path
    )

    # arena_navigator_node is intentionally excluded so test scripts
    # have exclusive control of /cmd_vel_input

    return LaunchDescription([
        set_gz_resource_path,
        kill_stale,
        delay_gazebo,
        bridge_gz,
        robot_state_publisher_node,
        delay_spawn,
        delay_ekf,
        delay_lid_control,
        delay_encoder_odometry,
        delay_imu,
        delay_ultrasonic,
        delay_start_stop,
        delay_pid_interface,
        delay_state_led,
        delay_vision_auth,
        delay_mecanum,
    ])
