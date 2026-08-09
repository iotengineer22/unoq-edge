#!/usr/bin/env python3
"""
UNO Q Triple Camera Streamer (multi-cam.py) - High-Speed RAM Engine
Features:
  1. 📷 MIPI-CSI2 Camera (1280x720 HD - Large Featured Stream)
  2. 🔌 USB Web Camera (HD Dynamic Resolution - Large Featured Stream)
  3. ⚡ SPI Camera (320x240 Compact Sub-Stream - 150KB RAM Dump Engine)

MIPI resolution updated to 1280x720 HD!
Includes Auto Roll Alignment & Black Horizontal Line Inpainting Filter!
Renders pristine 320x240 spi_camera.png for WebUI streaming on Port 7000.
"""

import os
import sys
import time
import cv2
import json
import re
import glob
import subprocess
import threading
import numpy as np
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Global App State for Triple Cameras
latest_mipi_frame = None
latest_usb_frame = None

mipi_lock = threading.Lock()
usb_lock = threading.Lock()
spi_lock = threading.Lock()

is_saving = False
mipi_fps = 0.0
usb_fps = 0.0
spi_fps = 0.067  # 15.0s Polling Cycle
usb_resolution_str = "Connecting..."
spi_last_update_str = "Ready"
save_count = 0
camera_running = True

OUTPUT_DIR = "output_images"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

# File Paths & Constants (320x240 RGB565 = 153600 bytes = 150KB)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_FILE_BOARD = os.path.join(CURRENT_DIR, "captured.raw")
PNG_FILE_BOARD = os.path.join(CURRENT_DIR, "spi_camera.png")
MAP_FILE = os.path.join(CURRENT_DIR, "build", "zephyr", "zephyr.map")
BUFFER_SIZE = 153600  # 320 * 240 * 2 = 153600 bytes (150KB)
SPI_WIDTH = 320
SPI_HEIGHT = 240

def get_buffer_address():
    if os.path.exists(MAP_FILE):
        try:
            with open(MAP_FILE, "r") as f:
                content = f.read()
            match = re.search(r"(0x[0-9a-fA-F]+)\s+image_buffer\b", content)
            if match:
                return match.group(1)
        except Exception:
            pass
    return "0x20001178"

# ---------------------------------------------------------
# Auto Roll Alignment & Black Horizontal Line Inpainting Filter
# ---------------------------------------------------------
def convert_raw_to_png_file(raw_bytes, output_png_path, width=320, height=240):
    expected = width * height * 2
    if len(raw_bytes) < expected:
        raw_bytes = raw_bytes + b'\x00' * (expected - len(raw_bytes))
    else:
        raw_bytes = raw_bytes[:expected]

    raw_np = np.frombuffer(raw_bytes, dtype=np.uint8)

    non_zero_indices = np.where(raw_np > 0)[0]
    if len(non_zero_indices) > 0:
        start_offset = non_zero_indices[0]
        if start_offset % 2 != 0 and start_offset > 0:
            start_offset -= 1
    else:
        start_offset = 0

    aligned_data = raw_np[start_offset:]
    if len(aligned_data) < expected:
        aligned_data = np.pad(aligned_data, (0, expected - len(aligned_data)), mode='constant')
    else:
        aligned_data = aligned_data[:expected]

    arr = aligned_data.reshape((height, width, 2))
    
    b1 = arr[:, :, 0].astype(np.uint16)
    b2 = arr[:, :, 1].astype(np.uint16)

    # Big Endian RGB565 Decoding
    val = (b1 << 8) | b2
    r = ((val >> 11) & 0x1F) << 3
    g = ((val >> 5) & 0x3F) << 2
    b = (val & 0x1F) << 3
    
    bgr = np.dstack([b, g, r]).astype(np.uint8)

    # 1. Auto Pixel Roll Alignment
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    col_diffs = np.sum(np.abs(np.diff(gray.astype(np.int32), axis=1)), axis=0)
    if len(col_diffs) > 0:
        max_seam_col = np.argmax(col_diffs)
        if 40 < max_seam_col < 280:
            bgr = np.roll(bgr, -max_seam_col, axis=1)

    # 2. Black Horizontal Line Inpainting Filter
    row_means = np.mean(bgr, axis=(1, 2))
    valid_rows_mean = np.median(row_means[row_means > 5]) if np.any(row_means > 5) else 30
    
    for y in range(1, height - 1):
        if row_means[y] < 0.25 * valid_rows_mean or row_means[y] < 3:
            bgr[y] = (bgr[y - 1].astype(np.uint16) + bgr[y + 1].astype(np.uint16)) // 2

    cv2.imwrite(output_png_path, bgr)

