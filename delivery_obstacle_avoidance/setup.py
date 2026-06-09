from glob import glob
from setuptools import find_packages, setup

package_name = "delivery_obstacle_avoidance"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Delivery Robot Team",
    maintainer_email="student@example.com",
    description="ROS2 obstacle detection and avoidance nodes for the delivery robot.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "ultrasonic_scan_node = delivery_obstacle_avoidance.ultrasonic_scan_node:main",
            "obstacle_decision_node = delivery_obstacle_avoidance.obstacle_decision_node:main",
            "esp_http_bridge_node = delivery_obstacle_avoidance.esp_http_bridge_node:main",
            "front_servo_calibration_node = delivery_obstacle_avoidance.front_servo_calibration_node:main",
        ],
    },
)
