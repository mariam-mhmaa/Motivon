"""
Face Recognition System - Step 6: Real-Time Camera Testing
Test face recognition on Raspberry Pi Camera V2 RAW TCP stream.

Run this file on the laptop.

Before running this file, run this on the Raspberry Pi:

pkill -f rpicam
pkill -f ffmpeg

rpicam-vid -t 0 -n --width 320 --height 240 --framerate 10 --codec yuv420 -o - | ffmpeg -f rawvideo -pix_fmt yuv420p -s:v 320x240 -r 10 -i - -pix_fmt bgr24 -f rawvideo "tcp://0.0.0.0:8888?listen=1"

This sends fixed-size raw BGR frames: 320 * 240 * 3 bytes per frame.
"""

import cv2
import numpy as np
import pickle
import json
from datetime import datetime
from pathlib import Path
from collections import deque
import socket


# =========================
# RAW TCP CAMERA CONFIG
# =========================
PI_CAMERA_HOST = "172.20.10.2"
PI_CAMERA_PORT = 8888
RAW_FRAME_WIDTH = 320
RAW_FRAME_HEIGHT = 240
PI_CAMERA_STREAM_URL = f"tcp://{PI_CAMERA_HOST}:{PI_CAMERA_PORT}"

PROCESS_EVERY_N_FRAMES = 2  # 2 = process every second frame, reducing recognition lag.
DISPLAY_WIDTH = 640         # Resize only for laptop display.
DISPLAY_HEIGHT = 480


