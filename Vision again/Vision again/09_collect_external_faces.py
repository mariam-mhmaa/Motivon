"""
Step 9: Collect External/Negative Faces for Open-Set Calibration
Creates a dataset of faces NOT belonging to the 4 target identities.

Usage:
  python 09_collect_external_faces.py --target-count 150 --camera-id 0
"""

import argparse
import json
import time
from pathlib import Path

import cv2


def parse_args():
    parser = argparse.ArgumentParser(description="Collect external face dataset from webcam")
    parser.add_argument("--camera-id", type=int, default=0, help="Webcam index")
    parser.add_argument("--target-count", type=int, default=120, help="How many face crops to save")
    parser.add_argument("--output-dir", type=str, default="external_faces", help="Output folder")
    parser.add_argument("--sample-every", type=int, default=4, help="Save at most one crop every N frames")
    parser.add_argument("--min-face-size", type=int, default=70, help="Minimum face size in pixels")
    return parser.parse_args()


def largest_face(faces):
    if len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])


def main():
    args = parse_args()

    root = Path(__file__).parent
    out_dir = root / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)

    cap = cv2.VideoCapture(args.camera_id)
    if not cap.isOpened():
        print("Error: could not open camera")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

    print("=" * 70)
    print("EXTERNAL FACE DATASET COLLECTION")
    print("=" * 70)
    print("Collect faces of people NOT in {Ainour, Mariam, Nour, Zeina}")
    print("Controls:")
    print("  SPACE - pause/resume auto-capture")
    print("  S     - force-save current largest face")
    print("  Q     - quit")
    print("-" * 70)

    saved = 0
    frame_idx = 0
    paused = False
    start = time.time()

    metadata = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "target_count": args.target_count,
        "camera_id": args.camera_id,
        "sample_every": args.sample_every,
        "min_face_size": args.min_face_size,
        "saved_images": [],
    }

    def save_face(frame, bbox, reason):
        nonlocal saved
        x, y, w, h = bbox
        pad = int(0.12 * max(w, h))
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(frame.shape[1], x + w + pad)
        y2 = min(frame.shape[0], y + h + pad)

        face = frame[y1:y2, x1:x2]
        if face.size == 0:
            return False

        face = cv2.resize(face, (160, 160), interpolation=cv2.INTER_LINEAR)
        fname = f"ext_{saved + 1:04d}.jpg"
        fpath = out_dir / fname
        cv2.imwrite(str(fpath), face)

        saved += 1
        metadata["saved_images"].append(
            {
                "file": fname,
                "bbox": [int(x), int(y), int(w), int(h)],
                "saved_reason": reason,
                "time": time.strftime("%H:%M:%S"),
            }
        )
        return True

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Warning: frame read failed")
                break

            frame_idx += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(args.min_face_size, args.min_face_size),
            )

            lf = largest_face(faces)

            if lf is not None:
                x, y, w, h = lf
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 180, 255), 2)

                if (not paused) and (frame_idx % max(1, args.sample_every) == 0) and saved < args.target_count:
                    save_face(frame, lf, reason="auto")

            elapsed = time.time() - start
            fps = frame_idx / elapsed if elapsed > 0 else 0.0

            info = [
                f"Saved: {saved}/{args.target_count}",
                f"Paused: {'YES' if paused else 'NO'}",
                f"FPS: {fps:.1f}",
                "SPACE pause/resume | S save now | Q quit",
            ]
            y0 = 28
            for line in info:
                cv2.putText(frame, line, (12, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 3)
                cv2.putText(frame, line, (12, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 1)
                y0 += 26

            cv2.imshow("Collect External Faces", frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            if key == ord(" "):
                paused = not paused
            if key == ord("s") and lf is not None and saved < args.target_count:
                save_face(frame, lf, reason="manual")

            if saved >= args.target_count:
                print(f"Reached target count: {args.target_count}")
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()

        metadata["final_saved_count"] = saved
        metadata["duration_seconds"] = round(time.time() - start, 2)

        meta_path = out_dir / "collection_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        print("\n" + "=" * 70)
        print(f"Saved external faces: {saved}")
        print(f"Folder: {out_dir}")
        print(f"Metadata: {meta_path}")
        print("=" * 70)


if __name__ == "__main__":
    main()
