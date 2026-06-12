"""
Face Recognition System - Step 5: Test Model
Evaluate model on test set and generate detailed metrics
"""

import os
import cv2
import numpy as np
import pickle
from pathlib import Path
from tqdm import tqdm
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns

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

def extract_test_embeddings(dataset_path):
    """Extract features from test dataset using LBPH"""
    
    embeddings = []
    labels = []
    failed_images = []
    
    # Get the split information
    split_path = Path(__file__).parent / "data_split" / "test"
    
    people_dirs = sorted([d for d in split_path.iterdir() if d.is_dir()])
    
    for person_dir in people_dirs:
        person_name = person_dir.name
        
        # Load images directly from test split directory (already face-focused)
        person_split_dir = split_path / person_name
        images = list(person_split_dir.glob("*.jpeg")) + list(person_split_dir.glob("*.jpg")) + list(person_split_dir.glob("*.png"))
        
        for img_path in tqdm(images, desc=f"Processing {person_name}"):
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
                print(f"Error: {img_path}: {e}")
                failed_images.append(str(img_path))
    
    return np.array(embeddings), np.array(labels), failed_images

def test_model():
    """Test the trained model on test set"""
    
    print("=" * 70)
    print("FACE RECOGNITION SYSTEM - MODEL TESTING")
    print("=" * 70)
    
    models_path = Path(__file__).parent / "models"
    
    # Load models
    print("\n📦 Loading trained models...")
    with open(models_path / "classifier.pkl", "rb") as f:
        classifier = pickle.load(f)
    
    with open(models_path / "label_encoder.pkl", "rb") as f:
        label_encoder = pickle.load(f)
    
    # Extract test features
    print("\n📊 Extracting test features (LBPH)...")
    test_embeddings, test_labels, failed = extract_test_embeddings(Path(__file__).parent / "data_split" / "test")
    
    print(f"✓ Test embeddings: {test_embeddings.shape}")
    print(f"⚠️  Failed images: {len(failed)}")
    
    # Make predictions
    print("\n🔮 Making predictions...")
    test_labels_encoded = label_encoder.transform(test_labels)
    predictions = classifier.predict(test_embeddings)
    probabilities = classifier.predict_proba(test_embeddings)
    
    # Calculate metrics
    print("\n📈 PERFORMANCE METRICS")
    print("-" * 70)
    
    accuracy = accuracy_score(test_labels_encoded, predictions)
    precision = precision_score(test_labels_encoded, predictions, average='weighted', zero_division=0)
    recall = recall_score(test_labels_encoded, predictions, average='weighted', zero_division=0)
    f1 = f1_score(test_labels_encoded, predictions, average='weighted', zero_division=0)
    
    print(f"Accuracy:  {accuracy:.4f} ({accuracy*100:.2f}%)")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1-Score:  {f1:.4f}")
    
    # Per-class metrics
    print("\n📊 PER-CLASS METRICS")
    print("-" * 70)
    
    for i, class_name in enumerate(label_encoder.classes_):
        class_mask = test_labels_encoded == i
        if np.sum(class_mask) > 0:
            class_accuracy = accuracy_score(
                test_labels_encoded[class_mask],
                predictions[class_mask]
            )
            class_precision = precision_score(
                test_labels_encoded[class_mask],
                predictions[class_mask],
                average='weighted',
                zero_division=0
            )
            class_recall = recall_score(
                test_labels_encoded[class_mask],
                predictions[class_mask],
                average='weighted',
                zero_division=0
            )
            print(f"{class_name}:")
            print(f"  Accuracy:  {class_accuracy:.4f}")
            print(f"  Precision: {class_precision:.4f}")
            print(f"  Recall:    {class_recall:.4f}")
    
    # Confusion Matrix
    print("\n📊 CONFUSION MATRIX")
    print("-" * 70)
    cm = confusion_matrix(test_labels_encoded, predictions)
    print(cm)
    
    # Plot confusion matrix
    plt.figure(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=label_encoder.classes_,
                yticklabels=label_encoder.classes_)
    plt.title('Confusion Matrix - Test Set')
    plt.ylabel('True Label')
    plt.xlabel('Predicted Label')
    plt.tight_layout()
    plt.savefig('confusion_matrix_test.png', dpi=150, bbox_inches='tight')
    print("\n✓ Confusion matrix saved as 'confusion_matrix_test.png'")
    
    # Get confidence statistics
    max_probs = np.max(probabilities, axis=1)
    print("\n🎯 CONFIDENCE STATISTICS")
    print("-" * 70)
    print(f"Average confidence: {np.mean(max_probs):.4f}")
    print(f"Min confidence: {np.min(max_probs):.4f}")
    print(f"Max confidence: {np.max(max_probs):.4f}")
    print(f"Std confidence: {np.std(max_probs):.4f}")
    
    print(f"\n{'=' * 70}")
    print("✓ Test complete!")
    print("=" * 70)
    
    return accuracy, precision, recall, f1

if __name__ == "__main__":
    test_model()
