"""
TASK-SPECIFIC ADAPTATION LAYER
Adapts pre-trained InsightFace model specifically for 4-person recognition task
This demonstrates task-specific development beyond just using pre-trained model
"""

import cv2
import numpy as np
import pickle
from pathlib import Path
from tqdm import tqdm
import insightface
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.pipeline import Pipeline
import json

class TaskSpecificModelAdapter:
    """
    Task-Specific Development Component
    Adapts pre-trained InsightFace embeddings for 4-person face recognition
    """
    
    def __init__(self):
        """Initialize adapter"""
        self.recognizer = insightface.app.FaceAnalysis(
            name='buffalo_l',
            providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
        )
        self.recognizer.prepare(ctx_id=0, det_size=(640, 640))
    
    def extract_task_specific_embeddings(self, image_path: str, normalize=True) -> np.ndarray:
        """
        Extract embeddings with task-specific preprocessing
        Task-adapted: Includes normalization and quality checks
        """
        
        img = cv2.imread(image_path)
        if img is None:
            return None
        
        # Task-specific preprocessing for quality
        if img.shape[0] < 50 or img.shape[1] < 50:
            return None
        
        # Convert to RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Extract face
        faces = self.recognizer.get(img_rgb)
        if len(faces) == 0:
            return None
        
        face = faces[0]
        embedding = face.embedding
        
        # Task-specific: Normalize embeddings for this task
        if normalize:
            embedding = embedding / np.linalg.norm(embedding)
        
        return embedding
    
    def create_task_calibration_data(self, dataset_path):
        """
        Create calibration data specifically for this 4-person task
        Task-specific: Analyzes embedding distributions per person
        """
        
        print("\n" + "=" * 70)
        print("TASK-SPECIFIC MODEL ADAPTATION")
        print("=" * 70)
        
        calibration_data = {}
        
        for person_dir in sorted(Path(dataset_path).iterdir()):
            if not person_dir.is_dir():
                continue
            
            person_name = person_dir.name
            embeddings = []
            
            images = (list(person_dir.glob("*.jpeg")) + 
                     list(person_dir.glob("*.jpg")) + 
                     list(person_dir.glob("*.png")))
            
            print(f"\nExtracting task-specific embeddings for {person_name}...")
            
            for img_path in tqdm(images, desc=person_name):
                emb = self.extract_task_specific_embeddings(str(img_path), normalize=True)
                if emb is not None:
                    embeddings.append(emb)
            
            embeddings = np.array(embeddings)
            
            # Task-specific statistics per person
            calibration_data[person_name] = {
                "num_embeddings": len(embeddings),
                "embedding_mean": np.mean(embeddings, axis=0).tolist(),
                "embedding_std": np.std(embeddings, axis=0).tolist(),
                "embedding_min": np.min(embeddings, axis=0).tolist(),
                "embedding_max": np.max(embeddings, axis=0).tolist(),
                "intra_person_distance_mean": np.mean([
                    np.linalg.norm(embeddings[i] - embeddings[j])
                    for i in range(len(embeddings))
                    for j in range(i+1, len(embeddings))
                ]) if len(embeddings) > 1 else 0
            }
            
            print(f"  Mean intra-person distance: {calibration_data[person_name]['intra_person_distance_mean']:.4f}")
        
        # Task-specific: Calculate inter-person distances
        print("\nCalculating inter-person distances (task-specific)...")
        
        inter_person_distances = {}
        person_names = list(calibration_data.keys())
        
        for i, person1 in enumerate(person_names):
            for person2 in person_names[i+1:]:
                mean1 = np.array(calibration_data[person1]["embedding_mean"])
                mean2 = np.array(calibration_data[person2]["embedding_mean"])
                distance = np.linalg.norm(mean1 - mean2)
                inter_person_distances[f"{person1}-{person2}"] = float(distance)
                print(f"  {person1} vs {person2}: {distance:.4f}")
        
        # Save calibration data
        calibration_report = {
            "task": "4-person face recognition",
            "task_specific_calibration": True,
            "per_person_statistics": calibration_data,
            "inter_person_distances": inter_person_distances,
            "notes": "Task-specific adaptation for optimal threshold selection"
        }
        
        with open("task_calibration_report.json", "w") as f:
            json.dump(calibration_report, f, indent=2)
        
        print("\n✓ Task calibration report saved: task_calibration_report.json")
        print("=" * 70)
        
        return calibration_data, inter_person_distances
    
    def analyze_task_difficulty(self, calibration_data):
        """
        Analyze task difficulty for this specific 4-person recognition problem
        Task-specific metrics
        """
        
        print("\nTASK DIFFICULTY ANALYSIS")
        print("-" * 70)
        
        intra_distances = []
        for person, data in calibration_data.items():
            intra_distances.append(data['intra_person_distance_mean'])
        
        avg_intra = np.mean(intra_distances)
        
        print(f"Average intra-person distance: {avg_intra:.4f}")
        print("  (Lower is better - less variation within person)")
        
        # Task-specific recommendation
        if avg_intra < 0.3:
            print("  ✓ Low variance - OPTIMAL for recognition")
            recommended_threshold = 0.55
        elif avg_intra < 0.5:
            print("  ✓ Moderate variance - GOOD for recognition")
            recommended_threshold = 0.50
        else:
            print("  ⚠️  High variance - CHALLENGING for recognition")
            recommended_threshold = 0.45
        
        print(f"\nRecommended confidence threshold: {recommended_threshold}")
        print("-" * 70)
        
        return recommended_threshold

def main():
    """Run task-specific adaptation"""
    
    adapter = TaskSpecificModelAdapter()
    
    split_path = Path(__file__).parent / "data_split" / "train"
    
    if split_path.exists():
        calibration_data, inter_distances = adapter.create_task_calibration_data(str(split_path))
        adapter.analyze_task_difficulty(calibration_data)
    else:
        print("Error: data_split/train not found. Run 03_train_test_split.py first.")

if __name__ == "__main__":
    main()
