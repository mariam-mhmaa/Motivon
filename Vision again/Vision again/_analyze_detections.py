import json, statistics
from collections import Counter, defaultdict
from pathlib import Path

p=Path(r"C:\Users\ainour\OneDrive - Faculty of Engineering Ain Shams University\Desktop\Vision again\real_time_camera_detections.json")
data=json.loads(p.read_text(encoding='utf-8'))

threshold = data.get('confidence_threshold') if isinstance(data,dict) else None
frames = data.get('detections',[]) if isinstance(data,dict) else data

records=[]
for frame in frames:
    dets = frame.get('detections',[]) if isinstance(frame,dict) else []
    for det in dets:
        cls = det.get('classification_result',{}) if isinstance(det,dict) else {}
        label = det.get('person_name') or cls.get('predicted_class') or 'UNKNOWN_FIELD'
        conf = det.get('confidence_score')
        if conf is None:
            conf = cls.get('confidence')
        try:
            conf = float(conf) if conf is not None else None
        except Exception:
            conf = None
        ts = None
        if isinstance(frame,dict):
            ts = (frame.get('header') or {}).get('timestamp') or frame.get('timestamp')
        records.append({'label':str(label), 'conf':conf, 'timestamp':ts})

n=len(records)
labels=[r['label'] for r in records]
cnt=Counter(labels)

unknown_count = sum(v for k,v in cnt.items() if str(k).strip().lower()=='unknown')
if unknown_count==0:
    unknown_count = sum(v for k,v in cnt.items() if 'unknown' in str(k).lower())

confs=[r['conf'] for r in records if r['conf'] is not None]

def s(vals):
    if not vals:
        return None
    return (sum(vals)/len(vals), statistics.median(vals), min(vals), max(vals), len(vals))

overall=s(confs)
per=defaultdict(list)
for r in records:
    if r['conf'] is not None:
        per[r['label']].append(r['conf'])

# top 10 non-Nour
non_nour=[r for r in records if r['conf'] is not None and r['label'].strip().lower()!='nour']
non_nour=sorted(non_nour, key=lambda x:x['conf'], reverse=True)

# high vs low mislabels relative to threshold
pivot=threshold
high=low=0
if pivot is not None:
    for r in non_nour:
        if r['conf']>=pivot: high+=1
        else: low+=1

print(f"TOTAL_DETECTIONS={n}")
print(f"THRESHOLD={threshold}")
print("LABEL_COUNTS_PERCENT=")
for lbl,c in sorted(cnt.items(), key=lambda kv:(-kv[1], kv[0])):
    print(f"  {lbl}: {c} ({(c/n*100 if n else 0):.2f}%)")
print(f"UNKNOWN_RATE={unknown_count}/{n} ({(unknown_count/n*100 if n else 0):.2f}%)")
if overall:
    print(f"OVERALL_CONF: avg={overall[0]:.4f} median={overall[1]:.4f} min={overall[2]:.4f} max={overall[3]:.4f} n={overall[4]}")
print("PER_LABEL_CONF=")
for lbl, vals in sorted(per.items(), key=lambda kv:(-len(kv[1]), kv[0])):
    a,m,mn,mx,k=s(vals)
    print(f"  {lbl}: avg={a:.4f} median={m:.4f} min={mn:.4f} max={mx:.4f} n={k}")
print("TOP10_NON_NOUR=")
for i,r in enumerate(non_nour[:10],1):
    print(f"  {i}. {r['label']} conf={r['conf']:.4f} ts={r['timestamp']}")
if pivot is not None:
    tot=len(non_nour)
    print(f"NON_NOUR_CONF_VS_THRESHOLD({pivot}): high={high} ({(high/tot*100 if tot else 0):.2f}%) low={low} ({(low/tot*100 if tot else 0):.2f}%)")
