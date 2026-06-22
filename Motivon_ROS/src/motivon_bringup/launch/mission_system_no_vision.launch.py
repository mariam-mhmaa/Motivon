from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    udp_port = LaunchConfiguration("udp_port")
    start_agent = LaunchConfiguration("start_agent")
    hardware_reset_enabled = LaunchConfiguration("hardware_reset_enabled")
    hardware_reset_gpio_bcm = LaunchConfiguration("hardware_reset_gpio_bcm")

    base_launch = PathJoinSubstitution(
        [FindPackageShare("motivon_bringup"), "launch", "base_system.launch.py"]
    )
    navigation_params = PathJoinSubstitution(
        [FindPackageShare("motivon_navigation"), "config", "navigation_params.yaml"]
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
    lid_params = PathJoinSubstitution(
        [FindPackageShare("motivon_lid"), "config", "lid_params.yaml"]
    )
    led_params = PathJoinSubstitution(
        [FindPackageShare("motivon_led"), "config", "led_params.yaml"]
    )
    mission_params = PathJoinSubstitution(
        [FindPackageShare("motivon_mission"), "config", "mission_params.yaml"]
    )
    bridge_params = PathJoinSubstitution(
        [FindPackageShare("motivon_gui_bridge"), "config", "gui_bridge_params.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("udp_port", default_value="8888"),
            DeclareLaunchArgument("start_agent", default_value="true"),
            DeclareLaunchArgument("hardware_reset_enabled", default_value="true"),
            DeclareLaunchArgument("hardware_reset_gpio_bcm", default_value="26"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(base_launch),
                launch_arguments={
                    "udp_port": udp_port,
                    "start_agent": start_agent,
                    "hardware_reset_enabled": hardware_reset_enabled,
                    "hardware_reset_gpio_bcm": hardware_reset_gpio_bcm,
                }.items(),
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
                respawn=True,
                respawn_delay=2.0,
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
                executable="mode_manager_node",
                name="mode_manager_node",
                output="screen",
                parameters=[gate_params],
                respawn=True,
                respawn_delay=2.0,
            ),
            Node(
                package="motivon_control",
                executable="manual_control_node",
                name="manual_control_node",
                output="screen",
                parameters=[gate_params],
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
                package="motivon_lid",
                executable="lid_control_node",
                name="lid_control_node",
                output="screen",
                parameters=[lid_params],
                respawn=True,
                respawn_delay=2.0,
            ),
            Node(
                package="motivon_led",
                executable="led_strip_node",
                name="led_strip_node",
                output="screen",
                parameters=[led_params],
                respawn=True,
                respawn_delay=2.0,
            ),
            Node(
                package="motivon_mission",
                executable="mission_manager_node",
                name="mission_manager_node",
                output="screen",
                parameters=[mission_params, {"use_vision": False}],
                respawn=True,
                respawn_delay=2.0,
            ),
            Node(
                package="motivon_gui_bridge",
                executable="gui_bridge_node",
                name="gui_bridge_node",
                output="screen",
                parameters=[bridge_params],
                respawn=True,
                respawn_delay=2.0,
            ),
        ]
    )
