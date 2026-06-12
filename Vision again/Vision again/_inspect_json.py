import json
from pathlib import Path
p=Path(r"C:\Users\ainour\OneDrive - Faculty of Engineering Ain Shams University\Desktop\Vision again\real_time_camera_detections.json")
data=json.loads(p.read_text(encoding='utf-8'))
print(type(data).__name__)
if isinstance(data,dict):
    print('dict keys', list(data.keys())[:30])
    for k,v in data.items():
        if isinstance(v,list):
            print('list key',k,'len',len(v))
            if v:
                print('first element type',type(v[0]).__name__)
                print(v[0])
            break
elif isinstance(data,list):
    print('len',len(data))
    if data:
        print('first type',type(data[0]).__name__)
        print(data[0])
