#!/usr/bin/env python3
"""
Standalone High-FPS MIPI-CSI2 Camera Streamer & Frame Saver for UNO Q (Qualcomm Linux)
Uses ONLY Python Standard Library (http.server) - Zero external dependencies!
Runs on Port 7000.
"""

import os
import sys
import time
import json
import subprocess
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Global App State
latest_jpeg_frame = None
frame_lock = threading.Lock()
is_saving = False
current_fps = 0.0
save_count = 0
camera_running = True

OUTPUT_DIR = "output_images"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def camera_capture_thread():
    """Background thread capturing JPEG frames from host GStreamer libcamerasrc."""
    global latest_jpeg_frame, camera_running, current_fps, save_count
    
    # Caps immediately after libcamerasrc forces hardware sensor binning to 1280x720 / 30 FPS
    cmd = [
        "gst-launch-1.0", "-q",
        "libcamerasrc", "!",
        "video/x-raw,width=1280,height=720", "!",
        "videoconvert", "!",
        "jpegenc", "quality=70", "idct-method=1", "!",
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

    print(f"[Camera] Launching optimized GStreamer pipeline:\n  {' '.join(cmd)}")
    
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=clean_env)
    except Exception as e:
        print(f"[Camera ERROR] Failed to launch process: {e}")
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

            with frame_lock:
                latest_jpeg_frame = jpg_data

            fps_counter += 1
            now = time.time()
            if now - fps_start_time >= 1.0:
                current_fps = fps_counter / (now - fps_start_time)
                fps_counter = 0
                fps_start_time = now

            if is_saving:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filepath = os.path.join(OUTPUT_DIR, f"frame_{ts}.jpg")
                try:
                    with open(filepath, "wb") as f:
                        f.write(jpg_data)
                    save_count += 1
                except Exception as e:
                    print(f"[Saver ERROR] {e}")

    proc.terminate()
    print("[Camera] Process terminated.")

# Threaded HTTP Server to handle concurrent video stream & API calls
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class CameraHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        global is_saving, save_count, current_fps
        
        if self.path == '/video_feed':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            last_sent_frame_id = None
            try:
                while True:
                    with frame_lock:
                        frame = latest_jpeg_frame
                    
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
                
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            data = {
                "fps": round(current_fps, 1),
                "is_saving": is_saving,
                "save_count": save_count,
                "resolution": "1280x720"
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
        if self.path == '/api/start_save':
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

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UNO Q High-FPS Camera Streamer</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.7);
            --accent-color: #0072ce;
            --accent-hover: #005bb5;
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
            padding: 2rem 1rem;
        }

        .header { text-align: center; margin-bottom: 2rem; }

        .header h1 {
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(135deg, #38bdf8, #0072ce);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }

        .header p { color: var(--text-secondary); font-size: 1rem; }

        .container {
            width: 100%;
            max-width: 1000px;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        .video-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            position: relative;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
            display: flex;
            justify-content: center;
            align-items: center;
            aspect-ratio: 16 / 9;
            background-color: #000;
        }

        .video-stream { width: 100%; height: 100%; object-fit: contain; }

        .fps-badge {
            position: absolute;
            top: 1rem;
            left: 1rem;
            background: rgba(15, 23, 42, 0.85);
            backdrop-filter: blur(8px);
            border: 1px solid var(--border-color);
            padding: 0.5rem 1rem;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 700;
            color: #38bdf8;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

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

        .status-group { display: flex; align-items: center; gap: 1.5rem; }

        .status-item { display: flex; flex-direction: column; gap: 0.2rem; }

        .status-label {
            font-size: 0.8rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .status-value { font-size: 1.2rem; font-weight: 700; }

        .btn-group { display: flex; gap: 1rem; }

        .btn {
            font-family: inherit;
            font-size: 1rem;
            font-weight: 600;
            padding: 0.8rem 1.8rem;
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

        .btn-danger { background-color: var(--danger-color); color: white; }
        .btn-danger:hover { opacity: 0.9; transform: translateY(-2px); }

        .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; }

        .indicator { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
        .indicator.active { background-color: var(--success-color); box-shadow: 0 0 10px var(--success-color); }
        .indicator.inactive { background-color: var(--text-secondary); }
    </style>
</head>
<body>

    <div class="header">
        <h1>Arduino UNO Q Camera Streamer</h1>
        <p>MIPI-CSI2 Ultra High-FPS Live Feed & Millisecond Frame Saver</p>
    </div>

    <div class="container">
        <div class="video-card">
            <div class="fps-badge">
                <span class="indicator active"></span>
                <span id="fpsVal">0.0</span> FPS | <span id="resVal">1280x720</span>
            </div>
            <img src="/video_feed" class="video-stream" alt="Live Camera Stream">
        </div>

        <div class="controls-card">
            <div class="status-group">
                <div class="status-item">
                    <span class="status-label">Saving Status</span>
                    <span id="saveStatus" class="status-value" style="color: var(--text-secondary);">IDLE</span>
                </div>
                <div class="status-item">
                    <span class="status-label">Saved Frames</span>
                    <span id="saveCount" class="status-value">0 Frames</span>
                </div>
            </div>

            <div class="btn-group">
                <button id="startBtn" class="btn btn-primary">
                    ▶ Start Frame Saving
                </button>
                <button id="stopBtn" class="btn btn-danger" disabled>
                    ■ Stop Saving
                </button>
            </div>
        </div>
    </div>

    <script>
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        const saveStatus = document.getElementById('saveStatus');
        const saveCount = document.getElementById('saveCount');
        const fpsVal = document.getElementById('fpsVal');

        async function updateStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                fpsVal.textContent = data.fps.toFixed(1);
                saveCount.textContent = `${data.save_count} Frames`;

                if (data.is_saving) {
                    saveStatus.textContent = "SAVING...";
                    saveStatus.style.color = "var(--success-color)";
                    startBtn.disabled = true;
                    stopBtn.disabled = false;
                } else {
                    saveStatus.textContent = "IDLE";
                    saveStatus.style.color = "var(--text-secondary)";
                    startBtn.disabled = false;
                    stopBtn.disabled = true;
                }
            } catch (e) {
                console.error("Status fetch error:", e);
            }
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
    # Start Camera Background Thread
    cam_thread = threading.Thread(target=camera_capture_thread, daemon=True)
    cam_thread.start()
    
    server_address = ('', 7000)
    httpd = ThreadedHTTPServer(server_address, CameraHTTPRequestHandler)
    print("==================================================")
    print("  UNO Q Standalone WebUI Camera Server Started")
    print("  Zero-Dependency Pure Python Server")
    print("  Access WebUI at: http://localhost:7000")
    print("==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == '__main__':
    main()
