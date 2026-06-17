from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    udp_port = LaunchConfiguration("udp_port")
    start_agent = LaunchConfiguration("start_agent")
    start_gpio_nodes = LaunchConfiguration("start_gpio_nodes")
    start_led_node = LaunchConfiguration("start_led_node")
    show_vision_preview = LaunchConfiguration("show_vision_preview")
    publish_vision_debug_image = LaunchConfiguration("publish_vision_debug_image")

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
    vision_params = PathJoinSubstitution(
        [FindPackageShare("motivon_vision"), "config", "vision_params.yaml"]
    )
    bridge_params = PathJoinSubstitution(
        [FindPackageShare("motivon_gui_bridge"), "config", "gui_bridge_params.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("udp_port", default_value="8888"),
            DeclareLaunchArgument("start_agent", default_value="true"),
            DeclareLaunchArgument(
                "start_gpio_nodes",
                default_value="true",
                description=(
                    "Start Raspberry Pi GPIO nodes for lid and ultrasonic sensors."
                ),
            ),
            DeclareLaunchArgument(
                "start_led_node",
                default_value="true",
                description="Start the Raspberry Pi SPI LED strip node.",
            ),
            DeclareLaunchArgument(
                "show_vision_preview",
                default_value="false",
                description="Open an OpenCV preview window from the vision node.",
            ),
            DeclareLaunchArgument(
                "publish_vision_debug_image",
                default_value="false",
                description="Publish old-style vision overlay frames for GUI preview.",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(base_launch),
                launch_arguments={
                    "udp_port": udp_port,
                    "start_agent": start_agent,
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
                condition=IfCondition(start_gpio_nodes),
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
                condition=IfCondition(start_gpio_nodes),
            ),
            Node(
                package="motivon_led",
                executable="led_strip_node",
                name="led_strip_node",
                output="screen",
                parameters=[led_params],
                respawn=True,
                respawn_delay=2.0,
                condition=IfCondition(start_led_node),
            ),
            Node(
                package="motivon_vision",
                executable="vision_node",
                name="vision_node",
                output="screen",
                parameters=[
                    vision_params,
                    {
                        "show_preview": ParameterValue(
                            show_vision_preview,
                            value_type=bool,
                        ),
                        "publish_debug_image": ParameterValue(
                            publish_vision_debug_image,
                            value_type=bool,
                        ),
                    },
                ],
                respawn=True,
                respawn_delay=2.0,
            ),
            Node(
                package="motivon_mission",
                executable="mission_manager_node",
                name="mission_manager_node",
                output="screen",
                parameters=[mission_params],
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