def dump_150k_openocd_ram(ram_addr):
    openocd_bin = "/opt/openocd/bin/openocd"
    if not os.path.exists(openocd_bin):
        print(f"[OpenOCD ERROR] Binary {openocd_bin} not found!")
        return False, 0.0

    if os.path.exists(RAW_FILE_BOARD):
        try:
            os.remove(RAW_FILE_BOARD)
        except Exception:
            pass

    openocd_cmd = f"init; dump_image {RAW_FILE_BOARD} {ram_addr} {BUFFER_SIZE}; shutdown"
    cmd = [
        openocd_bin,
        "-d0",
        "-s", "/opt/openocd",
        "-f", "openocd_gpiod.cfg",
        "-c", openocd_cmd
    ]
    t0 = time.time()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = time.time() - t0
        if res.returncode == 0 and os.path.exists(RAW_FILE_BOARD):
            return True, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[OpenOCD Exception] {e}")

    return False, elapsed

def process_and_generate_spi_png():
    global spi_last_update_str, save_count

    ram_addr = get_buffer_address()
    success, elapsed = dump_150k_openocd_ram(ram_addr)

    if os.path.exists(RAW_FILE_BOARD):
        try:
            with open(RAW_FILE_BOARD, "rb") as f:
                raw_data = f.read()

            if len(raw_data) > 0:
                convert_raw_to_png_file(raw_data, PNG_FILE_BOARD, SPI_WIDTH, SPI_HEIGHT)
                spi_last_update_str = datetime.now().strftime("%H:%M:%S") + f" ({round(elapsed, 2)}s)"
                print(f"[📸 SPI Camera Dump SUCCESS 🎉] Retrieved 153,600 bytes in {round(elapsed, 2)}s -> Saved Clean PNG to {PNG_FILE_BOARD}")

                if is_saving:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    filepath = os.path.join(OUTPUT_DIR, f"spi_{ts}.png")
                    try:
                        with open(PNG_FILE_BOARD, "rb") as sf, open(filepath, "wb") as df:
                            df.write(sf.read())
                    except Exception:
                        pass
                return True
        except Exception as e:
            print(f"[PNG Decode Exception] {e}")

    return False

def spi_camera_thread():
    global camera_running
    ram_addr = get_buffer_address()
    print(f"[⚡ SPI Camera Thread] Polling RAM Address {ram_addr} every 15.0s")

    while camera_running:
        process_and_generate_spi_png()
        time.sleep(15.0)

