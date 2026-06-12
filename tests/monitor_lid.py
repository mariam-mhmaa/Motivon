#!/usr/bin/env python3
import rclpy, time
from sensor_msgs.msg import JointState

rclpy.init()
node = rclpy.create_node("lid_monitor")
positions = []

def cb(msg):
    idx = msg.name.index("Lid_Joint")
    positions.append((msg.header.stamp.sec + msg.header.stamp.nanosec*1e-9, msg.position[idx], msg.velocity[idx]))

sub = node.create_subscription(JointState, "/joint_states", cb, 10)
t0 = time.time()
while time.time() - t0 < 10:
    rclpy.spin_once(node, timeout_sec=0.5)

node.destroy_node()
rclpy.shutdown()

for t,p,v in positions[::max(1,len(positions)//10)]:
    print(f"t={t:.1f} pos={p:.6f} vel={v:.8f}")
print(f"Total samples: {len(positions)}")
if positions:
    print(f"First pos: {positions[0][1]:.6f}, Last pos: {positions[-1][1]:.6f}, Delta: {positions[-1][1]-positions[0][1]:.8f}")
