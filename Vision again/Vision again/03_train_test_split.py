"""
Face Recognition System - Step 3: Train/Test/Validation Split
Split processed images into train, validation, and test sets
"""

import os
import shutil
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from tqdm import tqdm

def create_train_val_test_split(train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, random_state=42):
    """
    Split processed images into train, validation, and test sets
    
    Args:
        train_ratio: Proportion for training
        val_ratio: Proportion for validation
        test_ratio: Proportion for testing
        random_state: Random seed for reproducibility
    """
    
    print("=" * 70)
    print("FACE RECOGNITION SYSTEM - TRAIN/VAL/TEST SPLIT")
    print("=" * 70)
    
    processed_path = Path(__file__).parent / "processed_images"
    split_path = Path(__file__).parent / "data_split"
    
    # Create directories
    for split_type in ["train", "val", "test"]:
        (split_path / split_type).mkdir(parents=True, exist_ok=True)
    
    np.random.seed(random_state)
    
    split_stats = {
        "train": {"total": 0, "people": {}},
        "val": {"total": 0, "people": {}},
        "test": {"total": 0, "people": {}},
    }
    
    for person_dir in sorted(processed_path.iterdir()):
        if not person_dir.is_dir():
            continue
        
        person_name = person_dir.name
        
        # Create person directories in each split
        for split_type in ["train", "val", "test"]:
            (split_path / split_type / person_name).mkdir(parents=True, exist_ok=True)
            split_stats[split_type]["people"][person_name] = 0
        
        # Get all images for this person
        images = list(person_dir.glob("*.jpeg")) + list(person_dir.glob("*.jpg")) + list(person_dir.glob("*.png"))
        images = [img.name for img in images]
        
        print(f"\n📁 {person_name}: {len(images)} images")
        
        # First split: separate test set
        train_val, test = train_test_split(
            images,
            test_size=test_ratio,
            random_state=random_state
        )
        
        # Second split: separate train and validation
        train, val = train_test_split(
            train_val,
            test_size=val_ratio / (1 - test_ratio),
            random_state=random_state
        )
        
        # Copy files
        for img_name in train:
            src = person_dir / img_name
            dst = split_path / "train" / person_name / img_name
            shutil.copy2(src, dst)
            split_stats["train"]["total"] += 1
            split_stats["train"]["people"][person_name] += 1
        
        for img_name in val:
            src = person_dir / img_name
            dst = split_path / "val" / person_name / img_name
            shutil.copy2(src, dst)
            split_stats["val"]["total"] += 1
            split_stats["val"]["people"][person_name] += 1
        
        for img_name in test:
            src = person_dir / img_name
            dst = split_path / "test" / person_name / img_name
            shutil.copy2(src, dst)
            split_stats["test"]["total"] += 1
            split_stats["test"]["people"][person_name] += 1
        
        print(f"  Train: {len(train)} | Val: {len(val)} | Test: {len(test)}")
    
    # Print summary
    print(f"\n{'=' * 70}")
    print("SPLIT SUMMARY")
    print(f"{'=' * 70}")
    print(f"\nTrain set ({train_ratio*100:.0f}%): {split_stats['train']['total']} images")
    for person, count in split_stats['train']['people'].items():
        print(f"  {person}: {count}")
    
    print(f"\nValidation set ({val_ratio*100:.0f}%): {split_stats['val']['total']} images")
    for person, count in split_stats['val']['people'].items():
        print(f"  {person}: {count}")
    
    print(f"\nTest set ({test_ratio*100:.0f}%): {split_stats['test']['total']} images")
    for person, count in split_stats['test']['people'].items():
        print(f"  {person}: {count}")
    
    print(f"\n✓ Data split saved to: {split_path}")
    print("=" * 70)
    
    return split_stats

if __name__ == "__main__":
    stats = create_train_val_test_split()
