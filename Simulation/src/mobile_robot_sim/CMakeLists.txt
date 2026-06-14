cmake_minimum_required(VERSION 3.8)
project(mobile_robot_sim)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)

# Install directories (URDF, Meshes, Launch, RViz, Config, World, Scripts)
install(
  DIRECTORY urdf meshes launch config world scripts
  DESTINATION share/${PROJECT_NAME}
)

# Install Python Executables
install(
  PROGRAMS
    scripts/mecanum_drive_node.py
    scripts/navigation_routes.py
    scripts/navigation_test_runner.py
    scripts/navigation_test_matrix.py
    scripts/goal_sender_node.py
    scripts/lid_control_node.py
    scripts/start_stop_node.py
    scripts/dynamic_obstacle_node.py
    scripts/arena_navigator_node.py
    scripts/encoder_odometry_node.py
    scripts/imu_node.py
    scripts/ultrasonic_node.py
    scripts/pid_interface_node.py
    scripts/state_led_node.py
    scripts/vision_auth_node.py
    scripts/test_wp1_return.py
    scripts/test_wp2_return.py
    scripts/test_wp3_return.py
    scripts/test_wp1_to_wp2.py
    scripts/test_wp1_to_wp3.py
    scripts/test_wp2_to_wp3.py
    scripts/test_all_wp.py
  DESTINATION lib/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
