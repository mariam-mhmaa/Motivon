from glob import glob
import os

from setuptools import find_packages, setup


package_name = "motivon_gui_bridge"


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
    ],
    install_requires=["setuptools", "fastapi", "uvicorn"],
    zip_safe=True,
    maintainer="Motivon Team",
    maintainer_email="student@example.com",
    description="HTTP and WebSocket bridge between the Windows GUI and ROS.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "gui_bridge_node = motivon_gui_bridge.gui_bridge_node:main",
        ],
    },
)
