"""
Step 10: External Open-Set Calibration
Builds threshold recommendations from external/negative faces and validation known faces.
Outputs: external_calibration.json
"""

import json
import importlib.util
from pathlib import Path

import cv2
import numpy as np


def load_rtc_module(base_path: Path):
    rtc_path = base_path / "06_real_time_camera.py"
    spec = importlib.util.spec_from_file_location("rtc_module", rtc_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def percentile_or_none(values, q):
    if not values:
        return None
    return float(np.percentile(np.array(values, dtype=np.float32), q))


def detect_largest_face(gray, detector):
    faces = detector.detectMultiScale(gray, 1.1, 5, minSize=(35, 35))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])

    # Match runtime adaptive padding strategy.
    face_scale = max(w, h)
    if face_scale < 90:
        pad_ratio = 0.22
    elif face_scale < 160:
        pad_ratio = 0.14
    else:
        pad_ratio = 0.08

    pad = int(pad_ratio * face_scale)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(gray.shape[1], x + w + pad)
    y2 = min(gray.shape[0], y + h + pad)

    face_region = gray[y1:y2, x1:x2]
    if face_region.shape[0] < 20 or face_region.shape[1] < 20:
        return None
    return face_region


def compute_metrics_for_face(face_region, system, module):
    score_list = []
    for variant in system._make_face_variants(face_region):
        features = module.compute_lbp_histogram(variant).reshape(1, -1)
        score_list.append(system._blend_scores(features))

    stacked_scores = np.vstack(score_list)
    blended_scores = 0.6 * np.mean(stacked_scores, axis=0) + 0.4 * np.max(stacked_scores, axis=0)

    pred_idx = int(np.argmax(blended_scores))
    max_prob = float(blended_scores[pred_idx])
    sorted_probs = np.sort(blended_scores)
    second_prob = float(sorted_probs[-2]) if len(sorted_probs) > 1 else 0.0
    margin = max_prob - second_prob

    variant_pred_indices = np.argmax(stacked_scores, axis=1)
    agreement_ratio = float(np.mean(variant_pred_indices == pred_idx))

    pred_class = str(system.label_encoder.classes_[pred_idx])

    return {
        "pred_class": pred_class,
        "max_prob": max_prob,
        "margin": float(margin),
        "agreement": agreement_ratio,
    }


def collect_external_metrics(system, module, external_dir):
    detector = system.face_cascade
    image_paths = sorted(
        list(external_dir.glob("*.jpg"))
        + list(external_dir.glob("*.jpeg"))
        + list(external_dir.glob("*.png"))
    )

    rows = []
    for p in image_paths:
        img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        face_region = detect_largest_face(img, detector)
        if face_region is None:
            continue
        row = compute_metrics_for_face(face_region, system, module)
        row["source"] = str(p.name)
        rows.append(row)

    return rows, len(image_paths)


def collect_known_val_metrics(system, module, val_dir):
    detector = system.face_cascade
    rows = []

    for class_dir in sorted([d for d in val_dir.iterdir() if d.is_dir()]):
        true_label = class_dir.name
        image_paths = sorted(
            list(class_dir.glob("*.jpg"))
            + list(class_dir.glob("*.jpeg"))
            + list(class_dir.glob("*.png"))
        )

        for p in image_paths:
            img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            face_region = detect_largest_face(img, detector)
            if face_region is None:
                continue
            row = compute_metrics_for_face(face_region, system, module)
            row["true_label"] = true_label
            row["correct"] = row["pred_class"] == true_label
            rows.append(row)

    return rows