# ---------------------------------------------------------
# 1. MIPI-CSI2 Camera Thread (1280x720 HD Resolution)
# ---------------------------------------------------------
def mipi_camera_thread():
    global latest_mipi_frame, camera_running, mipi_fps, save_count
    
    cmd = [
        "gst-launch-1.0", "-q",
        "libcamerasrc", "!",
        "video/x-raw,width=1280,height=720,framerate=30/1", "!",
        "videoconvert", "!",
        "jpegenc", "quality=80", "idct-method=1", "!",
        "fdsink", "sync=false", "async=false"
    ]
    
    clean_env = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "LD_LIBRARY_PATH": "/usr/lib/aarch64-linux-gnu:/usr/local/lib:/lib/aarch64-linux-gnu",
        "GST_PLUGIN_PATH": "/usr/lib/aarch64-linux-gnu/gstreamer-1.0:/usr/local/lib/gstreamer-1.0",
        "HOME": os.environ.get("HOME", "/home/arduino"),
        "USER": os.environ.get("USER", "arduino"),
        "SHELL": "/bin/bash"
    }

    print(f"[MIPI Camera] Launching pipeline:\n  {' '.join(cmd)}")
    
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=clean_env)
    except Exception as e:
        print(f"[MIPI Camera ERROR] {e}")
        return

    buf = bytearray()
    fps_counter = 0
    fps_start_time = time.time()
    
    while camera_running and proc.poll() is None:
        chunk = proc.stdout.read(16384)
        if not chunk:
            break
        buf.extend(chunk)
        
        while True:
            start = buf.find(b'\xff\xd8')
            if start == -1:
                if len(buf) > 2:
                    del buf[:-2]
                break
            if start > 0:
                del buf[:start]
                start = 0

            end = buf.find(b'\xff\xd9', 2)
            if end == -1:
                break

            jpg_data = bytes(buf[:end+2])
            del buf[:end+2]

            with mipi_lock:
                latest_mipi_frame = jpg_data

            fps_counter += 1
            now = time.time()
            if now - fps_start_time >= 1.0:
                mipi_fps = fps_counter / (now - fps_start_time)
                fps_counter = 0
                fps_start_time = now

            if is_saving:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filepath = os.path.join(OUTPUT_DIR, f"mipi_{ts}.jpg")
                try:
                    with open(filepath, "wb") as f:
                        f.write(jpg_data)
                    save_count += 1
                except Exception:
                    pass

    proc.terminate()

# ---------------------------------------------------------
# 2. USB Web Camera Thread (Dynamic Resolution Reader)
# ---------------------------------------------------------
def usb_camera_thread():
    global latest_usb_frame, camera_running, usb_fps, usb_resolution_str, save_count

    cap = None
    usb_dev_name = None
    target_indices = [0, 8, 9, 10, 2, 4, 6, 1]

    for dev_num in target_indices:
        dev_path = f"/dev/video{dev_num}"
        if not os.path.exists(dev_path):
            continue
        try:
            test_cap = cv2.VideoCapture(dev_num, cv2.CAP_V4L2)
            if test_cap.isOpened():
                ret, tmp = test_cap.read()
                if ret and tmp is not None and tmp.shape[0] > 0 and tmp.shape[1] > 0:
                    cap = test_cap
                    usb_dev_name = dev_path
                    usb_resolution_str = f"{tmp.shape[1]}x{tmp.shape[0]}"
                    print(f"[USB Camera] -> CONNECTED SUCCESS on {usb_dev_name} (Actual Res: {usb_resolution_str})!")
                    break
                test_cap.release()
        except Exception:
            pass

    if cap is None or not cap.isOpened():
        usb_resolution_str = "Not Found"
        print("[USB Camera WARNING] No USB Web Camera active on /dev/videoX. USB stream idle.")
        return

    fps_counter = 0
    fps_start_time = time.time()

    while camera_running:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.03)
            continue

        h, w = frame.shape[:2]
        actual_res = f"{w}x{h}"
        if usb_resolution_str != actual_res:
            usb_resolution_str = actual_res

        ret_jpg, jpeg_buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ret_jpg:
            jpg_bytes = jpeg_buf.tobytes()
            with usb_lock:
                latest_usb_frame = jpg_bytes

            fps_counter += 1
            now = time.time()
            if now - fps_start_time >= 1.0:
                usb_fps = fps_counter / (now - fps_start_time)
                fps_counter = 0
                fps_start_time = now

            if is_saving:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filepath = os.path.join(OUTPUT_DIR, f"usb_{ts}.jpg")
                try:
                    with open(filepath, "wb") as f:
                        f.write(jpg_bytes)
                except Exception:
                    pass

        time.sleep(0.01)

    cap.release()

