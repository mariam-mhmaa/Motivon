#!/usr/bin/env python3
"""
Simple client to connect to the camera server and display the live feed.
Press 'q' to quit.
"""

import sys
import cv2
from camera import get_client_camera

# Connect to Raspberry Pi camera server
HOST = '192.168.1.201'
PORT = 8888

print(f"🔌 Connecting to camera at {HOST}:{PORT}...")
camera = get_client_camera(host=HOST, port=PORT, width=240, height=180, framerate=8)

if camera.open():
    print("✓ Connected! Press 'q' to quit")
    frame_count = 0
    
    try:
        while True:
            success, frame = camera.read()
            if success:
                frame_count += 1
                # Display frame count
                cv2.putText(frame, f"Frame: {frame_count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow('Camera Feed', frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("\n✓ Closing camera feed...")
                    break
            else:
                print("✗ Failed to read frame")
                break
    except KeyboardInterrupt:
        print("\n✓ Interrupted by user")
    finally:
        camera.release()
        cv2.destroyAllWindows()
        print("✓ Camera released")
else:
    print("✗ Failed to connect to camera server")
    sys.exit(1)
