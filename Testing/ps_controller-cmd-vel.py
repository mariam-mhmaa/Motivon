import pygame
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

DEADZONE = 0.12

MAX_VX = 0.3   # forward speed scale
MAX_VY = 0.3   # strafe speed scale
MAX_W  = 0.8   # rotation speed scale


def dz(v):
    return 0.0 if abs(v) < DEADZONE else v


class PSControllerNode(Node):
    def __init__(self):
        super().__init__("ps_controller_cmd_vel")
        self.pub = self.create_publisher(Twist, "/cmd_vel", 10)

        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            self.get_logger().error("No controller detected.")
            raise SystemExit

        self.joy = pygame.joystick.Joystick(0)
        self.joy.init()

        self.get_logger().info(f"Controller: {self.joy.get_name()}")
        self.timer = self.create_timer(0.05, self.loop)  # 20 Hz

    def loop(self):
        pygame.event.pump()

        axis0 = self.joy.get_axis(0)  # left stick left/right
        axis1 = self.joy.get_axis(1)  # left stick forward/back
        axis2 = self.joy.get_axis(2)  # right stick left/right

        vx = dz(-axis1) * MAX_VX
        vy = dz(-axis0) * MAX_VY
        w  = dz(-axis2) * MAX_W

        msg = Twist()
        msg.linear.x = vx
        msg.linear.y = vy
        msg.angular.z = w

        self.pub.publish(msg)

        print(f"vx={vx:.2f}  vy={vy:.2f}  w={w:.2f}")


def main():
    rclpy.init()
    node = PSControllerNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        stop = Twist()
        node.pub.publish(stop)
        pygame.quit()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()