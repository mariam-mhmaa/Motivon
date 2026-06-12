#!/bin/bash
dpkg -l | grep -E 'ros-jazzy-(controller-interface|hardware-interface|velocity-controllers|position-controllers|forward-command|joint-state-broad|controller-manager|gz-ros2-control)' | awk '{print $2, $3}'