def compute_lbp_histogram(gray):
    """Compute LBP texture histogram features on a 4x4 grid."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.resize(gray, (64, 64))

    lbp = np.zeros_like(gray, dtype=np.uint8)
    center = gray[1:-1, 1:-1]
    lbp[1:-1, 1:-1] |= ((gray[:-2, :-2] >= center) << 7).astype(np.uint8)
    lbp[1:-1, 1:-1] |= ((gray[:-2, 1:-1] >= center) << 6).astype(np.uint8)
    lbp[1:-1, 1:-1] |= ((gray[:-2, 2:] >= center) << 5).astype(np.uint8)
    lbp[1:-1, 1:-1] |= ((gray[1:-1, 2:] >= center) << 4).astype(np.uint8)
    lbp[1:-1, 1:-1] |= ((gray[2:, 2:] >= center) << 3).astype(np.uint8)
    lbp[1:-1, 1:-1] |= ((gray[2:, 1:-1] >= center) << 2).astype(np.uint8)
    lbp[1:-1, 1:-1] |= ((gray[2:, :-2] >= center) << 1).astype(np.uint8)
    lbp[1:-1, 1:-1] |= ((gray[1:-1, :-2] >= center) << 0).astype(np.uint8)

    cell_h, cell_w = 16, 16
    features = []
    for i in range(0, 64, cell_h):
        for j in range(0, 64, cell_w):
            cell = lbp[i:i + cell_h, j:j + cell_w]
            hist = np.histogram(cell, bins=32, range=(0, 256))[0]
            hist = hist.astype(np.float32) / (hist.sum() + 1e-6)
            features.extend(hist)

    return np.array(features, dtype=np.float32)


class RawTCPFrameReader:
    """
    MJPEG-over-TCP frame reader.

    It keeps the same class name as before so the rest of your code does not need to change.
    Instead of assuming fixed-size raw frames, it searches for JPEG start/end markers:
    JPEG start = FF D8
    JPEG end   = FF D9
    """

    def __init__(self, host="172.20.10.2", port=8888, width=320, height=240):
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.sock = None
        self.buffer = bytearray()

    def open(self):
        print(f"Connecting to MJPEG TCP camera stream at {self.host}:{self.port}...")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect((self.host, self.port))
        self.sock.settimeout(3)
        print("✓ MJPEG TCP camera stream opened")
        return True

    def read(self):
        while True:
            start = self.buffer.find(b"\xff\xd8")
            end = self.buffer.find(b"\xff\xd9")

            if start != -1 and end != -1 and end > start:
                jpg = bytes(self.buffer[start:end + 2])
                del self.buffer[:end + 2]

                img_array = np.frombuffer(jpg, dtype=np.uint8)
                frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

                if frame is None:
                    continue

                return True, frame

            try:
                packet = self.sock.recv(4096)
            except socket.timeout:
                return False, None

            if not packet:
                return False, None

            self.buffer.extend(packet)

            # Prevent unlimited memory growth if something goes wrong.
            if len(self.buffer) > 2_000_000:
                self.buffer = self.buffer[-500_000:]

    def release(self):
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

class FaceRecognitionSystem:
    def __init__(
        self,
        confidence_threshold=0.26,
        margin_threshold=0.03,
        use_external_calibration=False,
        use_known_detector=False,
    ):
        """Initialize face recognition system."""
        self.confidence_threshold = confidence_threshold
        self.margin_threshold = margin_threshold
        self.class_min_confidence = {
            "Ainour": 0.18,
            "Mariam": 0.16,
            "Nour": 0.18,
            "Zeina": 0.14,
        }
        self.label_to_idx = {}

        self.published_detections = []
        self.processing_stats = {
            "total_frames_processed": 0,
            "total_detections_published": 0,
            "total_unknowns_detected": 0,
        }

        models_path = Path(__file__).parent / "models"

        print("📦 Loading trained models...")
        with open(models_path / "classifier.pkl", "rb") as f:
            self.classifier = pickle.load(f)

        self.knn_classifier = None
        knn_path = models_path / "knn_classifier.pkl"
        if knn_path.exists():
            with open(knn_path, "rb") as f:
                self.knn_classifier = pickle.load(f)

        self.known_detector = None
        self.known_threshold = 0.55
        self.use_known_detector = use_known_detector
        if self.use_known_detector:
            known_detector_path = models_path / "known_detector.pkl"
            known_threshold_path = models_path / "known_detector_threshold.json"
            if known_detector_path.exists():
                with open(known_detector_path, "rb") as f:
                    self.known_detector = pickle.load(f)
                if known_threshold_path.exists():
                    try:
                        with open(known_threshold_path, "r", encoding="utf-8") as f:
                            kd_cfg = json.load(f)
                        thr = kd_cfg.get("known_threshold")
                        if isinstance(thr, (int, float)):
                            self.known_threshold = float(thr)
                    except Exception:
                        pass

        with open(models_path / "label_encoder.pkl", "rb") as f:
            self.label_encoder = pickle.load(f)
        self.label_to_idx = {name: idx for idx, name in enumerate(self.label_encoder.classes_)}

        self.class_prototypes = self._build_class_prototypes()
        self.class_distance_thresholds = self._build_class_distance_thresholds()

        print("🔍 Initializing face detector...")
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

        self.prediction_history = deque(maxlen=7)

        self.locked_identity = None
        self.pending_identity = None
        self.pending_count = 0
        self.required_lock_frames = 3
        self.lock_min_confidence = {
            "Ainour": 0.54,
            "Mariam": 0.52,
            "Nour": 0.60,
            "Zeina": 0.40,
        }
        self.lock_min_margin = {
            "Ainour": 0.05,
            "Mariam": 0.04,
            "Nour": 0.06,
            "Zeina": 0.02,
        }
        self.switch_candidate = None
        self.switch_count = 0
        self.required_switch_frames = 3
        self.last_known_prob = None
        self.unknown_streak = 0
        self.max_unknown_hold_frames = 3
        self.ainour_unknown_hold_frames = 5
        self.zeina_unknown_hold_frames = 5
        self.ainour_switch_frames = 7
        self.ainour_switch_min_confidence = 0.92
        self.ainour_switch_min_margin = 0.08
        self.zeina_switch_frames = 5
        self.zeina_switch_min_confidence = 0.62
        self.zeina_switch_min_margin = 0.05

        if use_external_calibration:
            self._load_external_calibration()

        print("✓ System ready!")

    def _load_external_calibration(self):
        """Load optional calibration generated from external/negative faces."""
        calibration_path = Path(__file__).parent / "external_calibration.json"
        if not calibration_path.exists():
            return

        max_conf_threshold = 0.40
        max_margin_threshold = 0.06
        max_class_delta_by_class = {
            "Ainour": 0.06,
            "Mariam": 0.08,
            "Nour": 0.10,
            "Zeina": 0.10,
        }
        base_class_min = dict(self.class_min_confidence)

        try:
            with open(calibration_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            rec = data.get("recommended", {}) if isinstance(data, dict) else {}

            rec_conf = rec.get("confidence_threshold")
            if isinstance(rec_conf, (int, float)):
                rec_conf = float(rec_conf)
                if 0.20 <= rec_conf <= 0.95:
                    self.confidence_threshold = min(rec_conf, max_conf_threshold)

            rec_margin = rec.get("margin_threshold")
            if isinstance(rec_margin, (int, float)):
                rec_margin = float(rec_margin)
                if 0.0 <= rec_margin <= 0.30:
                    self.margin_threshold = min(rec_margin, max_margin_threshold)

            rec_class_min = rec.get("class_min_confidence")
            if isinstance(rec_class_min, dict):
                for cls_name, cls_val in rec_class_min.items():
                    if cls_name in self.class_min_confidence and isinstance(cls_val, (int, float)):
                        cls_val = float(cls_val)
                        if 0.20 <= cls_val <= 0.95:
                            upper = base_class_min[cls_name] + max_class_delta_by_class.get(cls_name, 0.08)
                            self.class_min_confidence[cls_name] = min(cls_val, upper)

            print(f"🧪 Loaded external calibration: {calibration_path.name}")
            print(
                f"   threshold={self.confidence_threshold:.3f}, "
                f"margin={self.margin_threshold:.3f}, "
                f"class_min={self.class_min_confidence}"
            )
        except Exception as e:
            print(f"⚠️  Could not load external calibration ({calibration_path.name}): {e}")

    def publish_detection(self, person_name, confidence, bbox, is_unknown):
        """Create and store a structured detection message with confidence score."""
        if bbox is None or person_name is None:
            return None

        x1, y1, x2, y2 = [int(v) for v in bbox]
        message = {
            "header": {
                "timestamp": datetime.now().isoformat(),
                "frame_id": "camera_frame",
            },
            "detections": [
                {
                    "person_name": str(person_name),
                    "confidence_score": float(confidence),
                    "bounding_box": {
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "width": int(x2 - x1),
                        "height": int(y2 - y1),
                    },
                    "is_unknown": bool(is_unknown),
                    "classification_result": {
                        "predicted_class": str(person_name),
                        "confidence": float(confidence),
                        "threshold": float(self.confidence_threshold),
                    },
                }
            ],
        }

        self.published_detections.append(message)
        self.processing_stats["total_detections_published"] += 1
        if is_unknown:
            self.processing_stats["total_unknowns_detected"] += 1

        return message

    def save_detection_log(self, filename="real_time_camera_detections.json"):
        """Save published detections from the real-time pipeline."""
        log_data = {
            "node": "real_time_camera_publisher",
            "timestamp": datetime.now().isoformat(),
            "confidence_threshold": float(self.confidence_threshold),
            "statistics": {
                "total_frames_processed": int(self.processing_stats["total_frames_processed"]),
                "total_detections_published": int(self.processing_stats["total_detections_published"]),
                "total_unknowns_detected": int(self.processing_stats["total_unknowns_detected"]),
            },
            "detections": self.published_detections,
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)

        print(f"✓ Detection log saved: {filename}")
        return filename

    def _blend_scores(self, features):
        """Blend SVM, KNN, and prototype scores for one feature vector."""
        svm_probs = self.classifier.predict_proba(features)[0]

        knn_probs = np.zeros_like(svm_probs)
        if self.knn_classifier is not None:
            knn_probs = self.knn_classifier.predict_proba(features)[0]

        prototype_scores = np.zeros_like(svm_probs)
        if self.class_prototypes:
            feat_vec = features[0]
            for idx, class_name in enumerate(self.label_encoder.classes_):
                proto = self.class_prototypes.get(class_name)
                if proto is None:
                    continue
                dist = np.linalg.norm(feat_vec - proto)
                prototype_scores[idx] = 1.0 / (1.0 + dist)

            score_sum = np.sum(prototype_scores)
            if score_sum > 0:
                prototype_scores = prototype_scores / score_sum

        return 0.50 * svm_probs + 0.35 * knn_probs + 0.15 * prototype_scores

    def _make_face_variants(self, face_region):
        """Create pose/scale-robust variants: rotations, flip, zoom in/out."""
        h, w = face_region.shape[:2]
        center = (w // 2, h // 2)
        variants = [face_region]

        for angle in (-12, -6, 6, 12):
            rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(
                face_region,
                rot_mat,
                (w, h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE,
            )
            variants.append(rotated)

        for scale in (0.9, 1.1):
            scaled_w = max(20, int(w * scale))
            scaled_h = max(20, int(h * scale))
            scaled = cv2.resize(face_region, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)

            if scale > 1.0:
                sy = (scaled_h - h) // 2
                sx = (scaled_w - w) // 2
                scaled = scaled[sy:sy + h, sx:sx + w]
            else:
                out = np.zeros((h, w), dtype=scaled.dtype)
                y_off = (h - scaled_h) // 2
                x_off = (w - scaled_w) // 2
                out[y_off:y_off + scaled_h, x_off:x_off + scaled_w] = scaled
                scaled = out

            variants.append(scaled)

        variants.append(cv2.flip(face_region, 1))
        return variants

    def _build_class_prototypes(self):
        """Build mean feature prototype per class from data_split/train."""
        split_path = Path(__file__).parent / "data_split" / "train"
        prototypes = {}

        if not split_path.exists():
            return prototypes

        for class_name in self.label_encoder.classes_:
            class_dir = split_path / class_name
            if not class_dir.exists():
                continue

            image_paths = (
                list(class_dir.glob("*.jpg"))
                + list(class_dir.glob("*.jpeg"))
                + list(class_dir.glob("*.png"))
            )

            class_features = []
            for img_path in image_paths:
                img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue
                feat = compute_lbp_histogram(img)
                class_features.append(feat)

            if class_features:
                prototypes[class_name] = np.mean(np.vstack(class_features), axis=0)

        return prototypes

    def _build_class_distance_thresholds(self):
        """Build per-class outlier thresholds from train split feature distances to class prototype."""
        split_path = Path(__file__).parent / "data_split" / "train"
        thresholds = {}

        if not split_path.exists() or not self.class_prototypes:
            return thresholds

        for class_name in self.label_encoder.classes_:
            class_dir = split_path / class_name
            proto = self.class_prototypes.get(class_name)
            if proto is None or not class_dir.exists():
                continue

            image_paths = (
                list(class_dir.glob("*.jpg"))
                + list(class_dir.glob("*.jpeg"))
                + list(class_dir.glob("*.png"))
            )

            distances = []
            for img_path in image_paths:
                img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue
                feat = compute_lbp_histogram(img)
                distances.append(float(np.linalg.norm(feat - proto)))

            if distances:
                distances = np.array(distances, dtype=np.float32)
                thresholds[class_name] = float(np.percentile(distances, 92) * 1.05)

        return thresholds

    def recognize_face(self, image):
        """
        Recognize face in image.
        Returns: person_name, confidence, face_bbox, is_unknown, margin
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(35, 35))

        if len(faces) == 0:
            return None, 0.0, None, True, 0.0

        face = max(faces, key=lambda f: f[2] * f[3])
        x, y, w, h = face

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
            return None, 0.0, None, True, 0.0

        score_list = []
        known_prob_list = []
        for variant in self._make_face_variants(face_region):
            features = compute_lbp_histogram(variant).reshape(1, -1)
            score_list.append(self._blend_scores(features))
            if self.known_detector is not None:
                known_prob = float(self.known_detector.predict_proba(features)[0, 1])
                known_prob_list.append(known_prob)

        stacked_scores = np.vstack(score_list)
        blended_scores = 0.6 * np.mean(stacked_scores, axis=0) + 0.4 * np.max(stacked_scores, axis=0)

        predicted_label_idx = np.argmax(blended_scores)
        max_prob = blended_scores[predicted_label_idx]
        sorted_probs = np.sort(blended_scores)
        second_prob = sorted_probs[-2] if len(sorted_probs) > 1 else 0.0
        margin = max_prob - second_prob

        variant_pred_indices = np.argmax(stacked_scores, axis=1)
        agreement_ratio = float(np.mean(variant_pred_indices == predicted_label_idx))

        known_prob = None
        if known_prob_list:
            known_prob = float(np.median(np.array(known_prob_list, dtype=np.float32)))
        self.last_known_prob = known_prob

        if not self.use_known_detector:
            person_name = self.label_encoder.classes_[predicted_label_idx]
            bbox = np.array([x1, y1, x2, y2], dtype=int)
            return person_name, float(max_prob), bbox, False, float(margin)

        is_unknown = (max_prob < self.confidence_threshold) or (
            (margin < self.margin_threshold) and (max_prob < 0.48)
        ) or (
            (agreement_ratio < 0.50) and (max_prob < 0.72)
        )

        if (
            self.use_known_detector
            and (not is_unknown)
            and (known_prob is not None)
            and (known_prob < self.known_threshold)
        ):
            is_unknown = True

        if is_unknown:
            person_name = "UNKNOWN"
        else:
            person_name = self.label_encoder.classes_[predicted_label_idx]

            if self.use_known_detector and self.locked_identity is None:
                init_conf_gate = {
                    "Ainour": 0.20,
                    "Nour": 0.20,
                    "Mariam": 0.18,
                    "Zeina": 0.15,
                }.get(person_name, 0.18)
                init_margin_gate = {
                    "Ainour": 0.02,
                    "Nour": 0.02,
                    "Mariam": 0.015,
                    "Zeina": 0.01,
                }.get(person_name, 0.015)
                init_agreement_gate = {
                    "Ainour": 0.20,
                    "Nour": 0.20,
                    "Mariam": 0.18,
                    "Zeina": 0.15,
                }.get(person_name, 0.18)

                if (max_prob < init_conf_gate) or (margin < init_margin_gate) or (agreement_ratio < init_agreement_gate):
                    person_name = "UNKNOWN"
                    is_unknown = True

            if self.use_known_detector and (not is_unknown) and (self.locked_identity is None) and (person_name == "Ainour"):
                if (agreement_ratio < 0.52) and (max_prob < 0.74):
                    person_name = "UNKNOWN"
                    is_unknown = True
                elif (margin < 0.045) and (max_prob < 0.70):
                    person_name = "UNKNOWN"
                    is_unknown = True

            if self.use_known_detector and (not is_unknown) and (self.locked_identity is None) and (person_name == "Nour"):
                if (agreement_ratio < 0.62) and (max_prob < 0.78):
                    person_name = "UNKNOWN"
                    is_unknown = True
                elif (margin < 0.06) and (max_prob < 0.74):
                    person_name = "UNKNOWN"
                    is_unknown = True

            min_conf = self.class_min_confidence.get(person_name, self.confidence_threshold)
            if max_prob < min_conf:
                person_name = "UNKNOWN"
                is_unknown = True
            else:
                if self.use_known_detector and self.class_prototypes and self.class_distance_thresholds:
                    variant_features = [compute_lbp_histogram(v) for v in self._make_face_variants(face_region)]
                    class_distances = {}
                    for class_name, proto in self.class_prototypes.items():
                        dists = [float(np.linalg.norm(feat - proto)) for feat in variant_features]
                        class_distances[class_name] = float(np.median(dists))

                    if person_name == "Nour":
                        pred_candidate_dist = class_distances.get("Nour")
                        ainour_dist = class_distances.get("Ainour")
                        zeina_dist = class_distances.get("Zeina")
                        candidates = []
                        if (
                            pred_candidate_dist is not None
                            and ainour_dist is not None
                            and ainour_dist <= pred_candidate_dist * 1.01
                            and max_prob >= 0.44
                            and agreement_ratio >= 0.32
                        ):
                            candidates.append(("Ainour", ainour_dist))
                        if (
                            pred_candidate_dist is not None
                            and zeina_dist is not None
                            and zeina_dist <= pred_candidate_dist * 1.02
                            and max_prob >= 0.42
                            and agreement_ratio >= 0.30
                        ):
                            candidates.append(("Zeina", zeina_dist))

                        if candidates:
                            person_name = min(candidates, key=lambda x: x[1])[0]
                            cls_min_conf = self.class_min_confidence.get(person_name, self.confidence_threshold)
                            if max_prob < cls_min_conf:
                                person_name = "UNKNOWN"
                                is_unknown = True

                    pred_dist = class_distances.get(person_name)
                    dist_thr = self.class_distance_thresholds.get(person_name)

                    other_dists = [d for name, d in class_distances.items() if name != person_name]
                    second_best_dist = min(other_dists) if other_dists else float("inf")
                    if (pred_dist is not None) and (second_best_dist != float("inf")):
                        separation_ratio = pred_dist / (second_best_dist + 1e-6)
                    else:
                        separation_ratio = 0.0

                    if pred_dist is not None and dist_thr is not None:
                        if (pred_dist > dist_thr * 1.00) and (max_prob < 0.65):
                            person_name = "UNKNOWN"
                            is_unknown = True
                        elif (self.locked_identity is None) and (person_name in ("Ainour", "Nour")) and (pred_dist > dist_thr * 0.95):
                            person_name = "UNKNOWN"
                            is_unknown = True

        bbox = np.array([x1, y1, x2, y2], dtype=int)
        return person_name, max_prob, bbox, is_unknown, margin

    def smooth_prediction(self, person_name, confidence, is_unknown):
        """Stabilize predictions with confidence-weighted temporal voting."""
        if person_name is None:
            self.prediction_history.clear()
            return None, 0.0, True

        self.prediction_history.append((person_name, confidence, is_unknown))

        scores = {}
        for idx, (label, conf, unknown_flag) in enumerate(self.prediction_history):
            weight = (idx + 1) / len(self.prediction_history)
            effective_label = "UNKNOWN" if unknown_flag else label
            effective_conf = conf if not unknown_flag else conf * 0.5
            scores[effective_label] = scores.get(effective_label, 0.0) + weight * effective_conf

        best_label = max(scores, key=scores.get)
        total_score = sum(scores.values()) + 1e-6
        best_confidence = min(1.0, scores[best_label] / total_score)

        if best_label == "UNKNOWN":
            return "UNKNOWN", best_confidence, True

        return best_label, best_confidence, False

    def stabilize_identity(self, person_name, confidence, is_unknown, margin=0.0):
        """Apply hysteresis to avoid rapid identity flips across nearby frames."""
        if person_name is None:
            self.unknown_streak = 0
            self.pending_identity = None
            self.pending_count = 0
            return None, 0.0, True

        if is_unknown:
            self.unknown_streak += 1
            if self.locked_identity is not None:
                hold_frames = self.max_unknown_hold_frames
                if self.locked_identity == "Ainour":
                    hold_frames = self.ainour_unknown_hold_frames
                if self.locked_identity == "Zeina":
                    hold_frames = self.zeina_unknown_hold_frames
                if self.unknown_streak > hold_frames:
                    self.locked_identity = None
                    self.pending_identity = None
                    self.pending_count = 0
                    self.switch_candidate = None
                    self.switch_count = 0
                    return "UNKNOWN", confidence, True
                return self.locked_identity, confidence * 0.85, False
            return person_name, confidence, True

        self.unknown_streak = 0

        if self.locked_identity is None:
            min_lock_conf = self.lock_min_confidence.get(person_name, 0.52)
            min_lock_margin = self.lock_min_margin.get(person_name, 0.04)

            if (confidence < min_lock_conf) or (margin < min_lock_margin):
                self.pending_identity = None
                self.pending_count = 0
                return "UNKNOWN", confidence, True

            if self.pending_identity == person_name:
                self.pending_count += 1
            else:
                self.pending_identity = person_name
                self.pending_count = 1

            if self.pending_count < self.required_lock_frames:
                return "UNKNOWN", confidence * 0.8, True

            self.locked_identity = person_name
            self.pending_identity = None
            self.pending_count = 0
            self.switch_candidate = None
            self.switch_count = 0
            return person_name, confidence, False

        if person_name == self.locked_identity:
            self.switch_candidate = None
            self.switch_count = 0
            return person_name, confidence, False

        if self.locked_identity == "Ainour" and person_name == "Zeina":
            if (confidence < self.ainour_switch_min_confidence) or (margin < self.ainour_switch_min_margin):
                self.switch_candidate = None
                self.switch_count = 0
                return self.locked_identity, confidence * 0.9, False

        if self.locked_identity == "Zeina" and person_name in ("Ainour", "Nour"):
            if (confidence < self.zeina_switch_min_confidence) or (margin < self.zeina_switch_min_margin):
                self.switch_candidate = None
                self.switch_count = 0
                return self.locked_identity, confidence * 0.9, False

        if self.switch_candidate == person_name:
            self.switch_count += 1
        else:
            self.switch_candidate = person_name
            self.switch_count = 1

        required_frames = self.required_switch_frames
        if self.locked_identity == "Ainour" and person_name == "Zeina":
            required_frames = self.ainour_switch_frames
        if self.locked_identity == "Zeina" and person_name in ("Ainour", "Nour"):
            required_frames = self.zeina_switch_frames

        if self.switch_count >= required_frames:
            self.locked_identity = person_name
            self.pending_identity = None
            self.pending_count = 0
            self.switch_candidate = None
            self.switch_count = 0
            return person_name, confidence, False

        return self.locked_identity, confidence * 0.9, False

    def draw_predictions(self, image, person_name, confidence, bbox, is_unknown):
        """Draw predictions on image."""
        if bbox is None:
            cv2.putText(image, "NO FACE DETECTED", (50, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)
            return image

        x1, y1, x2, y2 = bbox

        if is_unknown:
            color = (0, 0, 255)
            thickness = 3
        else:
            color = (0, 255, 0)
            thickness = 3

        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)

        label = f"{person_name}: {confidence:.2f}"
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)

        cv2.rectangle(image, (x1, y1 - 35), (x1 + label_size[0], y1), color, -1)
        cv2.putText(image, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)

        return image

    def draw_info_panel(
        self,
        frame,
        frame_count,
        smoothing_enabled,
        raw_person_name,
        raw_confidence,
        person_name,
        confidence,
        raw_is_unknown,
        is_unknown,
        stream_mode,
    ):
        """Draw runtime information overlay."""
        info_text = [
            f"Frame: {frame_count}",
            f"Camera: Raspberry Pi RAW TCP stream ({stream_mode})",
            f"Smoothing: {'ON' if smoothing_enabled else 'OFF'}",
            f"Process every: {PROCESS_EVERY_N_FRAMES} frame(s)",
            f"Threshold: {self.confidence_threshold:.2f}",
            f"Known detector: {'ON' if self.use_known_detector else 'OFF'} (thr={self.known_threshold:.2f})",
            f"Known prob: {(self.last_known_prob if self.last_known_prob is not None else -1):.2f}",
            f"Raw: {(raw_person_name if raw_person_name else 'NO_FACE')} | conf={raw_confidence:.2f}",
            f"Smoothed: {(person_name if person_name else 'NO_FACE')} | conf={confidence:.2f}",
            f"Raw UNKNOWN: {'YES' if raw_is_unknown else 'NO'} | Final UNKNOWN: {'YES' if is_unknown else 'NO'}",
            f"Published: {self.processing_stats['total_detections_published']}",
            "",
            "Recognized classes:",
            "  • Ainour, Mariam",
            "  • Nour, Zeina",
            f"  • UNKNOWN (if <{self.confidence_threshold:.2f})",
        ]

        y_pos = 30
        for text in info_text:
            cv2.putText(frame, text, (10, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
            cv2.putText(frame, text, (10, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
            y_pos += 23

        return frame

    def run_camera(self, camera_source=PI_CAMERA_STREAM_URL):
        """Run real-time face recognition on Raspberry Pi RAW TCP camera stream."""

        print("=" * 70)
        print("FACE RECOGNITION SYSTEM - RASPBERRY PI CAMERA RAW TCP STREAM")
        print("=" * 70)
        print("\nControls:")
        print("  SPACE - Toggle smoothing ON/OFF")
        print("  C     - Capture screenshot")
        print("  S     - Save detection log")
        print("  Q     - Quit")
        print("\nStarting Raspberry Pi camera stream...")
        print(f"Camera source: {camera_source}")
        print("\nMake sure this is running on the Pi first:")
        print('rpicam-vid -t 0 -n --width 320 --height 240 --framerate 10 --codec yuv420 -o - | ffmpeg -f rawvideo -pix_fmt yuv420p -s:v 320x240 -r 10 -i - -pix_fmt bgr24 -f rawvideo "tcp://0.0.0.0:8888?listen=1"')
        print("-" * 70 + "\n")

        cap = RawTCPFrameReader(
            host=PI_CAMERA_HOST,
            port=PI_CAMERA_PORT,
            width=RAW_FRAME_WIDTH,
            height=RAW_FRAME_HEIGHT,
        )

        try:
            cap.open()
        except Exception as e:
            print("❌ Error: Could not open raw TCP Raspberry Pi camera stream.")
            print("Make sure the Pi raw BGR stream command is running first.")
            print(f"Error: {e}")
            return

        smoothing_enabled = True
        frame_count = 0
        last_person_name = None
        last_confidence = 0.0
        last_bbox = None
        last_is_unknown = True
        last_raw_person_name = None
        last_raw_confidence = 0.0
        last_raw_is_unknown = True
        stream_mode = "320x240 @ 10 fps raw BGR"

        try:
            while True:
                ret, frame = cap.read()

                if not ret:
                    print("Error reading frame from Raspberry Pi RAW TCP stream")
                    break

                frame_count += 1
                self.processing_stats["total_frames_processed"] = frame_count

                # Resize only for display readability. Recognition still works on the received frame.
                if DISPLAY_WIDTH and DISPLAY_HEIGHT:
                    display_frame = cv2.resize(frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
                    scale_x = DISPLAY_WIDTH / frame.shape[1]
                    scale_y = DISPLAY_HEIGHT / frame.shape[0]
                else:
                    display_frame = frame.copy()
                    scale_x = 1.0
                    scale_y = 1.0

                # Process only every N frames to reduce recognition lag.
                should_process = (frame_count % PROCESS_EVERY_N_FRAMES == 0)

                if should_process:
                    person_name, confidence, bbox, is_unknown, margin = self.recognize_face(frame)

                    raw_person_name = person_name
                    raw_confidence = confidence
                    raw_is_unknown = is_unknown

                    if smoothing_enabled:
                        person_name, confidence, is_unknown = self.smooth_prediction(
                            person_name,
                            confidence,
                            is_unknown,
                        )

                        person_name, confidence, is_unknown = self.stabilize_identity(
                            person_name,
                            confidence,
                            is_unknown,
                            margin,
                        )
                    else:
                        self.locked_identity = None
                        self.pending_identity = None
                        self.pending_count = 0
                        self.switch_candidate = None
                        self.switch_count = 0

                    self.publish_detection(person_name, confidence, bbox, is_unknown)

                    last_person_name = person_name
                    last_confidence = confidence
                    last_bbox = bbox
                    last_is_unknown = is_unknown
                    last_raw_person_name = raw_person_name
                    last_raw_confidence = raw_confidence
                    last_raw_is_unknown = raw_is_unknown

                    if frame_count % 10 == 0:
                        print(
                            f"[Track] frame={frame_count} "
                            f"raw={(raw_person_name if raw_person_name else 'NO_FACE')} "
                            f"raw_conf={raw_confidence:.2f} "
                            f"known_prob={(self.last_known_prob if self.last_known_prob is not None else -1):.3f} "
                            f"final={(person_name if person_name else 'NO_FACE')} "
                            f"final_conf={confidence:.2f} "
                            f"raw_unknown={raw_is_unknown} final_unknown={is_unknown} "
                            f"margin={margin:.3f}",
                            flush=True,
                        )

                # Draw the latest known prediction on every displayed frame.
                draw_bbox = last_bbox
                if draw_bbox is not None and (scale_x != 1.0 or scale_y != 1.0):
                    draw_bbox = np.array([
                        int(last_bbox[0] * scale_x),
                        int(last_bbox[1] * scale_y),
                        int(last_bbox[2] * scale_x),
                        int(last_bbox[3] * scale_y),
                    ], dtype=int)

                display_frame = self.draw_predictions(
                    display_frame,
                    last_person_name,
                    last_confidence,
                    draw_bbox,
                    last_is_unknown,
                )

                display_frame = self.draw_info_panel(
                    display_frame,
                    frame_count,
                    smoothing_enabled,
                    last_raw_person_name,
                    last_raw_confidence,
                    last_person_name,
                    last_confidence,
                    last_raw_is_unknown,
                    last_is_unknown,
                    stream_mode,
                )

                cv2.imshow("Face Recognition System - Pi RAW TCP Camera", display_frame)

                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    print("\n🛑 Exiting camera feed...")
                    break
                elif key == ord(" "):
                    smoothing_enabled = not smoothing_enabled
                    status = "ENABLED" if smoothing_enabled else "DISABLED"
                    print(f"✓ Smoothing {status}")
                elif key == ord("c"):
                    filename = f"capture_{frame_count}.jpg"
                    cv2.imwrite(filename, display_frame)
                    print(f"✓ Screenshot saved: {filename}")
                elif key == ord("s"):
                    self.save_detection_log()

        except KeyboardInterrupt:
            print("\n🛑 Interrupted by user. Closing camera feed...")

        finally:
            cap.release()
            cv2.destroyAllWindows()

            print("\n" + "=" * 70)
            print("✓ Camera session ended")
            print(f"  Frames processed: {self.processing_stats['total_frames_processed']}")
            print(f"  Detections published: {self.processing_stats['total_detections_published']}")
            print(f"  Unknown detections: {self.processing_stats['total_unknowns_detected']}")
            print("=" * 70)


def main():
    """Main function."""

    system = FaceRecognitionSystem(
        confidence_threshold=0.20,
        margin_threshold=0.02,
        use_external_calibration=False,
        use_known_detector=False,
    )

    system.run_camera(camera_source=PI_CAMERA_STREAM_URL)


if __name__ == "__main__":
    main()
