"""Helpers for starting the local demo ROS stack from the Windows GUI."""

import base64
import os
from pathlib import Path
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
MOTIVON_ROS_DIR = REPO_ROOT / "Motivon_ROS"
DEFAULT_PI_SSH = os.environ.get("MOTIVON_PI_SSH", "mohamed@172.20.10.10")
DEFAULT_BRIDGE_URL = os.environ.get("MOTIVON_BRIDGE_URL", "http://172.20.10.10:8000")
VISION_PREVIEW_SCRIPT = Path(__file__).resolve().parent / "vision_preview_client.py"


def _creation_flags():
    return getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


def _windows_path_to_wsl(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive:
        return resolved.as_posix()
    rest = resolved.relative_to(resolved.anchor).as_posix()
    return f"/mnt/{drive}/{rest}"


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _remote_bash_command(script: str) -> str:
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    return f"printf %s {encoded} | base64 -d | bash"


def start_laptop_ros_stack():
    """Start the WSL laptop test launch in its own console window."""
    ros_dir = _windows_path_to_wsl(MOTIVON_ROS_DIR)
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        f"cd '{ros_dir}' && "
        "source install/setup.bash && "
        "ros2 launch motivon_bringup mission_gui_test.launch.py"
    )
    return subprocess.Popen(
        ["wsl.exe", "-e", "bash", "-lc", command],
        cwd=str(REPO_ROOT),
        creationflags=_creation_flags(),
    )


def start_pi_camera_stream(pi_ssh: str = DEFAULT_PI_SSH):
    """Start the Raspberry Pi camera stream over SSH in its own console window."""
    ssh_exe = shutil.which("ssh")
    if not ssh_exe:
        raise RuntimeError("ssh.exe was not found on PATH.")

    remote_script = "\n".join(
        [
            "set -e",
            "echo 'Motivon camera stream starting on TCP 8890'",
            "echo 'Pi IP:'",
            "hostname -I",
            "pkill -f '[c]amera.py' || true",
            "pkill -x rpicam-vid || true",
            "pkill -x libcamera-vid || true",
            "pkill -x ffmpeg || true",
            "echo 'Starting rpicam-vid -> ffmpeg stream. Leave this window open.'",
            "rpicam-vid -t 0 -n --width 1280 --height 720 --framerate 8 "
            "--codec mjpeg --quality 95 -o - | "
            "ffmpeg -hide_banner -loglevel info -fflags nobuffer -flags low_delay "
            "-f mjpeg -i pipe:0 -c:v copy -flush_packets 1 -f mjpeg "
            "'tcp://0.0.0.0:8890?listen=1&tcp_nodelay=1'",
        ]
    )
    remote_command = _remote_bash_command(remote_script)
    powershell_command = (
        "Write-Host 'Starting Pi camera over SSH. "
        "Enter the Pi password if prompted.'; "
        f"& {_ps_quote(ssh_exe)} {_ps_quote(pi_ssh)} {_ps_quote(remote_command)}; "
        "Write-Host 'Pi camera command ended.'"
    )
    return subprocess.Popen(
        [
            "powershell.exe",
            "-NoExit",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            powershell_command,
        ],
        cwd=str(REPO_ROOT),
        creationflags=_creation_flags(),
    )


def start_windows_vision_preview():
    """Start the Windows OpenCV preview fed by the ROS GUI bridge."""
    env = os.environ.copy()
    env.setdefault("MOTIVON_BRIDGE_URL", DEFAULT_BRIDGE_URL)
    return subprocess.Popen(
        [sys.executable, str(VISION_PREVIEW_SCRIPT)],
        cwd=str(VISION_PREVIEW_SCRIPT.parent),
        env=env,
        creationflags=_creation_flags(),
    )
