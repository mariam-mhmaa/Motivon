#!/usr/bin/env python3
"""Generate the mecanum test script."""
import os

path = "/home/zeinazz/design_ws/test_mecanum.py"
code = r'''#!/usr/bin/env python3
import subprocess, time, re, sys, math, os, signal

EP = 'source /opt/ros/jazzy/setup.bash && source ~/design_ws/install/setup.bash && '

def ros2(cmd, timeout=15):
    r = subprocess.run(['bash', '-c', EP + cmd], capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()

def get_odom():
    try:
        out = ros2('ros2 topic echo /odom --once --no-daemon 2>/dev/null', timeout=15)
    except subprocess.TimeoutExpired:
        return None, None, None
    x = y = 0.0
    m = re.search(r'position:\s*\n\s*x:\s*([-\d.e+]+)\s*\n\s*y:\s*([-\d.e+]+)', out)
    if m:
        x, y = float(m.group(1)), float(m.group(2))
    oz = ow = 0.0
    m2 = re.search(r'orientation:\s*\n\s*x:\s*[-\d.e+]+\s*\n\s*y:\s*[-\d.e+]+\s*\n\s*z:\s*([-\d.e+]+)\s*\n\s*w:\s*([-\d.e+]+)', out)
    if m2:
        oz, ow = float(m2.group(1)), float(m2.group(2))
    yaw = 2.0 * math.atan2(oz, ow)
    return x, y, yaw

def send_vel(vx, vy, wz, dur=2.0):
    msg = '{linear: {x: %s, y: %s, z: 0.0}, angular: {x: 0.0, y: 0.0, z: %s}}' % (vx, vy, wz)
    cmd = "ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \"%s\" --rate 20 --no-daemon 2>/dev/null" % msg
    proc = subprocess.Popen(['bash', '-c', EP + cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
    time.sleep(dur)
    try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError: pass
    try: proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except: pass
        proc.wait()

def stop():
    try: send_vel(0,0,0, dur=0.5)
    except: pass

tests = [
    ('Forward',       0.3,  0.0,  0.0),
    ('Backward',     -0.3,  0.0,  0.0),
    ('Strafe Left',   0.0,  0.3,  0.0),
    ('Strafe Right',  0.0, -0.3,  0.0),
    ('Diagonal FL',   0.3,  0.3,  0.0),
    ('Diagonal FR',   0.3, -0.3,  0.0),
    ('Diagonal BL',  -0.3,  0.3,  0.0),
    ('Diagonal BR',  -0.3, -0.3,  0.0),
    ('Rotate CCW',    0.0,  0.0,  0.5),
    ('Rotate CW',     0.0,  0.0, -0.5),
]

print('=' * 70)
print('MECANUM WHEEL MOVEMENT TEST')
print('=' * 70)
try:
    nodes = ros2('ros2 node list --no-daemon 2>/dev/null', timeout=15)
except:
    nodes = ''
if 'mecanum_drive_node' not in nodes:
    print('[ERROR] mecanum_drive_node not found!'); sys.exit(1)
print('[OK] mecanum_drive_node is running')
print()

results = []
for name, vx, vy, wz in tests:
    print(f'--- {name} (vx={vx}, vy={vy}, wz={wz}) ---', flush=True)
    stop(); time.sleep(0.5)
    x0, y0, yaw0 = get_odom()
    if x0 is None:
        print('  [SKIP]', flush=True); results.append((name,'SKIP',0,0,0)); continue
    send_vel(vx, vy, wz, dur=2.5); time.sleep(0.3)
    x1, y1, yaw1 = get_odom()
    if x1 is None:
        print('  [SKIP]', flush=True); results.append((name,'SKIP',0,0,0)); continue
    dx, dy, dyaw = x1-x0, y1-y0, yaw1-yaw0
    while dyaw > math.pi: dyaw -= 2*math.pi
    while dyaw < -math.pi: dyaw += 2*math.pi
    T = 0.02
    p = False
    if name=='Forward': p=dx>T
    elif name=='Backward': p=dx<-T
    elif name=='Strafe Left': p=dy>T
    elif name=='Strafe Right': p=dy<-T
    elif name=='Diagonal FL': p=dx>T and dy>T
    elif name=='Diagonal FR': p=dx>T and dy<-T
    elif name=='Diagonal BL': p=dx<-T and dy>T
    elif name=='Diagonal BR': p=dx<-T and dy<-T
    elif name=='Rotate CCW': p=dyaw>T
    elif name=='Rotate CW': p=dyaw<-T
    s = 'PASS' if p else 'FAIL'
    results.append((name, s, dx, dy, dyaw))
    print(f'  dx={dx:+.4f}  dy={dy:+.4f}  dyaw={dyaw:+.4f}  [{s}]', flush=True)
    stop(); time.sleep(1.0)

print()
print('=' * 70)
print('SUMMARY')
print('=' * 70)
print(f"{'Test':<20} {'Status':<8} {'dx':>8} {'dy':>8} {'dyaw':>8}")
print('-' * 56)
for n, s, dx, dy, dyaw in results:
    print(f'{n:<20} {s:<8} {dx:>+8.4f} {dy:>+8.4f} {dyaw:>+8.4f}')
print('-' * 56)
pc = sum(1 for _,s,*_ in results if s=='PASS')
fc = sum(1 for _,s,*_ in results if s=='FAIL')
print(f'PASSED: {pc}/{len(results)}  FAILED: {fc}')
'''

with open(path, 'w') as f:
    f.write(code)
print('[OK] test_mecanum.py created')
