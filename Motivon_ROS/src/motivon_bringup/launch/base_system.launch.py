from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description():
    udp_port = LaunchConfiguration("udp_port")
    start_agent = LaunchConfiguration("start_agent")

    base_params = PathJoinSubstitution(
        [FindPackageShare("motivon_bringup"), "config", "base_params.yaml"]
    )
    ekf_config = PathJoinSubstitution(
        [FindPackageShare("motivon_bringup"), "config", "ekf.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "udp_port",
                default_value="8888",
                description="UDP port used by the micro-ROS agent.",
            ),
            DeclareLaunchArgument(
                "start_agent",
                default_value="true",
                description="Start the Wi-Fi UDP micro-ROS agent.",
            ),
            ExecuteProcess(
                cmd=[
                    "ros2",
                    "run",
                    "micro_ros_agent",
                    "micro_ros_agent",
                    "udp4",
                    "--port",
                    udp_port,
                ],
                output="screen",
                respawn=True,
                respawn_delay=2.0,
                condition=IfCondition(start_agent),
            ),
            Node(
                package="motivon_base",
                executable="wheel_odometry_node",
                name="wheel_odometry_node",
                output="screen",
                parameters=[base_params],
                respawn=True,
                respawn_delay=2.0,
            ),
            Node(
                package="robot_localization",
                executable="ekf_node",
                name="ekf_filter_node",
                output="screen",
                parameters=[ekf_config],
                remappings=[("odometry/filtered", "/odometry/filtered")],
                respawn=True,
                respawn_delay=2.0,
            ),
        ]
    )
