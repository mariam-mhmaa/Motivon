from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params = PathJoinSubstitution(
        [
            FindPackageShare("delivery_obstacle_avoidance"),
            "config",
            "obstacle_params.yaml",
        ]
    )

    return LaunchDescription(
        [
            Node(
                package="delivery_obstacle_avoidance",
                executable="esp_http_bridge_node",
                name="esp_http_bridge_node",
                output="screen",
                parameters=[params],
            ),
            Node(
                package="delivery_obstacle_avoidance",
                executable="ultrasonic_scan_node",
                name="ultrasonic_scan_node",
                output="screen",
                parameters=[params],
            ),
            Node(
                package="delivery_obstacle_avoidance",
                executable="obstacle_decision_node",
                name="obstacle_decision_node",
                output="screen",
                parameters=[params],
            ),
        ]
    )
