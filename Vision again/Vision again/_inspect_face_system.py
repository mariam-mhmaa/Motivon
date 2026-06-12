import importlib.util
from pathlib import Path

base = Path.cwd()
spec = importlib.util.spec_from_file_location('rtc', base / '06_real_time_camera.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

system = module.FaceRecognitionSystem()

print('class_min_confidence:', getattr(system, 'class_min_confidence', None))

prototypes = getattr(system, 'class_prototypes', {}) or {}
thresholds = getattr(system, 'class_distance_thresholds', {}) or {}

print('prototype_keys:', sorted(prototypes.keys()))
print('threshold_keys:', sorted(thresholds.keys()))

print('thresholds_per_class:')
for cls in sorted(thresholds.keys()):
    print(f'  {cls}: {thresholds[cls]}')

train_dir = base / 'data_split' / 'train'
print('train_counts_per_class:')
if train_dir.exists():
    for class_dir in sorted([p for p in train_dir.iterdir() if p.is_dir()]):
        count = sum(1 for f in class_dir.rglob('*') if f.is_file())
        print(f'  {class_dir.name}: {count}')
else:
    print('  <missing train dir>')
