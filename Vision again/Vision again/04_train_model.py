"""
Face Recognition System - Step 4: Train Model
Train SVM classifier using LBPH features for face recognition
Uses OpenCV LBPH for feature extraction and SVM for classification
"""

import cv2
import numpy as np
import pickle
import json
from pathlib import Path
from tqdm import tqdm
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score


def select_best_svm(train_embeddings, train_labels_encoded, val_embeddings, val_labels_encoded, external_embeddings=None):
    """Select an SVM configuration balancing validation performance and external-face rejection."""

    candidate_configs = [
        {"kernel": "rbf", "C": 0.8, "gamma": "scale", "class_weight": "balanced"},
        {"kernel": "rbf", "C": 1.5, "gamma": "scale", "class_weight": "balanced"},
        {"kernel": "rbf", "C": 3.0, "gamma": "scale", "class_weight": "balanced"},
        {"kernel": "linear", "C": 1.0, "gamma": "scale", "class_weight": "balanced"},
    ]

    best_model = None
    best_config = None
    best_train = -1.0
    best_val = -1.0
    best_gap = float("inf")
    best_external_risk = float("inf")

    print("\n🔎 Selecting SVM config (validation-focused, anti-overfitting)...")
    for cfg in candidate_configs:
        model = Pipeline([
            ('scaler', StandardScaler()),
            ('svm', SVC(
                kernel=cfg["kernel"],
                C=cfg["C"],
                gamma=cfg["gamma"],
                class_weight=cfg["class_weight"],
                probability=True,
            ))
        ])

        model.fit(train_embeddings, train_labels_encoded)
        train_score = model.score(train_embeddings, train_labels_encoded)
        val_score = model.score(val_embeddings, val_labels_encoded)
        gap = train_score - val_score

        external_risk = 0.0
        if external_embeddings is not None and len(external_embeddings) > 0:
            ext_probs = model.predict_proba(external_embeddings)
            ext_max = np.max(ext_probs, axis=1)
            ext_sorted = np.sort(ext_probs, axis=1)
            ext_margin = ext_sorted[:, -1] - ext_sorted[:, -2]

            ext_p95 = float(np.percentile(ext_max, 95))
            ext_mean = float(np.mean(ext_max))
            ext_margin_p90 = float(np.percentile(ext_margin, 90))

            # Higher = riskier (external faces looking too confidently like known classes).
            external_risk = 0.65 * ext_p95 + 0.25 * ext_mean + 0.10 * ext_margin_p90

            print(
                f"  candidate={cfg} -> train={train_score:.4f}, val={val_score:.4f}, "
                f"gap={gap:.4f}, ext_risk={external_risk:.4f}"
            )
        else:
            print(
                f"  candidate={cfg} -> train={train_score:.4f}, "
                f"val={val_score:.4f}, gap={gap:.4f}"
            )

        is_better_val = val_score > best_val + 0.003
        is_similar_val_better_risk = (
            abs(val_score - best_val) <= 0.003
            and external_risk < best_external_risk - 1e-6
        )
        is_similar_val_risk_better_gap = (
            abs(val_score - best_val) <= 0.003
            and abs(external_risk - best_external_risk) <= 1e-6
            and gap < best_gap
        )
        if is_better_val or is_similar_val_better_risk or is_similar_val_risk_better_gap:
            best_model = model
            best_config = cfg
            best_train = train_score
            best_val = val_score
            best_gap = gap
            best_external_risk = external_risk

    print(
        f"\n✓ Selected SVM config: {best_config} "
        f"(train={best_train:.4f}, val={best_val:.4f}, gap={best_gap:.4f}, "
        f"ext_risk={best_external_risk:.4f})"
    )

    return best_model

def compute_lbp_histogram(gray):
    """Compute LBP texture histogram features on a 4x4 grid."""
    # Apply CLAHE for better local contrast enhancement
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
            cell = lbp[i:i+cell_h, j:j+cell_w]
            hist = np.histogram(cell, bins=32, range=(0, 256))[0]
            hist = hist.astype(np.float32) / (hist.sum() + 1e-6)
            features.extend(hist)

    return np.array(features, dtype=np.float32)

