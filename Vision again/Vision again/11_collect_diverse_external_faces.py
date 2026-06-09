"""
Step 11: Build a Diverse External/Negative Faces Dataset

Builds a balanced external set from labeled Hugging Face datasets:
- Teenagers / 20s / 30s: FairFace age groups
- Women in hijab: hijab image dataset
- Men with beards: CelebA male + beard attributes

Usage:
  python 11_collect_diverse_external_faces.py --target-per-group 60 --output-dir external_faces
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import cv2
import numpy as np
from datasets import load_dataset


# Keep HF network timeouts sane even if shell env was previously set too low.
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")


def parse_args():
    parser = argparse.ArgumentParser(description="Collect diverse external faces from labeled datasets")
    parser.add_argument("--output-dir", type=str, default="external_faces", help="Output folder")
    parser.add_argument("--target-per-group", type=int, default=60, help="Target images per diversity group")
    parser.add_argument("--face-size", type=int, default=160, help="Saved face crop size")
    parser.add_argument("--min-face-size", type=int, default=60, help="Minimum detected face size")
    return parser.parse_args()


def largest_face(detector, gray, min_face):
    faces = detector.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(min_face, min_face),
    )
    if len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])


def crop_face(img, bbox, out_size):
    x, y, w, h = bbox
    pad = int(0.16 * max(w, h))
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(img.shape[1], x + w + pad)
    y2 = min(img.shape[0], y + h + pad)
    face = img[y1:y2, x1:x2]
    if face.size == 0:
        return None
    return cv2.resize(face, (out_size, out_size), interpolation=cv2.INTER_LINEAR)


def pil_or_ndarray_to_bgr(image_obj):
    if image_obj is None:
        return None

    if isinstance(image_obj, np.ndarray):
        img = image_obj
        if img.ndim == 2:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        if img.ndim == 3 and img.shape[2] == 3:
            return cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_RGB2BGR)
        return None

    arr = np.array(image_obj)
    if arr.ndim == 2:
        return cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_GRAY2BGR)
    if arr.ndim == 3 and arr.shape[2] == 3:
        return cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2BGR)
    if arr.ndim == 3 and arr.shape[2] == 4:
        return cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGBA2BGR)
    return None


def fairface_age_match(example, age_name):
    # FairFace age class names:
    # ['0-2','3-9','10-19','20-29','30-39','40-49','50-59','60-69','more than 70']
    idx = int(example.get("age", -1))
    mapping = {
        "teenagers": 2,
        "twenties": 3,
        "thirties": 4,
    }
    return idx == mapping.get(age_name, -999)


def celeba_beard_match(example):
    # CelebA attributes are usually -1/1 (1 means attribute present).
    male = int(example.get("Male", -1)) == 1
    beardish = (
        int(example.get("No_Beard", 1)) == -1
        or int(example.get("Goatee", -1)) == 1
        or int(example.get("Mustache", -1)) == 1
        or int(example.get("5_o_Clock_Shadow", -1)) == 1
        or int(example.get("Sideburns", -1)) == 1
    )
    return male and beardish


def load_dataset_with_retries(dataset_name, split, config_name=None, streaming=True, attempts=4):
    last_exc = None
    for i in range(attempts):
        try:
            if config_name is None:
                return load_dataset(dataset_name, split=split, streaming=streaming)
            return load_dataset(dataset_name, config_name, split=split, streaming=streaming)
        except Exception as exc:
            last_exc = exc
            if i < attempts - 1:
                time.sleep(2 * (i + 1))
    raise last_exc


def save_group_from_stream(stream, group_name, out_dir, detector, args, seen_hashes, matcher=None):
    saved = 0
    checked = 0
    existing_count = len(list(out_dir.glob(f"div_{group_name}_*.jpg")))
    target_needed = max(0, args.target_per_group - existing_count)
    if target_needed == 0:
        return 0, 0

    for ex in stream:
        if saved >= target_needed:
            break
        checked += 1

        try:
            if matcher is not None and not matcher(ex):
                continue

            img = pil_or_ndarray_to_bgr(ex.get("image"))
            if img is None or img.size == 0:
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            lf = largest_face(detector, gray, args.min_face_size)
            if lf is None:
                continue

            face = crop_face(img, lf, args.face_size)
            if face is None:
                continue

            ok, enc = cv2.imencode(".jpg", face, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            if not ok:
                continue
            raw = enc.tobytes()
            h = hashlib.sha1(raw).hexdigest()
            if h in seen_hashes:
                continue

            fname = f"div_{group_name}_{existing_count + saved + 1:04d}.jpg"
            path = out_dir / fname
            if cv2.imwrite(str(path), face):
                seen_hashes.add(h)
                saved += 1
        except Exception:
            continue

    return saved, checked


def main():
    args = parse_args()

    root = Path(__file__).parent
    out_dir = root / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)

    metadata = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "target_per_group": args.target_per_group,
        "groups": {},
        "saved_files": [],
    }

    # Keep existing files but avoid duplicates using content hash.
    seen_hashes = set()
    for p in out_dir.glob("*.jpg"):
        try:
            seen_hashes.add(hashlib.sha1(p.read_bytes()).hexdigest())
        except Exception:
            continue

    total_saved = 0

    print("\n[Source] FairFace age groups")
    for group_name in ("teenagers", "twenties", "thirties"):
        print(f"\n[Group] {group_name}")
        try:
            fair_stream = load_dataset_with_retries(
                dataset_name="HuggingFaceM4/FairFace",
                config_name="0.25",
                split="train",
                streaming=True,
            )
            saved_group, checked = save_group_from_stream(
                stream=fair_stream,
                group_name=group_name,
                out_dir=out_dir,
                detector=detector,
                args=args,
                seen_hashes=seen_hashes,
                matcher=lambda ex, g=group_name: fairface_age_match(ex, g),
            )
            total_saved += saved_group
            metadata["groups"][group_name] = {
                "saved": saved_group,
                "target": args.target_per_group,
                "checked": checked,
                "source": "HuggingFaceM4/FairFace",
                "status": "ok",
            }
            existing_count = len(list(out_dir.glob(f"div_{group_name}_*.jpg")))
            print(f"  saved +{saved_group}; total now {existing_count}/{args.target_per_group}")
        except Exception as exc:
            metadata["groups"][group_name] = {
                "saved": 0,
                "target": args.target_per_group,
                "checked": 0,
                "source": "HuggingFaceM4/FairFace",
                "status": f"error: {exc}",
            }
            print(f"  failed: {exc}")

    print("\n[Source] Hijab dataset")
    try:
        hijab_stream = load_dataset_with_retries(
            dataset_name="herutriana44/hijab_dataset",
            split="train",
            streaming=True,
        )
        saved_group, checked = save_group_from_stream(
            stream=hijab_stream,
            group_name="women_hijab",
            out_dir=out_dir,
            detector=detector,
            args=args,
            seen_hashes=seen_hashes,
            matcher=None,
        )
        total_saved += saved_group
        metadata["groups"]["women_hijab"] = {
            "saved": saved_group,
            "target": args.target_per_group,
            "checked": checked,
            "source": "herutriana44/hijab_dataset",
            "status": "ok",
        }
        existing_count = len(list(out_dir.glob("div_women_hijab_*.jpg")))
        print(f"  saved +{saved_group}; total now {existing_count}/{args.target_per_group}")
    except Exception as exc:
        metadata["groups"]["women_hijab"] = {
            "saved": 0,
            "target": args.target_per_group,
            "checked": 0,
            "source": "herutriana44/hijab_dataset",
            "status": f"error: {exc}",
        }
        print(f"  failed: {exc}")

    print("\n[Source] CelebA beard attributes")
    try:
        celeba_stream = load_dataset_with_retries(
            dataset_name="huggan/CelebA-faces-with-attributes",
            split="train",
            streaming=True,
        )
        saved_group, checked = save_group_from_stream(
            stream=celeba_stream,
            group_name="men_beard",
            out_dir=out_dir,
            detector=detector,
            args=args,
            seen_hashes=seen_hashes,
            matcher=celeba_beard_match,
        )
        total_saved += saved_group
        metadata["groups"]["men_beard"] = {
            "saved": saved_group,
            "target": args.target_per_group,
            "checked": checked,
            "source": "huggan/CelebA-faces-with-attributes",
            "status": "ok",
        }
        existing_count = len(list(out_dir.glob("div_men_beard_*.jpg")))
        print(f"  saved +{saved_group}; total now {existing_count}/{args.target_per_group}")
    except Exception as exc:
        metadata["groups"]["men_beard"] = {
            "saved": 0,
            "target": args.target_per_group,
            "checked": 0,
            "source": "huggan/CelebA-faces-with-attributes",
            "status": f"error: {exc}",
        }
        print(f"  failed: {exc}")

    metadata["total_saved_new"] = total_saved
    metadata["total_files_in_output"] = len(list(out_dir.glob("*.jpg")))

    meta_path = out_dir / "diverse_collection_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("\n" + "=" * 70)
    print(f"New diverse faces saved: {total_saved}")
    print(f"Output folder: {out_dir}")
    print(f"Metadata: {meta_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
