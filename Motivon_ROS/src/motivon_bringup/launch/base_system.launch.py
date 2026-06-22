from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description():
    udp_port = LaunchConfiguration("udp_port")
    start_agent = LaunchConfiguration("start_agent")
    hardware_reset_enabled = LaunchConfiguration("hardware_reset_enabled")
    hardware_reset_gpio_bcm = LaunchConfiguration("hardware_reset_gpio_bcm")

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
            DeclareLaunchArgument(
                "hardware_reset_enabled",
                default_value="true",
                description="Allow /base/recover to pulse the ESP32 EN reset GPIO.",
            ),
            DeclareLaunchArgument(
                "hardware_reset_gpio_bcm",
                default_value="26",
                description="BCM GPIO wired to the ESP32 EN pin.",
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
            Node(
                package="motivon_base",
                executable="base_recovery_node",
                name="base_recovery_node",
                output="screen",
                parameters=[
                    {
                        "hardware_reset_enabled": ParameterValue(
                            hardware_reset_enabled,
                            value_type=bool,
                        ),
                        "hardware_reset_gpio_bcm": ParameterValue(
                            hardware_reset_gpio_bcm,
                            value_type=int,
                        ),
                        "agent_udp_port": ParameterValue(
                            udp_port,
                            value_type=int,
                        ),
                    }
                ],
                respawn=True,
                respawn_delay=2.0,
            ),
        ]
    )