def recommend_thresholds(system, external_rows, known_rows):
    rec_conf = float(system.confidence_threshold)
    rec_margin = float(system.margin_threshold)
    rec_class_min = dict(system.class_min_confidence)
    max_conf_threshold = 0.45
    max_margin_threshold = 0.08
    max_class_delta = 0.12

    ext_probs = [r["max_prob"] for r in external_rows]
    ext_margins = [r["margin"] for r in external_rows]
    known_correct = [r for r in known_rows if r.get("correct")]
    known_probs = [r["max_prob"] for r in known_correct]
    known_margins = [r["margin"] for r in known_correct]

    ext_prob_p90 = percentile_or_none(ext_probs, 90)
    ext_prob_p95 = percentile_or_none(ext_probs, 95)
    known_prob_p10 = percentile_or_none(known_probs, 10)

    ext_margin_p90 = percentile_or_none(ext_margins, 90)
    known_margin_p10 = percentile_or_none(known_margins, 10)

    # Global confidence threshold: push above most external confidences, while
    # keeping below low-end known correct confidence where possible.
    if ext_prob_p90 is not None:
        target = min(0.80, ext_prob_p90 + 0.03)
        if known_prob_p10 is not None:
            target = min(target, max(system.confidence_threshold, known_prob_p10 - 0.02))
        rec_conf = max(system.confidence_threshold, target)
    rec_conf = min(rec_conf, max_conf_threshold)

    # Global margin threshold: require more separation if external margins are high.
    if ext_margin_p90 is not None:
        target_margin = min(0.20, ext_margin_p90 + 0.01)
        if known_margin_p10 is not None:
            target_margin = min(target_margin, max(system.margin_threshold, 0.9 * known_margin_p10))
        rec_margin = max(system.margin_threshold, target_margin)
    rec_margin = min(rec_margin, max_margin_threshold)

    # Per-class minimum confidence from external false-accept distributions.
    for cls_name in rec_class_min.keys():
        ext_cls = [r["max_prob"] for r in external_rows if r["pred_class"] == cls_name]
        known_cls = [
            r["max_prob"]
            for r in known_correct
            if r.get("true_label") == cls_name
        ]

        if not ext_cls:
            continue

        ext_cls_p95 = percentile_or_none(ext_cls, 95)
        if ext_cls_p95 is None:
            continue

        candidate = min(0.90, ext_cls_p95 + 0.03)

        known_cls_p10 = percentile_or_none(known_cls, 10)
        if known_cls_p10 is not None:
            candidate = min(candidate, max(rec_class_min[cls_name], known_cls_p10 - 0.02))

        candidate = max(rec_class_min[cls_name], candidate)
        rec_class_min[cls_name] = min(candidate, rec_class_min[cls_name] + max_class_delta)

    return {
        "confidence_threshold": round(float(rec_conf), 4),
        "margin_threshold": round(float(rec_margin), 4),
        "class_min_confidence": {k: round(float(v), 4) for k, v in rec_class_min.items()},
        "stats": {
            "external_prob_p90": ext_prob_p90,
            "external_prob_p95": ext_prob_p95,
            "known_correct_prob_p10": known_prob_p10,
            "external_margin_p90": ext_margin_p90,
            "known_correct_margin_p10": known_margin_p10,
        },
    }


def main():
    base = Path(__file__).parent
    external_dir = base / "external_faces"
    val_dir = base / "data_split" / "val"

    if not external_dir.exists():
        print("Error: external_faces folder not found.")
        return
    if not val_dir.exists():
        print("Error: data_split/val not found. Run 03_train_test_split.py first.")
        return

    module = load_rtc_module(base)
    system = module.FaceRecognitionSystem()

    ext_rows, ext_total_images = collect_external_metrics(system, module, external_dir)
    known_rows = collect_known_val_metrics(system, module, val_dir)

    if not ext_rows:
        print("Error: no usable external faces found for calibration.")
        return
    if not known_rows:
        print("Error: no usable validation faces found for calibration.")
        return

    rec = recommend_thresholds(system, ext_rows, known_rows)

    report = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "source": {
            "external_faces_dir": str(external_dir),
            "external_total_images": ext_total_images,
            "external_used_faces": len(ext_rows),
            "validation_used_faces": len(known_rows),
        },
        "current": {
            "confidence_threshold": float(system.confidence_threshold),
            "margin_threshold": float(system.margin_threshold),
            "class_min_confidence": {k: float(v) for k, v in system.class_min_confidence.items()},
        },
        "recommended": {
            "confidence_threshold": rec["confidence_threshold"],
            "margin_threshold": rec["margin_threshold"],
            "class_min_confidence": rec["class_min_confidence"],
        },
        "stats": rec["stats"],
    }

    out_path = base / "external_calibration.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("=" * 70)
    print("EXTERNAL OPEN-SET CALIBRATION COMPLETE")
    print("=" * 70)
    print(f"External images found: {ext_total_images}")
    print(f"External faces used:   {len(ext_rows)}")
    print(f"Validation faces used: {len(known_rows)}")
    print("\nRecommended thresholds:")
    print(f"  confidence_threshold: {report['recommended']['confidence_threshold']}")
    print(f"  margin_threshold:     {report['recommended']['margin_threshold']}")
    print(f"  class_min_confidence: {report['recommended']['class_min_confidence']}")
    print(f"\nSaved: {out_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
