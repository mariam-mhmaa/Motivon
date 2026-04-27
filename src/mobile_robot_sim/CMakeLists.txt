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
    scripts/obstacle_avoidance.py
    scripts/mecanum_drive_node.py
    scripts/goal_sender_node.py
    scripts/lid_control_node.py
    scripts/start_stop_node.py
    scripts/test_cmd_vel.py
    scripts/test_lid.py
    scripts/test_obstacle.py
    scripts/test_movements.py
    scripts/robot_navigator_node.py
    scripts/dynamic_obstacle_node.py
    scripts/arena_navigator_node.py
  DESTINATION lib/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()