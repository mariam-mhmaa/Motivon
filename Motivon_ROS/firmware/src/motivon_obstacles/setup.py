from glob import glob
import os

from setuptools import find_packages, setup


package_name = "motivon_obstacles"


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
        (
            os.path.join("share", package_name, "config"),
            glob("config/*.yaml"),
        ),
        (
            os.path.join("share", package_name, "launch"),
            glob("launch/*.launch.py"),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Motivon Team",
    maintainer_email="student@example.com",
    description="Ultrasonic obstacle detection for the Motivon robot.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "ultrasonic_node = motivon_obstacles.ultrasonic_node:main",
            (
                "obstacle_manager_node = "
                "motivon_obstacles.obstacle_manager_node:main"
            ),
        ],
    },
)
