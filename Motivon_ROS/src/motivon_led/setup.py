from glob import glob
import os

from setuptools import find_packages, setup


package_name = "motivon_led"


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
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Motivon Team",
    maintainer_email="student@example.com",
    description="Mission-state LED strip feedback for the Motivon robot.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "led_strip_node = motivon_led.led_strip_node:main",
        ],
    },
)