# ---------------------------------------------------------
# 4. Multithreaded HTTP Server & Handler
# ---------------------------------------------------------
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class CameraHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        global is_saving, save_count, mipi_fps, usb_fps, spi_fps, usb_resolution_str, spi_last_update_str
        
        # 1. MIPI Camera Stream
        if self.path in ['/video_feed', '/video_feed/mipi']:
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            last_sent_frame_id = None
            try:
                while True:
                    with mipi_lock:
                        frame = latest_mipi_frame
                    
                    if frame is not None and frame is not last_sent_frame_id:
                        last_sent_frame_id = frame
                        self.wfile.write(b'--frame\r\n')
                        self.wfile.write(b'Content-Type: image/jpeg\r\n\r\n')
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                        self.wfile.flush()
                        time.sleep(0.001)
                    else:
                        time.sleep(0.005)
            except Exception:
                pass

        # 2. USB Camera Stream
        elif self.path == '/video_feed/usb':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            last_sent_frame_id = None
            try:
                while True:
                    with usb_lock:
                        frame = latest_usb_frame
                    
                    if frame is not None and frame is not last_sent_frame_id:
                        last_sent_frame_id = frame
                        self.wfile.write(b'--frame\r\n')
                        self.wfile.write(b'Content-Type: image/jpeg\r\n\r\n')
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                        self.wfile.flush()
                        time.sleep(0.001)
                    else:
                        time.sleep(0.01)
            except Exception:
                pass

        # 3. SPI Camera PNG Endpoint (Serves spi_camera.png in project directory)
        elif self.path.startswith('/video_feed/spi_png'):
            if os.path.exists(PNG_FILE_BOARD):
                try:
                    with open(PNG_FILE_BOARD, "rb") as f:
                        png_bytes = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/png')
                    self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(png_bytes)
                    return
                except Exception:
                    pass
            self.send_error(404, "PNG Not Ready")

        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            data = {
                "mipi_fps": round(mipi_fps, 1),
                "usb_fps": round(usb_fps, 1),
                "spi_fps": 0.067,
                "usb_res": usb_resolution_str,
                "spi_update": spi_last_update_str,
                "is_saving": is_saving,
                "save_count": save_count
            }
            self.wfile.write(json.dumps(data).encode('utf-8'))
            
        elif self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode('utf-8'))
            
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        global is_saving
        if self.path == '/api/trigger_spi':
            res = process_and_generate_spi_png()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            resp_data = {"status": "ok" if res else "error", "update": spi_last_update_str}
            self.wfile.write(json.dumps(resp_data).encode('utf-8'))

        elif self.path == '/api/start_save':
            is_saving = True
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"started","is_saving":true}')
            
        elif self.path == '/api/stop_save':
            is_saving = False
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"stopped","is_saving":false}')
            
        else:
            self.send_error(404, "Not Found")

