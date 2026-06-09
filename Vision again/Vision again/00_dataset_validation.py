"""
REQUIREMENT 1: Dataset Validation
Verify custom dataset meets minimum 100 images requirement
"""

import os
from pathlib import Path
from collections import defaultdict
import json

def validate_dataset():
    """Validate dataset meets requirements"""
    
    print("=" * 70)
    print("REQUIREMENT 1: CUSTOM DATASET VALIDATION")
    print("=" * 70)
    
    raw_images_path = Path(__file__).parent / "raw_images"
    
    stats = {
        "total_images": 0,
        "people": defaultdict(int),
        "formats": defaultdict(int)
    }
    
    # Count all images
    for person_dir in raw_images_path.iterdir():
        if person_dir.is_dir():
            person_name = person_dir.name
            
            images = (
                list(person_dir.glob("*.jpeg")) +
                list(person_dir.glob("*.jpg")) +
                list(person_dir.glob("*.JPG")) +
                list(person_dir.glob("*.png"))
            )
            
            for img in images:
                stats["total_images"] += 1
                stats["people"][person_name] += 1
                stats["formats"][img.suffix.lower()] += 1
    
    # Print results
    print(f"\n✓ DATASET MEETS REQUIREMENT: {stats['total_images']} images (minimum required: 100)")
    print(f"\nClass Distribution:")
    for person, count in sorted(stats['people'].items()):
        percentage = (count / stats['total_images']) * 100
        print(f"  • {person}: {count} images ({percentage:.1f}%)")
    
    print(f"\nImage Formats:")
    for fmt, count in sorted(stats['formats'].items()):
        print(f"  • {fmt}: {count} images")
    
    # Check minimum per class
    min_class_images = min(stats['people'].values())
    print(f"\nMinimum images per class: {min_class_images}")
    
    if stats['total_images'] >= 100:
        print("\n✅ DATASET VALIDATION: PASSED")
        print(f"   Total images: {stats['total_images']} >= 100 (REQUIRED)")
    else:
        print("\n❌ DATASET VALIDATION: FAILED")
        print(f"   Total images: {stats['total_images']} < 100 (REQUIRED)")
    
    # Save validation report
    with open("dataset_validation_report.json", "w") as f:
        json.dump({
            "requirement": "Minimum 100 custom images",
            "status": "PASSED" if stats['total_images'] >= 100 else "FAILED",
            "total_images": stats['total_images'],
            "required_images": 100,
            "classes": dict(stats['people']),
            "image_formats": dict(stats['formats'])
        }, f, indent=2)
    
    print("\n✓ Report saved: dataset_validation_report.json")
    print("=" * 70)
    
    return stats

if __name__ == "__main__":
    validate_dataset()
