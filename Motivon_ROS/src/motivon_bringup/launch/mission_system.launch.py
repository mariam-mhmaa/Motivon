from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    OpaqueFunction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def _make_pi_camera_script(context):
    width = LaunchConfiguration("camera_width").perform(context)
    height = LaunchConfiguration("camera_height").perform(context)
    framerate = LaunchConfiguration("camera_framerate").perform(context)
    quality = LaunchConfiguration("camera_quality").perform(context)
    port = LaunchConfiguration("camera_port").perform(context)

    return "\n".join(
        [
            "set -e",
            f"echo 'Motivon camera stream starting on TCP {port}'",
            "echo 'Pi IP:'",
            "hostname -I",
            "pkill -x rpicam-vid || true",
            "pkill -x libcamera-vid || true",
            "pkill -x ffmpeg || true",
            "if command -v rpicam-vid >/dev/null 2>&1; then",
            "  CAMERA_CMD=rpicam-vid",
            "elif command -v libcamera-vid >/dev/null 2>&1; then",
            "  CAMERA_CMD=libcamera-vid",
            "else",
            "  echo 'ERROR: neither rpicam-vid nor libcamera-vid is installed.'",
            "  exit 1",
            "fi",
            "echo 'Starting rpicam-vid -> ffmpeg stream. Leave launch running.'",
            f"$CAMERA_CMD -t 0 -n --width {width} --height {height} "
            f"--framerate {framerate} --codec mjpeg --quality {quality} -o - | "
            "ffmpeg -hide_banner -loglevel info -fflags nobuffer -flags low_delay "
            "-f mjpeg -i pipe:0 -c:v copy -flush_packets 1 -f mjpeg "
            f"'tcp://0.0.0.0:{port}?listen=1&tcp_nodelay=1'",
        ]
    )


def _camera_stream_actions(context, *args, **kwargs):
    return [
        ExecuteProcess(
            cmd=["bash", "-lc", _make_pi_camera_script(context)],
            name="pi_camera_stream",
            output="screen",
            respawn=True,
            respawn_delay=2.0,
            condition=IfCondition(LaunchConfiguration("start_pi_camera_stream")),
        )
    ]


def generate_launch_description():
    udp_port = LaunchConfiguration("udp_port")
    start_agent = LaunchConfiguration("start_agent")
    hardware_reset_enabled = LaunchConfiguration("hardware_reset_enabled")
    hardware_reset_gpio_bcm = LaunchConfiguration("hardware_reset_gpio_bcm")
    start_gpio_nodes = LaunchConfiguration("start_gpio_nodes")
    start_led_node = LaunchConfiguration("start_led_node")
    camera_host = LaunchConfiguration("camera_host")
    camera_port = LaunchConfiguration("camera_port")
    camera_width = LaunchConfiguration("camera_width")
    camera_height = LaunchConfiguration("camera_height")
    camera_framerate = LaunchConfiguration("camera_framerate")
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
            DeclareLaunchArgument("hardware_reset_enabled", default_value="true"),
            DeclareLaunchArgument("hardware_reset_gpio_bcm", default_value="26"),
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
                "start_pi_camera_stream",
                default_value="true",
                description="Start the Raspberry Pi camera MJPEG TCP stream for vision.",
            ),
            DeclareLaunchArgument("camera_host", default_value="172.20.10.10"),
            DeclareLaunchArgument("camera_port", default_value="8890"),
            DeclareLaunchArgument("camera_width", default_value="640"),
            DeclareLaunchArgument("camera_height", default_value="480"),
            DeclareLaunchArgument("camera_framerate", default_value="8"),
            DeclareLaunchArgument("camera_quality", default_value="95"),
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
                    "hardware_reset_enabled": hardware_reset_enabled,
                    "hardware_reset_gpio_bcm": hardware_reset_gpio_bcm,
                }.items(),
            ),
            OpaqueFunction(function=_camera_stream_actions),
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
                        "camera_host": camera_host,
                        "camera_port": ParameterValue(camera_port, value_type=int),
                        "camera_width": ParameterValue(camera_width, value_type=int),
                        "camera_height": ParameterValue(camera_height, value_type=int),
                        "camera_framerate": ParameterValue(
                            camera_framerate,
                            value_type=int,
                        ),
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