def extract_embeddings(split_type="train", dataset_type="train"):
    """Extract LBPH features directly from split face images"""
    
    embeddings = []
    labels = []
    failed_images = []
    
    # Get the split information
    split_path = Path(__file__).parent / "data_split" / split_type
    
    people_dirs = sorted([d for d in split_path.iterdir() if d.is_dir()])
    
    for person_dir in people_dirs:
        person_name = person_dir.name
        
        # Load images directly from split directory (already face-focused)
        person_split_dir = split_path / person_name
        images = list(person_split_dir.glob("*.jpeg")) + list(person_split_dir.glob("*.jpg")) + list(person_split_dir.glob("*.png"))
        
        for img_path in tqdm(images, desc=f"Extracting {dataset_type} features - {person_name}"):
            try:
                img = cv2.imread(str(img_path))
                if img is None:
                    failed_images.append(str(img_path))
                    continue
                
                # Convert to grayscale
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                
                # Extract features
                features = compute_lbp_histogram(gray)
                
                if features is not None and len(features) > 0:
                    embeddings.append(features)
                    labels.append(person_name)
                else:
                    failed_images.append(str(img_path))
            
            except Exception as e:
                print(f"Error processing {img_path}: {e}")
                failed_images.append(str(img_path))
    
    return np.array(embeddings), np.array(labels), failed_images


def extract_external_embeddings(external_dir_name="external_faces"):
    """Extract LBPH features from external/negative faces for open-set-aware model selection."""

    external_dir = Path(__file__).parent / external_dir_name
    if not external_dir.exists():
        return np.array([]), []

    embeddings = []
    failed_images = []

    image_paths = sorted(
        list(external_dir.glob("*.jpeg"))
        + list(external_dir.glob("*.jpg"))
        + list(external_dir.glob("*.png"))
    )

    for img_path in tqdm(image_paths, desc="Extracting external negative features"):
        try:
            img = cv2.imread(str(img_path))
            if img is None:
                failed_images.append(str(img_path))
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            features = compute_lbp_histogram(gray)
            if features is not None and len(features) > 0:
                embeddings.append(features)
            else:
                failed_images.append(str(img_path))
        except Exception:
            failed_images.append(str(img_path))

    return np.array(embeddings), failed_images

