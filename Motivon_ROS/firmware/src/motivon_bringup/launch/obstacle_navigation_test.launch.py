from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description():
    udp_port = LaunchConfiguration("udp_port")
    start_agent = LaunchConfiguration("start_agent")

    base_launch = PathJoinSubstitution(
        [
            FindPackageShare("motivon_bringup"),
            "launch",
            "base_system.launch.py",
        ]
    )
    navigation_params = PathJoinSubstitution(
        [
            FindPackageShare("motivon_navigation"),
            "config",
            "navigation_params.yaml",
        ]
    )
    route_file = PathJoinSubstitution(
        [FindPackageShare("motivon_navigation"), "config", "routes.yaml"]
    )
    obstacle_params = PathJoinSubstitution(
        [FindPackageShare("motivon_obstacles"), "config", "obstacle_params.yaml"]
    )
    gate_params = PathJoinSubstitution(
        [FindPackageShare("motivon_control"), "config", "cmd_vel_gate.yaml"]
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
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(base_launch),
                launch_arguments={
                    "udp_port": udp_port,
                    "start_agent": start_agent,
                }.items(),
            ),
            Node(
                package="motivon_obstacles",
                executable="ultrasonic_node",
                name="ultrasonic_node",
                output="screen",
                parameters=[obstacle_params],
                respawn=True,
                respawn_delay=2.0,
            ),
            Node(
                package="motivon_obstacles",
                executable="obstacle_manager_node",
                name="obstacle_manager_node",
                output="screen",
                parameters=[obstacle_params],
                respawn=True,
                respawn_delay=2.0,
            ),
            Node(
                package="motivon_control",
                executable="cmd_vel_gate_node",
                name="cmd_vel_gate_node",
                output="screen",
                parameters=[gate_params],
                respawn=True,
                respawn_delay=2.0,
            ),
            Node(
                package="motivon_navigation",
                executable="navigation_node",
                name="navigation_node",
                output="screen",
                parameters=[
                    navigation_params,
                    {
                        "route_file": route_file,
                        "command_topic": "/navigation/cmd_vel_raw",
                    },
                ],
            ),
        ]
    )
