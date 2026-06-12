"""
Raspberry Pi Camera Module - Real-time streaming via TCP.

This module provides a clean interface to capture video from Raspberry Pi Camera V2
using rpicam-vid and ffmpeg, streaming over TCP with MJPEG format for reliable frame parsing.

Usage:
    On Raspberry Pi (run once, then leave running):
        camera = PiCamera(mode='server', port=8888)
        camera.start_server()

    On laptop (consuming frames):
        camera = PiCamera(mode='client', host='192.168.1.200', port=8888)
        camera.open()
        success, frame = camera.read()
        camera.release()
"""

import subprocess
import socket
import numpy as np
import cv2
import threading
import time
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PiCamera:
    """
    Raspberry Pi Camera V2 interface with TCP streaming.
    
    Supports two modes:
    - 'server': Runs rpicam + ffmpeg locally (on Raspberry Pi)
    - 'client': Connects to existing TCP stream (on laptop/desktop)
    """
    
    def __init__(
        self,
        mode='client',
        host='192.168.1.200',
        port=8888,
        width=240,
        height=180,
        framerate=8,
        codec='mjpeg'
    ):
        """
        Initialize Raspberry Pi Camera.
        
        Args:
            mode: 'server' to start rpicam locally, 'client' to connect to remote stream
            host: Camera host IP address (for client mode) or bind address (for server mode)
            port: TCP port for streaming
            width: Video width
            height: Video height
            framerate: Video framerate
            codec: 'mjpeg' or 'yuv420' (server mode only)
        """
        self.mode = mode
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.framerate = framerate
        self.codec = codec
        
        self.sock = None
        self.buffer = bytearray()
        self.process = None
        self.is_running = False
        
    # =====================================================================
    # CLIENT MODE: Connect to existing TCP stream on Raspberry Pi
    # =====================================================================
    
    def open(self):
        """Connect to TCP stream (client mode)."""
        if self.mode != 'client':
            raise RuntimeError("open() only works in 'client' mode")
        
        logger.info(f"🔌 Connecting to camera at {self.host}:{self.port}...")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        
        try:
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(3)
            self.is_running = True
            logger.info("✓ Connected to camera stream")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to connect: {e}")
            return False
    
    def read(self):
        """
        Read next frame from TCP stream (client mode).
        
        Returns:
            (success: bool, frame: ndarray or None)
        """
        if self.mode != 'client':
            raise RuntimeError("read() only works in 'client' mode")
        
        if not self.is_running or self.sock is None:
            return False, None
        
        while True:
            # Look for JPEG markers (MJPEG format)
            start = self.buffer.find(b'\xff\xd8')  # JPEG start
            end = self.buffer.find(b'\xff\xd9')    # JPEG end
            
            if start != -1 and end != -1 and end > start:
                # Extract JPEG data
                jpg_data = bytes(self.buffer[start:end + 2])
                del self.buffer[:end + 2]
                
                # Decode frame
                img_array = np.frombuffer(jpg_data, dtype=np.uint8)
                frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                
                if frame is not None:
                    return True, frame
                continue
            
            # Receive more data
            try:
                packet = self.sock.recv(4096)
            except socket.timeout:
                return False, None
            
            if not packet:
                return False, None
            
            self.buffer.extend(packet)
            
            # Prevent memory overflow
            if len(self.buffer) > 2_000_000:
                self.buffer = self.buffer[-500_000:]
    
    def release(self):
        """Close TCP connection (client mode)."""
        self.is_running = False
        if self.sock is not None:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
        logger.info("✓ Camera released")
    
    # =====================================================================
    # SERVER MODE: Start rpicam + ffmpeg on Raspberry Pi
    # =====================================================================
    
    def start_server(self):
        """
        Start camera server (server mode).
        
        Runs on Raspberry Pi to stream video via TCP.
        The ffmpeg command streams MJPEG which the client can parse with read().
        """
        if self.mode != 'server':
            raise RuntimeError("start_server() only works in 'server' mode")
        
        logger.info(f"🚀 Starting camera server on {self.host}:{self.port}...")
        
        # Kill any existing processes
        self._kill_existing_processes()
        time.sleep(0.5)
        
        # Build the rpicam + ffmpeg pipeline
        rpicam_cmd = [
            'rpicam-vid',
            '-t', '0',           # Run forever
            '-n',                # No preview
            '--width', str(self.width),
            '--height', str(self.height),
            '--framerate', str(self.framerate),
            '--codec', self.codec,
            '-o', '-'            # Output to stdout
        ]
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'warning',
            '-fflags', 'nobuffer',
            '-flags', 'low_delay',
            '-f', self.codec,    # Input format matches rpicam output
            '-i', 'pipe:0',      # Read from stdin
            '-c:v', 'mjpeg',     # Output MJPEG for reliable parsing
            '-q:v', '8',         # Quality
            '-f', 'mjpeg',       # MJPEG format
            f'tcp://{self.host}:{self.port}?listen=1'
        ]
        
        try:
            # Start rpicam, pipe to ffmpeg
            self.process = subprocess.Popen(
                rpicam_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            
            ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=self.process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            
            # Allow rpicam's stdout to be closed when ffmpeg closes
            self.process.stdout.close()
            
            self.is_running = True
            logger.info(f"✓ Camera server started")
            logger.info(f"  Clients can connect to tcp://{self.host}:{self.port}")
            logger.info(f"  Video: {self.width}x{self.height} @ {self.framerate} fps")
            
            # Monitor processes
            self._monitor_processes(self.process, ffmpeg_process)
            
        except Exception as e:
            logger.error(f"✗ Failed to start server: {e}")
            self.is_running = False
    
    def stop_server(self):
        """Stop camera server (server mode)."""
        self.is_running = False
        self._kill_existing_processes()
        logger.info("✓ Camera server stopped")
    
    def _kill_existing_processes(self):
        """Kill any existing rpicam and ffmpeg processes."""
        try:
            subprocess.run(['pkill', '-f', 'rpicam'], check=False)
            subprocess.run(['pkill', '-f', 'ffmpeg'], check=False)
        except:
            pass
    
    def _monitor_processes(self, rpicam_proc, ffmpeg_proc):
        """Monitor processes and restart if they die."""
        def monitor():
            while self.is_running:
                if rpicam_proc.poll() is not None:
                    logger.warning("rpicam process died, restarting...")
                    self.start_server()
                    return
                if ffmpeg_proc.poll() is not None:
                    logger.warning("ffmpeg process died, restarting...")
                    self.start_server()
                    return
                time.sleep(1)
        
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()


# =====================================================================
# Quick utility functions for easy use
# =====================================================================

def get_client_camera(host='192.168.1.200', port=8888, width=240, height=180, framerate=8):
    """Create a client camera that connects to remote Pi camera."""
    return PiCamera(
        mode='client',
        host=host,
        port=port,
        width=width,
        height=height,
        framerate=framerate
    )


def get_server_camera(host='0.0.0.0', port=8888, width=240, height=180, framerate=8, codec='mjpeg'):
    """Create a server camera (for running on Raspberry Pi)."""
    return PiCamera(
        mode='server',
        host=host,
        port=port,
        width=width,
        height=height,
        framerate=framerate,
        codec=codec
    )


if __name__ == '__main__':
    """
    Example: Run this on Raspberry Pi to start the server.
    Then connect from laptop using the client mode in your face recognition code.
    """
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'server':
        # Run on Raspberry Pi
        camera = get_server_camera(host='0.0.0.0', port=8888, width=240, height=180, framerate=8)
        camera.start_server()
        
        try:
            while camera.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            camera.stop_server()
    else:
        # Example client usage
        print("Example client usage:")
        print()
        print("  from camera import get_client_camera")
        print("  camera = get_client_camera(host='192.168.1.200', port=8888)")
        print("  camera.open()")
        print("  success, frame = camera.read()")
        print("  camera.release()")
        print()
        print("Or run 'python camera.py server' on Raspberry Pi to start the server")
