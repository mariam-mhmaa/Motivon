"""Windows OpenCV preview for the ROS vision debug image stream."""

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import cv2
import numpy as np


BRIDGE_URL = os.environ.get("MOTIVON_BRIDGE_URL", "http://localhost:8000").rstrip("/")
IMAGE_URL = f"{BRIDGE_URL}/api/vision/debug-image.jpg"
STATUS_URL = f"{BRIDGE_URL}/api/status"
WINDOW_NAME = "Face Recognition System - Pi RAW TCP Camera"
PLACEHOLDER_SIZE = (720, 720, 3)


def fetch_image():
    url = f"{IMAGE_URL}?t={time.time():.3f}"
    with urlopen(url, timeout=1.0) as response:
        data = response.read()
    image_array = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(image_array, cv2.IMREAD_COLOR)


def fetch_status():
    with urlopen(STATUS_URL, timeout=1.0) as response:
        return json.loads(response.read().decode("utf-8"))


def make_waiting_frame(message, status=None):
    frame = np.zeros(PLACEHOLDER_SIZE, dtype=np.uint8)
    frame[:] = (10, 18, 28)

    lines = [
        "Motivon Vision Preview",
        "",
        message,
        "",
        f"Image endpoint: {IMAGE_URL}",
    ]

    if status:
        vision = status.get("vision", {})
        detection = status.get("vision_detection", {})
        lines.extend(
            [
                "",
                f"Vision state: {vision.get('state', '-')}",
                f"Detail: {vision.get('detail', '-')}",
                f"Camera OK: {vision.get('camera_ok', False)}",
                f"Model OK: {vision.get('model_ok', False)}",
                f"Face detected: {vision.get('face_detected', False)}",
                f"Last identity: {vision.get('last_identity', '-')}",
                f"Confidence: {float(vision.get('last_confidence', 0.0) or 0.0):.2f}",
                f"Detection: {detection.get('detail', '-')}",
            ]
        )

    lines.extend(["", "Press Q to close this preview."])

    y = 45
    for index, line in enumerate(lines):
        color = (0, 255, 255) if index == 0 else (210, 235, 255)
        scale = 0.8 if index == 0 else 0.55
        thickness = 2 if index == 0 else 1
        cv2.putText(
            frame,
            str(line)[:95],
            (25, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thickness,
            cv2.LINE_AA,
        )
        y += 34 if index == 0 else 26

    return frame


def main():
    print(f"Waiting for vision preview at {IMAGE_URL}")
    last_status = None
    last_status_fetch_s = 0.0
    while True:
        try:
            frame = fetch_image()
            if frame is not None:
                cv2.imshow(WINDOW_NAME, frame)
            else:
                time.sleep(0.1)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            now = time.monotonic()
            if now - last_status_fetch_s > 0.5:
                last_status_fetch_s = now
                try:
                    last_status = fetch_status()
                except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
                    last_status = None
            frame = make_waiting_frame(
                f"Waiting for camera/ROS image: {type(error).__name__}",
                last_status,
            )
            cv2.imshow(WINDOW_NAME, frame)
            time.sleep(0.25)
        except KeyboardInterrupt:
            break

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
