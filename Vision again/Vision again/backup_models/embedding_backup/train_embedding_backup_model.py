"""
Train an isolated backup face recognizer using InsightFace embeddings.

This script writes only inside backup_models/embedding_backup/artifacts.
It does not modify the active models/ folder or 06_real_time_camera.py.
"""

import json
import pickle
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import SVC
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKUP_ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = BACKUP_ROOT / "artifacts"
CACHE_DIR = ARTIFACTS_DIR / "cache"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")


def l2_normalize(vector):
    vector = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(vector) + 1e-8
    return vector / norm


def load_face_app():
    try:
        from insightface.app import FaceAnalysis
    except ImportError as exc:
        raise RuntimeError(
            "insightface is required for this backup model. Install requirements.txt "
            "in the Python environment you use for training."
        ) from exc

    app = FaceAnalysis(
        name="buffalo_l",
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    app.prepare(ctx_id=0, det_size=(640, 640))
    return app


def detect_embedding(face_app, image_bgr):
    faces = face_app.get(image_bgr)

    if not faces:
        # Some split images are tight face crops. Padding often lets the detector
        # see enough context to recover landmarks without changing active data.
        padded = cv2.copyMakeBorder(
            image_bgr,
            80,
            80,
            80,
            80,
            borderType=cv2.BORDER_REPLICATE,
        )
        faces = face_app.get(padded)

    if not faces:
        return None, None

    face = max(faces, key=lambda f: float((f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])))
    embedding = getattr(face, "normed_embedding", None)
    if embedding is None:
        embedding = l2_normalize(face.embedding)
    else:
        embedding = l2_normalize(embedding)
    bbox = [float(v) for v in face.bbox]
    return embedding, bbox


def iter_images(split_name):
    split_dir = PROJECT_ROOT / "data_split" / split_name
    if not split_dir.exists():
        raise FileNotFoundError(f"Missing split directory: {split_dir}")

    for class_dir in sorted(p for p in split_dir.iterdir() if p.is_dir()):
        for image_path in sorted(class_dir.iterdir()):
            if image_path.suffix.lower() in IMAGE_EXTENSIONS:
                yield class_dir.name, image_path


def image_signature(image_path):
    stat = image_path.stat()
    return {
        "path": str(image_path),
        "mtime_ns": int(stat.st_mtime_ns),
        "size": int(stat.st_size),
    }


def load_embedding_cache(cache_path):
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, "rb") as f:
            cache = pickle.load(f)
        if isinstance(cache, dict):
            return cache
    except Exception as exc:
        print(f"Could not load cache {cache_path.name}; rebuilding. Error: {exc}")
    return {}


def save_embedding_cache(cache_path, cache):
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    with open(tmp_path, "wb") as f:
        pickle.dump(cache, f)
    tmp_path.replace(cache_path)


def extract_split(face_app, split_name):
    embeddings = []
    labels = []
    failed = []
    cache_path = CACHE_DIR / f"{split_name}_embeddings.pkl"
    cache = load_embedding_cache(cache_path)
    images = list(iter_images(split_name))
    cache_hits = 0
    cache_misses = 0

    progress = tqdm(images, desc=f"Extracting {split_name}", unit="img")
    for idx, (label, image_path) in enumerate(progress, start=1):
        sig = image_signature(image_path)
        cache_key = str(image_path)
        cached = cache.get(cache_key)
        if cached and cached.get("signature") == sig:
            embedding = cached.get("embedding")
            cached_label = cached.get("label")
            if embedding is not None and cached_label == label:
                embeddings.append(np.asarray(embedding, dtype=np.float32))
                labels.append(label)
                cache_hits += 1
                progress.set_postfix(hit=cache_hits, miss=cache_misses, fail=len(failed))
                continue

        cache_misses += 1
        image = cv2.imread(str(image_path))
        if image is None:
            failed.append(str(image_path))
            cache.pop(cache_key, None)
            progress.set_postfix(hit=cache_hits, miss=cache_misses, fail=len(failed))
            continue

        embedding, _ = detect_embedding(face_app, image)
        if embedding is None:
            failed.append(str(image_path))
            cache.pop(cache_key, None)
            progress.set_postfix(hit=cache_hits, miss=cache_misses, fail=len(failed))
            continue

        embeddings.append(embedding)
        labels.append(label)
        cache[cache_key] = {
            "signature": sig,
            "label": label,
            "embedding": np.asarray(embedding, dtype=np.float32),
        }

        if idx % 25 == 0:
            save_embedding_cache(cache_path, cache)
        progress.set_postfix(hit=cache_hits, miss=cache_misses, fail=len(failed))

    save_embedding_cache(cache_path, cache)
    print(
        f"{split_name}: embeddings={len(embeddings)}, "
        f"cache_hits={cache_hits}, extracted={cache_misses}, failed={len(failed)}"
    )

    if not embeddings:
        raise RuntimeError(f"No embeddings extracted from split: {split_name}")

    return np.vstack(embeddings).astype(np.float32), np.array(labels), failed


