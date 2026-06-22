import base64
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def _infer_repo_root() -> str:
    launch_path = Path(__file__).resolve()
    launch_text = launch_path.as_posix()
    marker = "/Motivon_ROS/"
    marker_index = launch_text.find(marker)
    if marker_index >= 0:
        return launch_text[:marker_index]
    return str(launch_path.parents[4])


def _wsl_path_to_windows(path_text: str) -> str:
    path_text = path_text.strip()
    if path_text.startswith("/mnt/") and len(path_text) > 6:
        drive = path_text[5]
        rest = path_text[7:].replace("/", "\\")
        return f"{drive.upper()}:\\{rest}"
    return path_text.replace("/", "\\")


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _win_join(*parts: str) -> str:
    cleaned = [part.strip("\\/") for part in parts if part]
    if not cleaned:
        return ""
    first = cleaned[0]
    if len(first) == 2 and first[1] == ":":
        first += "\\"
    return first.rstrip("\\/") + "\\" + "\\".join(cleaned[1:])


def _remote_bash_command(script: str) -> str:
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    return f"printf %s {encoded} | base64 -d | bash"


def _camera_script(context):
    port = LaunchConfiguration("camera_port").perform(context)
    width = LaunchConfiguration("camera_width").perform(context)
    height = LaunchConfiguration("camera_height").perform(context)
    framerate = LaunchConfiguration("camera_framerate").perform(context)
    quality = LaunchConfiguration("camera_quality").perform(context)

    return "\n".join(
        [
            "set -e",
            f"echo 'Motivon camera stream starting on TCP {port}'",
            "echo 'Pi IP:'",
            "hostname -I",
            "pkill -f '[c]amera.py' || true",
            "pkill -x rpicam-vid || true",
            "pkill -x libcamera-vid || true",
            "pkill -x ffmpeg || true",
            "echo 'Starting rpicam-vid -> ffmpeg stream. Leave this terminal open.'",
            f"rpicam-vid -t 0 -n --width {width} --height {height} "
            f"--framerate {framerate} --codec mjpeg --quality {quality} -o - | "
            "ffmpeg -hide_banner -loglevel info -fflags nobuffer -flags low_delay "
            "-f mjpeg -i pipe:0 -c:v copy -flush_packets 1 -f mjpeg "
            f"'tcp://0.0.0.0:{port}?listen=1&tcp_nodelay=1'",
        ]
    )


def _runtime_actions(context, *args, **kwargs):
    repo_root = LaunchConfiguration("repo_root").perform(context).strip()
    if not repo_root:
        repo_root = _infer_repo_root()

    repo_root_windows = LaunchConfiguration("repo_root_windows").perform(context).strip()
    if not repo_root_windows:
        repo_root_windows = _wsl_path_to_windows(repo_root)

    windows_python = LaunchConfiguration("windows_python").perform(context).strip()
    if not windows_python:
        windows_python = _win_join(repo_root_windows, ".venv", "Scripts", "python.exe")

    preview_script = LaunchConfiguration("preview_script").perform(context).strip()
    if not preview_script:
        preview_script = _win_join(
            repo_root_windows,
            "GUI",
            "delivery_robot_gui (2)",
            "delivery_robot_gui",
            "vision_preview_client.py",
        )

    pi_ssh = LaunchConfiguration("pi_ssh").perform(context)
    ssh_remote_command = _remote_bash_command(_camera_script(context))
    camera_powershell_command = (
        "Write-Host 'Starting Pi camera stream over SSH. "
        "Enter the Pi password if prompted, then leave this window open.'; "
        f"& ssh.exe {_ps_quote(pi_ssh)} {_ps_quote(ssh_remote_command)}; "
        "Write-Host 'Pi camera command ended.'"
    )
    start_camera_command = (
        "Start-Process "
        "-FilePath 'powershell.exe' "
        "-ArgumentList @("
        "'-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', "
        f"{_ps_quote(camera_powershell_command)})"
    )
    start_preview_command = (
        "Start-Process "
        f"-FilePath {_ps_quote(windows_python)} "
        f"-ArgumentList @({_ps_quote(preview_script)})"
    )

    return [
        ExecuteProcess(
            cmd=[
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                start_camera_command,
            ],
            name="pi_camera_stream",
            output="screen",
            condition=IfCondition(LaunchConfiguration("start_pi_camera")),
        ),
        ExecuteProcess(
            cmd=[
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                start_preview_command,
            ],
            name="windows_vision_preview",
            output="screen",
            condition=IfCondition(LaunchConfiguration("start_windows_preview")),
        ),
    ]


def generate_launch_description():
    mission_launch = PathJoinSubstitution(
        [FindPackageShare("motivon_bringup"), "launch", "mission_system.launch.py"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("start_pi_camera", default_value="true"),
            DeclareLaunchArgument("start_windows_preview", default_value="true"),
            DeclareLaunchArgument("pi_ssh", default_value="mohamed@172.20.10.10"),
            DeclareLaunchArgument("camera_port", default_value="8890"),
            DeclareLaunchArgument("camera_width", default_value="640"),
            DeclareLaunchArgument("camera_height", default_value="480"),
            DeclareLaunchArgument("camera_framerate", default_value="8"),
            DeclareLaunchArgument("camera_quality", default_value="95"),
            DeclareLaunchArgument("repo_root", default_value=""),
            DeclareLaunchArgument("repo_root_windows", default_value=""),
            DeclareLaunchArgument("windows_python", default_value=""),
            DeclareLaunchArgument("preview_script", default_value=""),
            OpaqueFunction(function=_runtime_actions),
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
