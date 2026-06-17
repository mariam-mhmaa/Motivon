import importlib.util
from pathlib import Path

from launch import LaunchDescription
import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def load_yaml(filename):
    path = PACKAGE_ROOT / "config" / filename
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def test_launch_description_constructs_all_base_actions():
    launch_path = PACKAGE_ROOT / "launch" / "base_system.launch.py"
    spec = importlib.util.spec_from_file_location(
        "base_system_launch", launch_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    description = module.generate_launch_description()

    assert isinstance(description, LaunchDescription)
    assert len(description.entities) == 6


def test_base_parameters_match_pid_geometry():
    document = load_yaml("base_params.yaml")
    parameters = document["wheel_odometry_node"]["ros__parameters"]

    assert parameters["wheel_radius_m"] == 0.0485
    assert parameters["half_wheelbase_m"] == 0.1975
    assert parameters["half_track_width_m"] == 0.22725
    assert parameters["odom_x_scale"] == 1.0
    assert parameters["odom_y_scale"] == 0.948
    assert parameters["maximum_sample_period_s"] == 0.25
    assert parameters["stale_timeout_s"] == 0.50
    assert parameters["maximum_wheel_speed_rad_s"] == 20.0


def test_ekf_uses_wheel_translation_and_imu_only_for_yaw_rate():
    document = load_yaml("ekf.yaml")
    parameters = document["ekf_filter_node"]["ros__parameters"]

    assert parameters["world_frame"] == "odom"
    assert parameters["odom0"] == "/wheel/odometry"
    assert parameters["imu0"] == "/imu/data_raw"
    assert len(parameters["odom0_config"]) == 15
    assert len(parameters["imu0_config"]) == 15

    assert [
        index
        for index, enabled in enumerate(parameters["odom0_config"])
        if enabled
    ] == [6, 7]
    assert [
        index
        for index, enabled in enumerate(parameters["imu0_config"])
        if enabled
    ] == [11]
