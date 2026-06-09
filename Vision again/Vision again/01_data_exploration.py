"""
Face Recognition System - Step 1: Data Exploration and Statistics
Explore dataset, check image quality, and prepare for preprocessing
"""

import os
import cv2
import numpy as np
from pathlib import Path
from collections import defaultdict
import json

def explore_dataset():
    """Explore the dataset structure and gather statistics"""
    
    dataset_path = Path(__file__).parent / "raw_images"
    
    stats = {
        "total_images": 0,
        "people": {},
        "invalid_images": [],
        "image_sizes": defaultdict(list)
    }
    
    print("=" * 70)
    print("FACE RECOGNITION SYSTEM - DATA EXPLORATION")
    print("=" * 70)
    
    for person_dir in sorted(dataset_path.iterdir()):
        if person_dir.is_dir():
            person_name = person_dir.name
            images = list(person_dir.glob("*.jpeg")) + list(person_dir.glob("*.jpg")) + list(person_dir.glob("*.png"))
            
            valid_images = 0
            valid_sizes = []
            
            for img_path in images:
                try:
                    img = cv2.imread(str(img_path))
                    if img is not None:
                        valid_images += 1
                        h, w = img.shape[:2]
                        valid_sizes.append((w, h))
                    else:
                        stats["invalid_images"].append(str(img_path))
                except Exception as e:
                    stats["invalid_images"].append(str(img_path))
            
            stats["people"][person_name] = {
                "total": len(images),
                "valid": valid_images,
                "invalid": len(images) - valid_images,
                "avg_size": tuple(np.mean(valid_sizes, axis=0).astype(int)) if valid_sizes else (0, 0)
            }
            stats["total_images"] += valid_images
            
            print(f"\n📁 {person_name}:")
            print(f"   Total images: {len(images)}")
            print(f"   Valid images: {valid_images}")
            print(f"   Invalid/Corrupt: {len(images) - valid_images}")
            print(f"   Average size: {stats['people'][person_name]['avg_size']}")
    
    print(f"\n{'=' * 70}")
    print(f"DATASET SUMMARY")
    print(f"{'=' * 70}")
    print(f"Total valid images: {stats['total_images']}")
    print(f"Number of people: {len(stats['people'])}")
    print(f"Invalid/Corrupt images: {len(stats['invalid_images'])}")
    
    print(f"\nClass distribution:")
    for person_name, person_stats in stats["people"].items():
        percentage = (person_stats['valid'] / stats['total_images'] * 100) if stats['total_images'] > 0 else 0
        print(f"  {person_name}: {person_stats['valid']} images ({percentage:.1f}%)")
    
    if stats['invalid_images']:
        print(f"\n⚠️  Invalid images to remove:")
        for img in stats['invalid_images'][:5]:
            print(f"  - {img}")
        if len(stats['invalid_images']) > 5:
            print(f"  ... and {len(stats['invalid_images']) - 5} more")
    
    # Save stats
    with open("dataset_stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    
    print(f"\n✓ Dataset stats saved to 'dataset_stats.json'")
    print("=" * 70)
    
    return stats

if __name__ == "__main__":
    stats = explore_dataset()