def extract_external(face_app):
    external_dir = PROJECT_ROOT / "external_faces"
    if not external_dir.exists():
        return np.empty((0, 512), dtype=np.float32), []

    embeddings = []
    failed = []
    cache_path = CACHE_DIR / "external_embeddings.pkl"
    cache = load_embedding_cache(cache_path)
    image_paths = [
        path for path in sorted(external_dir.iterdir())
        if path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    cache_hits = 0
    cache_misses = 0

    progress = tqdm(image_paths, desc="Extracting external", unit="img")
    for idx, image_path in enumerate(progress, start=1):
        if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        sig = image_signature(image_path)
        cache_key = str(image_path)
        cached = cache.get(cache_key)
        if cached and cached.get("signature") == sig:
            embedding = cached.get("embedding")
            if embedding is not None:
                embeddings.append(np.asarray(embedding, dtype=np.float32))
                cache_hits += 1
                progress.set_postfix(hit=cache_hits, miss=cache_misses, fail=len(failed))
                continue

        cache_misses += 1
        image = cv2.imread(str(image_path))
        if image is None:
            failed.append(str(image_path))
            cache.pop(cache_key, None)
            progress.set_postfix(hit=cache_hits, miss=cache_misses, fail=len(failed))
            continue
        embedding, _ = detect_embedding(face_app, image)
        if embedding is None:
            failed.append(str(image_path))
            cache.pop(cache_key, None)
            progress.set_postfix(hit=cache_hits, miss=cache_misses, fail=len(failed))
            continue
        embeddings.append(embedding)
        cache[cache_key] = {
            "signature": sig,
            "embedding": np.asarray(embedding, dtype=np.float32),
        }

        if idx % 25 == 0:
            save_embedding_cache(cache_path, cache)
        progress.set_postfix(hit=cache_hits, miss=cache_misses, fail=len(failed))

    save_embedding_cache(cache_path, cache)
    print(
        f"external: embeddings={len(embeddings)}, "
        f"cache_hits={cache_hits}, extracted={cache_misses}, failed={len(failed)}"
    )

    if not embeddings:
        return np.empty((0, 512), dtype=np.float32), failed
    return np.vstack(embeddings).astype(np.float32), failed


def build_prototypes(embeddings, encoded_labels, label_encoder):
    prototypes = {}
    for class_index, class_name in enumerate(label_encoder.classes_):
        class_embeddings = embeddings[encoded_labels == class_index]
        if len(class_embeddings) == 0:
            continue
        prototypes[class_name] = l2_normalize(np.mean(class_embeddings, axis=0))
    return prototypes


def prototype_scores(embeddings, prototypes, label_encoder):
    scores = np.zeros((len(embeddings), len(label_encoder.classes_)), dtype=np.float32)
    for idx, class_name in enumerate(label_encoder.classes_):
        proto = prototypes[class_name]
        scores[:, idx] = embeddings @ proto
    return scores


def select_classifier(train_x, train_y, val_x, val_y):
    candidates = [
        SVC(kernel="linear", C=0.1, class_weight="balanced", probability=True),
        SVC(kernel="linear", C=1.0, class_weight="balanced", probability=True),
        SVC(kernel="linear", C=5.0, class_weight="balanced", probability=True),
        SVC(kernel="rbf", C=1.0, gamma="scale", class_weight="balanced", probability=True),
        SVC(kernel="rbf", C=5.0, gamma="scale", class_weight="balanced", probability=True),
    ]

    best_model = None
    best_score = -1.0
    best_name = None
    for model in candidates:
        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("svm", model),
        ])
        pipe.fit(train_x, train_y)
        score = pipe.score(val_x, val_y)
        name = f"{model.kernel}_C{model.C}"
        print(f"candidate={name} val_accuracy={score:.4f}")
        if score > best_score:
            best_model = pipe
            best_score = score
            best_name = name

    return best_model, best_name, best_score


