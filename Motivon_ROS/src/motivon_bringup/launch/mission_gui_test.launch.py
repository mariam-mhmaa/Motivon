from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    mission_launch = PathJoinSubstitution(
        [FindPackageShare("motivon_bringup"), "launch", "mission_system.launch.py"]
    )

    return LaunchDescription(
        [
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(mission_launch),
                launch_arguments={
                    "start_agent": "false",
                    "start_gpio_nodes": "false",
                    "start_led_node": "false",
                    "show_vision_preview": "false",
                    "publish_vision_debug_image": "true",
                }.items(),
            )
        ]
    )