# Modern Layout HTML: MIPI (1280x720) & USB Large Featured, SPI Compact
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UNO Q Triple Camera Streamer (MIPI 1280x720 & USB Large + SPI Compact)</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.7);
            --accent-color: #0072ce;
            --accent-hover: #005bb5;
            --purple-color: #818cf8;
            --purple-hover: #6366f1;
            --danger-color: #ef4444;
            --success-color: #22c55e;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --border-color: rgba(255, 255, 255, 0.1);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 1.5rem 1rem;
        }
        .header { text-align: center; margin-bottom: 1.5rem; }
        .header h1 {
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(135deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.3rem;
        }
        .header p { color: var(--text-secondary); font-size: 0.95rem; }
        .container {
            width: 100%;
            max-width: 1550px;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }
        .triple-grid {
            display: grid;
            grid-template-columns: 2.2fr 2.2fr 1.2fr;
            gap: 1.25rem;
            align-items: start;
        }
        @media (max-width: 1100px) { .triple-grid { grid-template-columns: 1fr 1fr; } }
        @media (max-width: 700px) { .triple-grid { grid-template-columns: 1fr; } }
        
        .video-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            position: relative;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
            display: flex;
            flex-direction: column;
            aspect-ratio: 16 / 9;
            background-color: #000;
        }
        .video-card.spi-card {
            aspect-ratio: 4 / 3;
            border-color: rgba(56, 189, 248, 0.3);
        }
        .video-title {
            position: absolute;
            top: 0.75rem;
            left: 0.75rem;
            background: rgba(15, 23, 42, 0.85);
            backdrop-filter: blur(8px);
            border: 1px solid var(--border-color);
            padding: 0.4rem 0.8rem;
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 700;
            color: #38bdf8;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            z-index: 10;
        }
        .video-stream { width: 100%; height: 100%; object-fit: contain; }
        .controls-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
        }
        .status-group { display: flex; align-items: center; gap: 2rem; }
        .status-item { display: flex; flex-direction: column; gap: 0.2rem; }
        .status-label {
            font-size: 0.8rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .status-value { font-size: 1.2rem; font-weight: 700; }
        .btn-group { display: flex; gap: 1rem; flex-wrap: wrap; }
        .btn {
            font-family: inherit;
            font-size: 0.95rem;
            font-weight: 600;
            padding: 0.75rem 1.5rem;
            border-radius: 10px;
            border: none;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .btn-primary { background-color: var(--accent-color); color: white; }
        .btn-primary:hover { background-color: var(--accent-hover); transform: translateY(-2px); }
        .btn-purple { background-color: var(--purple-color); color: white; }
        .btn-purple:hover { background-color: var(--purple-hover); transform: translateY(-2px); }
        .btn-danger { background-color: var(--danger-color); color: white; }
        .btn-danger:hover { opacity: 0.9; transform: translateY(-2px); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; }
        .indicator { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
        .indicator.active { background-color: var(--success-color); box-shadow: 0 0 10px var(--success-color); }
    </style>
</head>
<body>
    <div class="header">
        <h1>UNO Q Triple Camera Streamer</h1>
        <p>Simultaneous 3-Camera Live Stream: MIPI-CSI2 (1280x720) + USB Web Cam + SPI Camera</p>
    </div>
    <div class="container">
        <div class="triple-grid">
            <div class="video-card">
                <div class="video-title">
                    <span class="indicator active"></span>
                    📷 MIPI-CSI2 (1280x720) | <span id="mipiFps">0.0</span> FPS
                </div>
                <img src="/video_feed/mipi" class="video-stream" alt="MIPI Camera Stream">
            </div>
            <div class="video-card">
                <div class="video-title">
                    <span class="indicator active"></span>
                    🔌 USB Web Cam (<span id="usbRes" style="color: #4ade80;">...</span>) | <span id="usbFps">0.0</span> FPS
                </div>
                <img src="/video_feed/usb" class="video-stream" alt="USB Camera Stream">
            </div>
            <div class="video-card spi-card">
                <div class="video-title">
                    <span class="indicator active"></span>
                    📡 SPI Camera | Live: <span id="spiUpdate" style="color: #38bdf8;">--</span>
                </div>
                <img id="spiStreamImg" src="/video_feed/spi_png" class="video-stream" alt="SPI Camera Stream">
            </div>
        </div>

        <div class="controls-card">
            <div class="status-group">
                <div class="status-item">
                    <span class="status-label">Saving Status</span>
                    <span id="saveStatus" class="status-value" style="color: var(--text-secondary);">IDLE</span>
                </div>
                <div class="status-item">
                    <span class="status-label">Saved Triple Frames</span>
                    <span id="saveCount" class="status-value">0 Frames</span>
                </div>
            </div>

            <div class="btn-group">
                <button id="fetchSpiBtn" class="btn btn-purple">
                    📸 Instant SPI Camera Read
                </button>
                <button id="startBtn" class="btn btn-primary">
                    ▶ Start Triple Frame Saving
                </button>
                <button id="stopBtn" class="btn btn-danger" disabled>
                    ■ Stop Saving
                </button>
            </div>
        </div>
    </div>

    <script>
        const fetchSpiBtn = document.getElementById('fetchSpiBtn');
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        const saveStatus = document.getElementById('saveStatus');
        const saveCount = document.getElementById('saveCount');
        const mipiFps = document.getElementById('mipiFps');
        const usbFps = document.getElementById('usbFps');
        const usbRes = document.getElementById('usbRes');
        const spiUpdate = document.getElementById('spiUpdate');
        const spiStreamImg = document.getElementById('spiStreamImg');

        let lastSpiTime = "";

        async function refreshSpiFrame() {
            fetchSpiBtn.disabled = true;
            fetchSpiBtn.textContent = "⏳ Reading SPI Camera...";
            try {
                const res = await fetch('/api/trigger_spi', { method: 'POST' });
                const data = await res.json();
                if (data.update) {
                    spiUpdate.textContent = data.update;
                    spiStreamImg.src = `/video_feed/spi_png?t=${Date.now()}`;
                }
            } catch (e) {}
            fetchSpiBtn.disabled = false;
            fetchSpiBtn.textContent = "📸 Instant SPI Camera Read";
        }

        fetchSpiBtn.addEventListener('click', refreshSpiFrame);

        async function updateStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                mipiFps.textContent = (data.mipi_fps || 0).toFixed(1);
                usbFps.textContent = (data.usb_fps || 0).toFixed(1);
                usbRes.textContent = data.usb_res || 'Connecting...';
                
                if (data.spi_update && data.spi_update !== lastSpiTime) {
                    lastSpiTime = data.spi_update;
                    spiUpdate.textContent = data.spi_update;
                    spiStreamImg.src = `/video_feed/spi_png?t=${Date.now()}`;
                }

                saveCount.textContent = `${data.save_count} Frames`;

                if (data.is_saving) {
                    saveStatus.textContent = "SAVING TRIPLE...";
                    saveStatus.style.color = "var(--success-color)";
                    startBtn.disabled = true;
                    stopBtn.disabled = false;
                } else {
                    saveStatus.textContent = "IDLE";
                    saveStatus.style.color = "var(--text-secondary)";
                    startBtn.disabled = false;
                    stopBtn.disabled = true;
                }
            } catch (e) {}
        }

        startBtn.addEventListener('click', async () => {
            await fetch('/api/start_save', { method: 'POST' });
            updateStatus();
        });

        stopBtn.addEventListener('click', async () => {
            await fetch('/api/stop_save', { method: 'POST' });
            updateStatus();
        });

        setInterval(updateStatus, 500);
    </script>
</body>
</html>
"""

def main():
    # Start MIPI Camera Thread (1280x720 HD)
    mipi_thread = threading.Thread(target=mipi_camera_thread, daemon=True)
    mipi_thread.start()

    # Start USB Camera Thread
    usb_thread = threading.Thread(target=usb_camera_thread, daemon=True)
    usb_thread.start()

    # Start SPI Camera Engine Thread
    spi_thread = threading.Thread(target=spi_camera_thread, daemon=True)
    spi_thread.start()
    
    server_address = ('', 7000)
    httpd = ThreadedHTTPServer(server_address, CameraHTTPRequestHandler)
    print("==================================================")
    print("  UNO Q Triple Camera Streamer Started (multi-cam.py)")
    print("  📷 MIPI Camera Resolution: 1280x720 HD")
    print("  Streams: MIPI-CSI2 (1280x720) + USB + SPI Camera")
    print("  Access WebUI at: http://localhost:7000")
    print("==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == '__main__':
    main()
