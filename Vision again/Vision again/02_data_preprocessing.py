"""
Face Recognition System - Step 2: Data Preprocessing
Clean data, detect faces, and prepare clean dataset for training
"""

import os
import cv2
import numpy as np
from pathlib import Path
from tqdm import tqdm
import shutil
import insightface

def get_face_detector():
    """Initialize face detector"""
    detector = insightface.app.FaceAnalysis(
        name='buffalo_l',
        providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
    )
    detector.prepare(ctx_id=0, det_size=(640, 640))
    return detector

def preprocess_image(image, target_size=(224, 224)):
    """Preprocess image for face recognition"""
    # Normalize pixel values
    image = image.astype(np.float32) / 255.0
    # Resize
    image = cv2.resize(image, target_size)
    return image

def process_dataset():
    """Process entire dataset: clean, detect faces, organize"""
    
    print("=" * 70)
    print("FACE RECOGNITION SYSTEM - DATA PREPROCESSING")
    print("=" * 70)
    
    raw_images_path = Path(__file__).parent / "raw_images"
    processed_path = Path(__file__).parent / "processed_images"
    invalid_path = Path(__file__).parent / "invalid_images"
    
    # Create output directories
    processed_path.mkdir(exist_ok=True)
    invalid_path.mkdir(exist_ok=True)
    
    # Initialize face detector
    print("\n🔍 Initializing face detector...")
    detector = get_face_detector()
    
    stats = {
        "total_processed": 0,
        "multiple_faces": 0,
        "no_faces": 0,
        "low_quality": 0,
        "valid_images": 0,
        "people": {}
    }
    
    for person_dir in sorted(raw_images_path.iterdir()):
        if not person_dir.is_dir():
            continue
            
        person_name = person_dir.name
        person_output = processed_path / person_name
        person_invalid = invalid_path / person_name
        
        person_output.mkdir(exist_ok=True)
        person_invalid.mkdir(exist_ok=True)
        
        stats["people"][person_name] = {
            "processed": 0,
            "valid": 0,
            "multiple_faces": 0,
            "no_faces": 0,
            "corrupted": 0
        }
        
        images = list(person_dir.glob("*.jpeg")) + list(person_dir.glob("*.jpg")) + list(person_dir.glob("*.png"))
        
        print(f"\n📁 Processing {person_name} ({len(images)} images)...")
        
        for img_path in tqdm(images, desc=person_name):
            try:
                # Read image
                img = cv2.imread(str(img_path))
                if img is None:
                    stats["people"][person_name]["corrupted"] += 1
                    shutil.copy(img_path, person_invalid / img_path.name)
                    continue
                
                # Detect faces
                faces = detector.get(img)
                
                if len(faces) == 0:
                    stats["no_faces"] += 1
                    stats["people"][person_name]["no_faces"] += 1
                    shutil.copy(img_path, person_invalid / img_path.name)
                    continue
                
                if len(faces) > 1:
                    stats["multiple_faces"] += 1
                    stats["people"][person_name]["multiple_faces"] += 1
                    shutil.copy(img_path, person_invalid / img_path.name)
                    continue
                
                # Extract face bbox
                face = faces[0]
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = bbox
                
                # Add padding
                pad = 20
                x1 = max(0, x1 - pad)
                y1 = max(0, y1 - pad)
                x2 = min(img.shape[1], x2 + pad)
                y2 = min(img.shape[0], y2 + pad)
                
                # Crop face
                face_img = img[y1:y2, x1:x2]
                
                if face_img.shape[0] < 50 or face_img.shape[1] < 50:
                    stats["low_quality"] += 1
                    stats["people"][person_name]["corrupted"] += 1
                    shutil.copy(img_path, person_invalid / img_path.name)
                    continue
                
                # Standardize size
                face_img = cv2.resize(face_img, (224, 224))
                
                # Save processed image
                output_path = person_output / img_path.name
                cv2.imwrite(str(output_path), face_img)
                
                stats["valid_images"] += 1
                stats["people"][person_name]["valid"] += 1
                stats["total_processed"] += 1
                
            except Exception as e:
                print(f"Error processing {img_path}: {e}")
                stats["people"][person_name]["corrupted"] += 1
                try:
                    shutil.copy(img_path, person_invalid / img_path.name)
                except:
                    pass
    
    # Print summary
    print(f"\n{'=' * 70}")
    print("PREPROCESSING SUMMARY")
    print(f"{'=' * 70}")
    print(f"✓ Valid images: {stats['valid_images']}")
    print(f"⚠️  Multiple faces: {stats['multiple_faces']}")
    print(f"⚠️  No faces detected: {stats['no_faces']}")
    print(f"⚠️  Low quality: {stats['low_quality']}")
    
    print(f"\nPer-person breakdown:")
    for person_name, person_stats in stats["people"].items():
        print(f"  {person_name}: {person_stats['valid']} valid images")
    
    print(f"\n✓ Processed images saved to: {processed_path}")
    print(f"✓ Invalid images moved to: {invalid_path}")
    print("=" * 70)
    
    return stats

if __name__ == "__main__":
    stats = process_dataset()
