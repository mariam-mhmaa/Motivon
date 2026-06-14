#!/usr/bin/env python3
"""
Apply dark-purple color scheme to Gazebo world models.
  Floor   #10091D -> 0.063 0.035 0.114
  Walls   #28193D -> 0.157 0.098 0.239
  Boxes/Shelves #46315C -> 0.275 0.192 0.361
"""
import re, os

MODELS = os.path.expanduser(
    '~/design_ws/src/mobile_robot_sim/worldd/gazebo_models_worlds_collection/models')
WORLD = os.path.expanduser(
    '~/design_ws/src/mobile_robot_sim/world/my_world.sdf')

FLOOR = '0.063 0.035 0.114'
WALL  = '0.157 0.098 0.239'
BOX   = '0.275 0.192 0.361'

# ── helper ──────────────────────────────────────────────────────────────────
def read(path):
    with open(path) as f:
        return f.read()

def write(path, text):
    with open(path, 'w') as f:
        f.write(text)
    print('  Saved:', path)

# ── 1. rubberFloor.material  (floor texture -> solid colour) ─────────────
rubber_path = os.path.join(MODELS, 'Workshop/materials/scripts/rubberFloor.material')
write(rubber_path, '''\
material rubber
{
  technique
  {
    pass
    {
      ambient %s 1.0
      diffuse %s 1.0
      specular 0.05 0.05 0.05 1.0
    }
  }
}
''' % (FLOOR, FLOOR))

# ── 2. Workshop/model.sdf ────────────────────────────────────────────────
wsh_path = os.path.join(MODELS, 'Workshop/model.sdf')
wsh = read(wsh_path)

# 2a. Walls  (Gazebo/Grey + <ambient>0 0 0 1</ambient>)
wall_re = re.compile(
    r'(?m)        <material>\s*\n'
    r'          <script>\s*\n'
    r'            <uri>file://media/materials/scripts/gazebo\.material</uri>\s*\n'
    r'            <name>Gazebo/Grey</name>\s*\n'
    r'          </script>\s*\n'
    r'          <ambient>0 0 0 1</ambient>\s*\n'
    r'        </material>'
)
wall_new = (
    '        <material>\n'
    '          <ambient>%s 1</ambient>\n'
    '          <diffuse>%s 1</diffuse>\n'
    '          <specular>0.1 0.1 0.1 1</specular>\n'
    '        </material>' % (WALL, WALL)
)
wsh, n = wall_re.subn(wall_new, wsh)
print('Workshop walls replaced:', n)

# 2b. Floor  (rubber script block)
floor_re = re.compile(
    r'(?s)\s*<material>\s*\n'
    r'          <script>\s*\n'
    r'            <uri>model://Workshop/materials/scripts</uri>\s*\n'
    r'            <uri>model://Workshop/materials/textures</uri>\s*\n'
    r'            <name>rubber</name>\s*\n'
    r'          </script>\s*\n'
    r'        </material>'
)
floor_new = (
    '\n           <material>\n'
    '          <ambient>%s 1</ambient>\n'
    '          <diffuse>%s 1</diffuse>\n'
    '          <specular>0.05 0.05 0.05 1</specular>\n'
    '        </material>' % (FLOOR, FLOOR)
)
wsh, n = floor_re.subn(floor_new, wsh)
print('Workshop floor replaced:', n)
write(wsh_path, wsh)

# ── 3. Box / Cabinet / Storage models  (Gazebo/Grey + any ambient) ───────
box_re = re.compile(
    r'(?m)        <material>\s*\n'
    r'          <script>\s*\n'
    r'            <uri>file://media/materials/scripts/gazebo\.material</uri>\s*[^\n]*\n'
    r'            <name>Gazebo/Grey</name>\s*\n'
    r'          </script>\s*\n'
    r'          <ambient>[^<]+</ambient>\s*\n'
    r'        </material>'
)
box_new = (
    '        <material>\n'
    '          <ambient>%s 1</ambient>\n'
    '          <diffuse>%s 1</diffuse>\n'
    '          <specular>0.1 0.1 0.1 1</specular>\n'
    '        </material>' % (BOX, BOX)
)

for model in ['Box_15x30', 'Box_24x15M', 'Box_24x15W',
              'Box_33x15', 'Box_36x15W',
              'Wall_Cabinet_Coin_24x30W', '6_Cube_StorageE']:
    path = os.path.join(MODELS, model, 'model.sdf')
    content = read(path)
    new_content, n = box_re.subn(box_new, content)
    if n == 0:
        print('  WARNING: no match in', model)
    else:
        write(path, new_content)
        print(' ', model, '->', n, 'block(s) replaced')

# ── 4. Wire_Shelf: insert material into each mesh visual ─────────────────
wire_path = os.path.join(MODELS, 'Wire_Shelf/model.sdf')
wire = read(wire_path)

# Each visual ends with:  \t  </geometry>\n\t</visual>
# Insert <material> before </visual>
wire_mat = (
    '\t    <ambient>%s 1</ambient>\n'
    '\t    <diffuse>%s 1</diffuse>\n'
    '\t    <specular>0.1 0.1 0.1 1</specular>\n'
    '\t  </material>' % (BOX, BOX)
)
old_end = '\t  </geometry>\n\t</visual>'
new_end = (
    '\t  </geometry>\n'
    '\t  <material>\n' +
    wire_mat + '\n'
    '\t</visual>'
)
count_wire = wire.count(old_end)
wire = wire.replace(old_end, new_end)
write(wire_path, wire)
print('Wire_Shelf visuals updated:', count_wire)

# ── 5. my_world.sdf ground plane ─────────────────────────────────────────
world = read(WORLD)
old_gp = (
    '          <material>\n'
    '            <ambient>0.8 0.8 0.8 1</ambient>\n'
    '            <diffuse>0.8 0.8 0.8 1</diffuse>\n'
    '          </material>'
)
new_gp = (
    '          <material>\n'
    '            <ambient>%s 1</ambient>\n'
    '            <diffuse>%s 1</diffuse>\n'
    '          </material>' % (FLOOR, FLOOR)
)
if old_gp in world:
    world = world.replace(old_gp, new_gp)
    write(WORLD, world)
    print('Ground plane updated in my_world.sdf')
else:
    print('WARNING: ground plane material not found')

print('\nAll color changes applied.')
