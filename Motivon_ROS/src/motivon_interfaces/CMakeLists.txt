cmake_minimum_required(VERSION 3.8)
project(motivon_interfaces)

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/NavigateToTarget.action"
  "msg/MissionEvent.msg"
  "msg/MissionStatus.msg"
  "msg/NavigationStatus.msg"
  "msg/ObstacleScan.msg"
  "msg/ObstacleState.msg"
  "srv/StartMission.srv"
  DEPENDENCIES builtin_interfaces
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
