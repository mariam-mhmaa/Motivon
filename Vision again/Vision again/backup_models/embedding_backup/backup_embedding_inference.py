"""
Inference adapter for the isolated embedding backup model.

This is not used by the active live camera script unless explicitly imported later.
"""

import argparse
import pickle
from pathlib import Path

import cv2
import numpy as np


BACKUP_ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = BACKUP_ROOT / "artifacts" / "embedding_backup_model.pkl"


def l2_normalize(vector):
    vector = np.asarray(vector, dtype=np.float32)
    return vector / (np.linalg.norm(vector) + 1e-8)


class BackupEmbeddingRecognizer:
    def __init__(self, model_path=DEFAULT_MODEL_PATH):
        self.model_path = Path(model_path)
        with open(self.model_path, "rb") as f:
            artifact = pickle.load(f)

        self.classifier = artifact["classifier"]
        self.label_encoder = artifact["label_encoder"]
        self.prototypes = artifact["prototypes"]
        self.confidence_threshold = float(artifact["confidence_threshold"])
        self.prototype_threshold = float(artifact["prototype_threshold"])

        from insightface.app import FaceAnalysis

        self.face_app = FaceAnalysis(
            name="buffalo_l",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self.face_app.prepare(ctx_id=0, det_size=(640, 640))

    def _extract_largest_face(self, image_bgr):
        faces = self.face_app.get(image_bgr)
        if not faces:
            return None, None

        face = max(faces, key=lambda f: float((f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])))
        embedding = getattr(face, "normed_embedding", None)
        if embedding is None:
            embedding = l2_normalize(face.embedding)
        else:
            embedding = l2_normalize(embedding)
        bbox = [int(round(v)) for v in face.bbox]
        return embedding.reshape(1, -1), bbox

    def recognize_bgr(self, image_bgr):
        embedding, bbox = self._extract_largest_face(image_bgr)
        if embedding is None:
            return {
                "person_name": None,
                "confidence": 0.0,
                "bbox": None,
                "is_unknown": True,
                "prototype_score": 0.0,
            }

        probs = self.classifier.predict_proba(embedding)[0]
        class_index = int(np.argmax(probs))
        person_name = str(self.label_encoder.classes_[class_index])
        confidence = float(probs[class_index])

        prototype = self.prototypes.get(person_name)
        prototype_score = float(embedding[0] @ prototype) if prototype is not None else 0.0
        is_unknown = (
            confidence < self.confidence_threshold
            or prototype_score < self.prototype_threshold
        )

        if is_unknown:
            person_name = "UNKNOWN"

        return {
            "person_name": person_name,
            "confidence": confidence,
            "bbox": bbox,
            "is_unknown": bool(is_unknown),
            "prototype_score": prototype_score,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--image", required=True)
    args = parser.parse_args()

    image = cv2.imread(args.image)
    if image is None:
        raise FileNotFoundError(args.image)

    recognizer = BackupEmbeddingRecognizer(args.model)
    print(recognizer.recognize_bgr(image))


if __name__ == "__main__":
    main()