def train_face_recognition_model():
    """Train face recognition model using LBPH + SVM"""
    
    print("=" * 70)
    print("FACE RECOGNITION SYSTEM - MODEL TRAINING (LBPH + SVM)")
    print("=" * 70)
    
    models_path = Path(__file__).parent / "models"
    models_path.mkdir(exist_ok=True)
    
    # Extract train embeddings
    print("\n📊 Extracting train features (LBPH)...")
    train_embeddings, train_labels, train_failed = extract_embeddings(
        split_type="train", dataset_type="train"
    )
    
    # Extract validation embeddings
    print("\n📊 Extracting validation features (LBPH)...")
    val_embeddings, val_labels, val_failed = extract_embeddings(
        split_type="val", dataset_type="validation"
    )
    
    print(f"\n✓ Train embeddings: {train_embeddings.shape}")
    print(f"✓ Validation embeddings: {val_embeddings.shape}")
    print(f"⚠️  Failed images (train): {len(train_failed)}")
    print(f"⚠️  Failed images (val): {len(val_failed)}")

    # Extract external/negative embeddings for open-set-aware selection
    print("\n📊 Extracting external negative features (LBPH)...")
    external_embeddings, external_failed = extract_external_embeddings("external_faces")
    print(f"✓ External embeddings: {external_embeddings.shape}")
    print(f"⚠️  Failed external images: {len(external_failed)}")
    
    # Encode labels
    print("\n🏷️  Encoding labels...")
    label_encoder = LabelEncoder()
    train_labels_encoded = label_encoder.fit_transform(train_labels)
    val_labels_encoded = label_encoder.transform(val_labels)
    
    # Train SVM classifier with anti-overfitting model selection.
    print("\n🤖 Training SVM classifier...")
    classifier = select_best_svm(
        train_embeddings,
        train_labels_encoded,
        val_embeddings,
        val_labels_encoded,
        external_embeddings=external_embeddings,
    )

    # Train KNN classifier as a complementary model for hard class boundaries
    print("\n🤖 Training KNN classifier...")
    knn_classifier = Pipeline([
        ('scaler', StandardScaler()),
        ('knn', KNeighborsClassifier(n_neighbors=7, weights='distance', metric='euclidean'))
    ])
    knn_classifier.fit(train_embeddings, train_labels_encoded)

    # Train known-vs-external rejection detector when external faces are available.
    known_detector = None
    known_threshold = 0.55
    if external_embeddings is not None and len(external_embeddings) > 0:
        print("\n🛡️  Training known-vs-external detector...")

        known_train = np.vstack([train_embeddings, val_embeddings])
        known_labels_bin = np.ones(len(known_train), dtype=np.int32)

        external_labels_bin = np.zeros(len(external_embeddings), dtype=np.int32)
        rej_X = np.vstack([known_train, external_embeddings])
        rej_y = np.concatenate([known_labels_bin, external_labels_bin])

        known_detector = Pipeline([
            ('scaler', StandardScaler()),
            ('lr', LogisticRegression(C=1.0, class_weight='balanced', max_iter=1500, random_state=42))
        ])
        known_detector.fit(rej_X, rej_y)

        rej_probs = known_detector.predict_proba(rej_X)[:, 1]

        # Pick threshold that maximizes balanced accuracy between known and external.
        best_thr = known_threshold
        best_bal_acc = -1.0
        for thr in np.linspace(0.35, 0.80, 46):
            pred_known = (rej_probs >= thr).astype(np.int32)
            known_recall = np.mean(pred_known[rej_y == 1] == 1) if np.any(rej_y == 1) else 0.0
            external_reject = np.mean(pred_known[rej_y == 0] == 0) if np.any(rej_y == 0) else 0.0
            bal_acc = 0.5 * (known_recall + external_reject)
            if bal_acc > best_bal_acc:
                best_bal_acc = bal_acc
                best_thr = float(thr)

        known_threshold = max(0.55, best_thr)
        pred_known_final = (rej_probs >= known_threshold).astype(np.int32)
        kd_acc = accuracy_score(rej_y, pred_known_final)
        kd_prec = precision_score(rej_y, pred_known_final, zero_division=0)
        kd_rec = recall_score(rej_y, pred_known_final, zero_division=0)

        print(f"  Known-detector threshold: {known_threshold:.3f}")
        print(f"  Known-detector accuracy:  {kd_acc:.4f}")
        print(f"  Known-detector precision: {kd_prec:.4f}")
        print(f"  Known-detector recall:    {kd_rec:.4f}")
    
    # Evaluate on validation set
    train_score = classifier.score(train_embeddings, train_labels_encoded)
    val_score = classifier.score(val_embeddings, val_labels_encoded)
    knn_train_score = knn_classifier.score(train_embeddings, train_labels_encoded)
    knn_val_score = knn_classifier.score(val_embeddings, val_labels_encoded)
    
    print(f"\n📈 Training accuracy: {train_score:.4f}")
    print(f"📈 Validation accuracy: {val_score:.4f}")
    print(f"📈 KNN training accuracy: {knn_train_score:.4f}")
    print(f"📈 KNN validation accuracy: {knn_val_score:.4f}")
    
    # Save models
    print("\n💾 Saving models...")
    with open(models_path / "classifier.pkl", "wb") as f:
        pickle.dump(classifier, f)
    
    with open(models_path / "label_encoder.pkl", "wb") as f:
        pickle.dump(label_encoder, f)

    with open(models_path / "knn_classifier.pkl", "wb") as f:
        pickle.dump(knn_classifier, f)

    if known_detector is not None:
        with open(models_path / "known_detector.pkl", "wb") as f:
            pickle.dump(known_detector, f)
        with open(models_path / "known_detector_threshold.json", "w", encoding="utf-8") as f:
            json.dump({"known_threshold": float(known_threshold)}, f, indent=2)
    
    with open(models_path / "class_labels.pkl", "wb") as f:
        pickle.dump(label_encoder.classes_, f)
    
    print(f"\n✓ Models saved to: {models_path}")
    print(f"  - classifier.pkl")
    print(f"  - knn_classifier.pkl")
    if known_detector is not None:
        print(f"  - known_detector.pkl")
        print(f"  - known_detector_threshold.json")
    print(f"  - label_encoder.pkl")
    print(f"  - class_labels.pkl")
    
    print(f"\n{'=' * 70}")
    print("Classes learned:")
    for i, class_name in enumerate(label_encoder.classes_):
        print(f"  {i}: {class_name}")
    print("=" * 70)
    
    return classifier, label_encoder

if __name__ == "__main__":
    classifier, label_encoder = train_face_recognition_model()
