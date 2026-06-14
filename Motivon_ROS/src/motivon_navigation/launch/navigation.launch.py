from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description():
    command_topic = LaunchConfiguration("command_topic")
    params = PathJoinSubstitution(
        [FindPackageShare("motivon_navigation"), "config",
         "navigation_params.yaml"]
    )
    routes = PathJoinSubstitution(
        [FindPackageShare("motivon_navigation"), "config", "routes.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "command_topic",
                default_value="/navigation/cmd_vel_raw",
                description="Navigation velocity output topic.",
            ),
            Node(
                package="motivon_navigation",
                executable="navigation_node",
                name="navigation_node",
                output="screen",
                parameters=[
                    params,
                    {
                        "route_file": routes,
                        "command_topic": command_topic,
                    },
                ],
            ),
        ]
    )