def calibrate_thresholds(classifier, val_x, val_y, prototypes, label_encoder, external_x):
    val_probs = classifier.predict_proba(val_x)
    val_max_probs = np.max(val_probs, axis=1)
    val_preds = np.argmax(val_probs, axis=1)
    val_correct = val_preds == val_y

    proto = prototype_scores(val_x, prototypes, label_encoder)
    true_proto_scores = proto[np.arange(len(val_y)), val_y]

    correct_probs = val_max_probs[val_correct]
    if len(correct_probs):
        confidence_threshold = float(max(0.25, min(0.75, np.percentile(correct_probs, 5) * 0.85)))
    else:
        confidence_threshold = 0.35

    prototype_threshold = float(max(0.15, min(0.55, np.percentile(true_proto_scores, 5) - 0.03)))

    external_summary = {}
    if len(external_x):
        external_probs = classifier.predict_proba(external_x)
        external_max = np.max(external_probs, axis=1)
        confidence_threshold = float(max(confidence_threshold, min(0.80, np.percentile(external_max, 90) + 0.02)))
        external_summary = {
            "external_count": int(len(external_x)),
            "external_max_prob_p90": float(np.percentile(external_max, 90)),
            "external_max_prob_p95": float(np.percentile(external_max, 95)),
        }

    return confidence_threshold, prototype_threshold, external_summary


def evaluate(name, classifier, x, y, label_encoder):
    probs = classifier.predict_proba(x)
    preds = np.argmax(probs, axis=1)
    return {
        "split": name,
        "accuracy": float(accuracy_score(y, preds)),
        "f1_weighted": float(f1_score(y, preds, average="weighted", zero_division=0)),
        "confusion_matrix": confusion_matrix(y, preds).tolist(),
        "labels": [str(label) for label in label_encoder.classes_],
        "mean_confidence": float(np.mean(np.max(probs, axis=1))),
    }


def main():
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading InsightFace...")
    face_app = load_face_app()

    print("Extracting embeddings...")
    train_x, train_labels, train_failed = extract_split(face_app, "train")
    val_x, val_labels, val_failed = extract_split(face_app, "val")
    test_x, test_labels, test_failed = extract_split(face_app, "test")
    external_x, external_failed = extract_external(face_app)

    label_encoder = LabelEncoder()
    train_y = label_encoder.fit_transform(train_labels)
    val_y = label_encoder.transform(val_labels)
    test_y = label_encoder.transform(test_labels)

    print("Selecting classifier...")
    classifier, classifier_name, val_score = select_classifier(train_x, train_y, val_x, val_y)

    prototypes = build_prototypes(train_x, train_y, label_encoder)
    confidence_threshold, prototype_threshold, external_summary = calibrate_thresholds(
        classifier,
        val_x,
        val_y,
        prototypes,
        label_encoder,
        external_x,
    )

    report = {
        "created_at": datetime.now().isoformat(),
        "model_type": "insightface_embedding_svm_backup",
        "active_in_runtime": False,
        "classifier": classifier_name,
        "validation_selection_accuracy": float(val_score),
        "confidence_threshold": confidence_threshold,
        "prototype_threshold": prototype_threshold,
        "train_count": int(len(train_x)),
        "val_count": int(len(val_x)),
        "test_count": int(len(test_x)),
        "failed": {
            "train": train_failed,
            "val": val_failed,
            "test": test_failed,
            "external": external_failed,
        },
        "external_summary": external_summary,
        "validation": evaluate("val", classifier, val_x, val_y, label_encoder),
        "test": evaluate("test", classifier, test_x, test_y, label_encoder),
    }

    artifact = {
        "created_at": report["created_at"],
        "model_type": report["model_type"],
        "classifier": classifier,
        "label_encoder": label_encoder,
        "class_names": [str(label) for label in label_encoder.classes_],
        "prototypes": prototypes,
        "confidence_threshold": confidence_threshold,
        "prototype_threshold": prototype_threshold,
        "report": report,
    }

    with open(ARTIFACTS_DIR / "embedding_backup_model.pkl", "wb") as f:
        pickle.dump(artifact, f)

    with open(ARTIFACTS_DIR / "backup_model_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Saved: {ARTIFACTS_DIR / 'embedding_backup_model.pkl'}")
    print(f"Saved: {ARTIFACTS_DIR / 'backup_model_report.json'}")
    print(f"Test accuracy: {report['test']['accuracy']:.4f}")


if __name__ == "__main__":
    main()
