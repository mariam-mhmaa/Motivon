import pygame
import time

DEADZONE = 0.12

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("No controller detected.")
    raise SystemExit

joy = pygame.joystick.Joystick(0)
joy.init()

def dz(v):
    return 0.0 if abs(v) < DEADZONE else v

def normalize(fl, fr, rl, rr):
    m = max(abs(fl), abs(fr), abs(rl), abs(rr), 1.0)
    return fl / m, fr / m, rl / m, rr / m

print("PS controller mecanum test")
print("Left stick = vx/vy")
print("Right stick X = rotation")
print("Press Ctrl+C to stop\n")

try:
    while True:
        pygame.event.pump()

        axis0 = joy.get_axis(0)  # left stick left/right
        axis1 = joy.get_axis(1)  # left stick forward/back
        axis2 = joy.get_axis(2)  # right stick left/right

        vx = dz(-axis1)   # + forward
        vy = dz(-axis0)   # + left
        w  = dz(-axis2)   # rotation

        fl = vx - vy - w
        fr = vx + vy + w
        rl = vx + vy - w
        rr = vx - vy + w

        fl, fr, rl, rr = normalize(fl, fr, rl, rr)

        print(
            f"vx:{vx: .2f} vy:{vy: .2f} w:{w: .2f} | "
            f"FL:{fl: .2f} FR:{fr: .2f} RL:{rl: .2f} RR:{rr: .2f}"
        )

        time.sleep(0.1)

except KeyboardInterrupt:
    pygame.quit()
    print("\nStopped.")