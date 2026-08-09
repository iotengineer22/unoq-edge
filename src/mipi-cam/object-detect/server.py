#!/usr/bin/env python3
"""
Arduino UNO Q High-Resolution MIPI-CSI2 Object Detection & Calibration Server
Target File: server.py
Features:
  - Terminal logs display Latency in ms
  - WebUI label for Defog/Dehaze updated to clean English
  - Target Model: camera-test-linux-aarch64-v10-impulse-#1.eim
"""

import os
import sys
import time
import cv2
import json
import threading
import numpy as np
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse
from edge_impulse_linux.runner import ImpulseRunner

# Working .eim model
EIM_FILE = os.path.abspath("camera-test-linux-aarch64-v10-impulse-#1.eim")
CONFIDENCE_THRESHOLD = 0.2

# Strict 1920x1080 Full HD Resolution
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080

# Save Directory for frames
SAVE_DIR = os.path.abspath("saved_frames")
os.makedirs(SAVE_DIR, exist_ok=True)

# Global Image Tuning Atomic Variables
g_red_gain = 1.0
g_green_gain = 1.0
g_blue_gain = 1.0
g_defog = 0           # 0 - 10 (Anti-Haze / Dehaze Filter for Cloudy Lenses)
g_sharpness = 0       # 0 - 10 (Focus/Edge Enhancement)
g_brightness = 0      # -100 - 100
g_contrast = 1.0      # 0.5 - 2.0

# Global State
g_latest_raw_frame = None
g_latest_annotated_jpeg = None
g_latest_metrics = {"boxes": [], "max_score": 0.0, "time_ms": 0.0, "frame_count": 0}
g_lock = threading.Lock()
g_running = True

# Multithreaded HTTP Server class so streaming video_feed doesn't block API requests!
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

# Process Frame with Dehaze/Defog, User RGB Gains, Sharpness/Focus, Brightness & Contrast
def apply_user_image_tune(frame_bgr, r_gain, g_gain, b_gain, defog_val, sharp_val, bright_val, contrast_val):
    img = frame_bgr.copy()

    # 0. Apply Dehaze / Defog Filter for Cloudy Lenses using CLAHE
    if defog_val > 0:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clip_lim = 1.5 + float(defog_val) * 0.4
        clahe = cv2.createCLAHE(clipLimit=clip_lim, tileGridSize=(8, 8))
        l = clahe.apply(l)
        img = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

    img = img.astype(np.float32)

    # 1. Apply RGB Gain Adjustments
    b, g, r = cv2.split(img)
    
    # Auto White-balance base
    b_avg = np.mean(b) + 1e-5
    g_avg = np.mean(g) + 1e-5
    r_avg = np.mean(r) + 1e-5
    k = (b_avg + g_avg + r_avg) / 3.0
    b *= (k / b_avg)
    g *= (k / g_avg)
    r *= (k / r_avg)

    # Apply User RGB Sliders Multipliers
    r *= float(r_gain)
    g *= float(g_gain)
    b *= float(b_gain)

    img = cv2.merge([b, g, r])

    # 2. Apply Brightness & Contrast
    if contrast_val != 1.0 or bright_val != 0:
        img = img * float(contrast_val) + float(bright_val)

    img = np.clip(img, 0, 255).astype(np.uint8)

    # 3. Apply Focus / Sharpness Enhancement if set
    if sharp_val > 0:
        kernel = np.array([[0, -1, 0],
                           [-1, 4 + sharp_val * 0.5, -1],
                           [0, -1, 0]], dtype=np.float32)
        img = cv2.filter2D(img, -1, kernel)

    return img

# Embedded Modern WebUI HTML (English Defog Label & Clean Metrics)
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Arduino UNO Q 1920x1080 MIPI Camera Server</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(21, 30, 48, 0.75);
            --accent-primary: #38bdf8;
            --accent-gradient: linear-gradient(135deg, #38bdf8, #818cf8);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --border-color: rgba(255, 255, 255, 0.12);
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
        .header { text-align: center; margin-bottom: 1.25rem; }
        .header h1 {
            font-size: 2.2rem;
            font-weight: 800;
            background: var(--accent-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.3rem;
        }
        .container {
            width: 100%;
            max-width: 1280px;
            display: grid;
            grid-template-columns: 1fr 380px;
            gap: 1.5rem;
        }
        @media (max-width: 960px) { .container { grid-template-columns: 1fr; } }
        .video-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            position: relative;
            overflow: hidden;
            aspect-ratio: 16 / 9;
            width: 100%;
            max-width: 800px;
            margin: 0 auto;
            background-color: #000;
        }
        #stream-img { width: 100%; height: 100%; display: block; object-fit: contain; }
        .sidebar { display: flex; flex-direction: column; gap: 1rem; }
        .card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.25rem;
        }
        .card h2 { font-size: 1.1rem; font-weight: 700; color: var(--accent-primary); margin-bottom: 1rem; }
        .metric-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.75rem; }
        .metric-box {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 0.75rem;
            text-align: center;
        }
        .metric-val { font-size: 1.35rem; font-weight: 700; }
        .metric-lbl { font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.2rem; }
        .slider-group { display: flex; flex-direction: column; gap: 0.85rem; }
        .slider-control { display: flex; flex-direction: column; gap: 0.25rem; }
        .slider-label { display: flex; justify-content: space-between; font-size: 0.85rem; font-weight: 600; }
        .slider-label span { color: var(--accent-primary); }
        input[type="range"] {
            width: 100%;
            height: 8px;
            border-radius: 4px;
            background: rgba(255, 255, 255, 0.15);
            outline: none;
            accent-color: var(--accent-primary);
            cursor: pointer;
        }
        .btn-reset {
            margin-top: 0.5rem;
            background: linear-gradient(135deg, #ef4444, #f43f5e);
            color: #fff;
            border: none;
            border-radius: 8px;
            padding: 0.6rem;
            font-weight: 700;
            font-size: 0.85rem;
            cursor: pointer;
            transition: opacity 0.2s;
        }
        .btn-reset:hover { opacity: 0.9; }
        .detections-list { max-height: 180px; overflow-y: auto; display: flex; flex-direction: column; gap: 0.5rem; }
        .detection-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(255, 255, 255, 0.04);
            border-left: 4px solid var(--accent-primary);
            border-radius: 6px;
            padding: 0.5rem 0.75rem;
            font-size: 0.85rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Arduino UNO Q 1920x1080 MIPI Server</h1>
        <p>1920x1080 Full HD Live Tuning & Detection Panel</p>
    </div>
    <div class="container">
        <div class="video-card">
            <img id="stream-img" src="/video_feed" alt="Full HD Camera Stream with Overlay">
        </div>
        <div class="sidebar">
            <div class="card">
                <h2>🎛️ Live RGB, Defog & Focus Controls</h2>
                <div class="slider-group">
                    <div class="slider-control">
                        <div class="slider-label">☁️ Defog / Dehaze: <span id="val-defog">0</span></div>
                        <input type="range" id="slider-defog" min="0" max="10" step="1" value="0" oninput="sendTune('defog', this.value, 'val-defog')">
                    </div>
                    <div class="slider-control">
                        <div class="slider-label">🔍 Focus / Sharpness: <span id="val-sharp">0</span></div>
                        <input type="range" id="slider-sharp" min="0" max="10" step="1" value="0" oninput="sendTune('sharpness', this.value, 'val-sharp')">
                    </div>
                    <div class="slider-control">
                        <div class="slider-label">🔴 Red Gain: <span id="val-red">1.00</span></div>
                        <input type="range" id="slider-red" min="0.5" max="2.5" step="0.05" value="1.0" oninput="sendTune('red_gain', this.value, 'val-red')">
                    </div>
                    <div class="slider-control">
                        <div class="slider-label">🟢 Green Gain: <span id="val-green">1.00</span></div>
                        <input type="range" id="slider-green" min="0.5" max="2.5" step="0.05" value="1.0" oninput="sendTune('green_gain', this.value, 'val-green')">
                    </div>
                    <div class="slider-control">
                        <div class="slider-label">🔵 Blue Gain: <span id="val-blue">1.00</span></div>
                        <input type="range" id="slider-blue" min="0.5" max="2.5" step="0.05" value="1.0" oninput="sendTune('blue_gain', this.value, 'val-blue')">
                    </div>
                    <div class="slider-control">
                        <div class="slider-label">☀️ Brightness: <span id="val-bright">0</span></div>
                        <input type="range" id="slider-bright" min="-100" max="100" step="5" value="0" oninput="sendTune('brightness', this.value, 'val-bright')">
                    </div>
                    <div class="slider-control">
                        <div class="slider-label">🌗 Contrast: <span id="val-contrast">1.00</span></div>
                        <input type="range" id="slider-contrast" min="0.5" max="2.0" step="0.1" value="1.0" oninput="sendTune('contrast', this.value, 'val-contrast')">
                    </div>
                    <button class="btn-reset" onclick="resetDefaults()">🔄 Reset Default Controls</button>
                </div>
            </div>
            <div class="card">
                <h2>📊 Metrics</h2>
                <div class="metric-grid">
                    <div class="metric-box">
                        <div class="metric-val" id="max-score" style="color: #38bdf8;">0.0000</div>
                        <div class="metric-lbl">Max Confidence</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-val" id="det-count">0</div>
                        <div class="metric-lbl">Objects Found</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-val" id="frame-num" style="color: #38bdf8;">#0</div>
                        <div class="metric-lbl">Processed Frame</div>
                    </div>
                </div>
            </div>
            <div class="card">
                <h2>🎯 Detected Objects</h2>
                <div class="detections-list" id="detections-list">
                    <div style="color: var(--text-secondary); font-size: 0.85rem; text-align: center;">Processing frames...</div>
                </div>
            </div>
        </div>
    </div>
    <script>
        function sendTune(key, val, displayId) {
            document.getElementById(displayId).innerText = parseFloat(val).toFixed(2);
            fetch('/api/tune?key=' + encodeURIComponent(key) + '&val=' + encodeURIComponent(val))
                .then(r => r.json())
                .then(d => console.log("Tune response:", d))
                .catch(err => console.error("Tune error:", err));
        }

        function resetDefaults() {
            document.getElementById('slider-defog').value = 0;
            document.getElementById('val-defog').innerText = "0";
            document.getElementById('slider-sharp').value = 0;
            document.getElementById('val-sharp').innerText = "0";
            document.getElementById('slider-red').value = 1.0;
            document.getElementById('val-red').innerText = "1.00";
            document.getElementById('slider-green').value = 1.0;
            document.getElementById('val-green').innerText = "1.00";
            document.getElementById('slider-blue').value = 1.0;
            document.getElementById('val-blue').innerText = "1.00";
            document.getElementById('slider-bright').value = 0;
            document.getElementById('val-bright').innerText = "0";
            document.getElementById('slider-contrast').value = 1.0;
            document.getElementById('val-contrast').innerText = "1.00";
            fetch('/api/tune?reset=true');
        }

        async function fetchMetrics() {
            try {
                const res = await fetch('/api/detections');
                const data = await res.json();

                const maxScoreVal = (data.max_score || 0.0);
                document.getElementById('max-score').innerText = maxScoreVal.toFixed(4) + ` (${(maxScoreVal * 100).toFixed(1)}%)`;
                document.getElementById('det-count').innerText = (data.boxes ? data.boxes.length : 0);
                document.getElementById('frame-num').innerText = '#' + (data.frame_count || 0);

                const listEl = document.getElementById('detections-list');
                if (!data.boxes || data.boxes.length === 0) {
                    listEl.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.85rem; text-align: center;">No objects detected</div>';
                } else {
                    let html = '';
                    data.boxes.forEach(box => {
                        html += `
                            <div class="detection-item">
                                <span style="font-weight:600">${box.label}</span>
                                <span style="color:#38bdf8;font-weight:700">${box.confidence.toFixed(4)} (${(box.confidence * 100).toFixed(1)}%)</span>
                            </div>
                        `;
                    });
                    listEl.innerHTML = html;
                }
            } catch (err){}
        }

        setInterval(fetchMetrics, 200);
    </script>
</body>
</html>
"""

class WebServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        self.do_GET()

    def do_GET(self):
        global g_latest_annotated_jpeg, g_latest_metrics
        global g_red_gain, g_green_gain, g_blue_gain, g_defog, g_sharpness, g_brightness, g_contrast

        parsed_url = urlparse(self.path)

        if parsed_url.path in ['/', '/index.html']:
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.send_header('Content-Length', str(len(INDEX_HTML.encode('utf-8'))))
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode('utf-8'))

        elif parsed_url.path == '/video_feed':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            while g_running:
                with g_lock:
                    jpeg = g_latest_annotated_jpeg
                if jpeg is not None:
                    try:
                        header = f"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n".encode('utf-8')
                        self.wfile.write(header)
                        self.wfile.write(jpeg)
                        self.wfile.write(b'\r\n')
                    except Exception:
                        break
                time.sleep(0.1)

        elif parsed_url.path == '/api/detections':
            with g_lock:
                data = json.dumps(g_latest_metrics)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(data.encode('utf-8'))))
            self.end_headers()
            self.wfile.write(data.encode('utf-8'))

        elif '/api/tune' in parsed_url.path:
            query = parse_qs(parsed_url.query)
            if 'reset' in query:
                g_red_gain = 1.0
                g_green_gain = 1.0
                g_blue_gain = 1.0
                g_defog = 0
                g_sharpness = 0
                g_brightness = 0
                g_contrast = 1.0
                print("\n[TUNE RESULT] Controls Reset to Defaults\n")
            elif 'key' in query and 'val' in query:
                key = query['key'][0]
                val = float(query['val'][0])
                if key == 'red_gain': g_red_gain = val
                elif key == 'green_gain': g_green_gain = val
                elif key == 'blue_gain': g_blue_gain = val
                elif key == 'defog': g_defog = int(val)
                elif key == 'sharpness': g_sharpness = int(val)
                elif key == 'brightness': g_brightness = float(val)
                elif key == 'contrast': g_contrast = float(val)
                print(f"\n[TUNE UPDATE SUCCESS] Slider Change: {key} -> {val:.2f}\n")
                sys.stdout.flush()

            resp_data = json.dumps({
                "status": "ok",
                "r": g_red_gain, "g": g_green_gain, "b": g_blue_gain,
                "defog": g_defog, "sharpness": g_sharpness, "brightness": g_brightness, "contrast": g_contrast
            }).encode('utf-8')

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(resp_data)))
            self.end_headers()
            self.wfile.write(resp_data)

        else:
            self.send_response(404)
            self.end_headers()

def camera_capture_thread():
    global g_latest_raw_frame, g_running

    pipeline = "libcamerasrc ! video/x-raw, width=1912, height=1080 ! videoconvert ! video/x-raw, format=BGR ! appsink drop=true"
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

    if not cap.isOpened():
        print("[Camera WARNING] Falling back to default pipeline...")
        pipeline_fallback = "libcamerasrc ! videoconvert ! video/x-raw, format=BGR ! appsink drop=true"
        cap = cv2.VideoCapture(pipeline_fallback, cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            print("[Camera ERROR] Could not open MIPI-CSI2 camera pipeline.")
            g_running = False
            return

    print("[Camera] Native MIPI-CSI2 Pipeline Active (Auto-Scaling to True 1920x1080 Full HD)!")

    while g_running:
        ret, frame = cap.read()
        if ret:
            if frame.shape[1] != TARGET_WIDTH or frame.shape[0] != TARGET_HEIGHT:
                frame = cv2.resize(frame, (TARGET_WIDTH, TARGET_HEIGHT))

            with g_lock:
                g_latest_raw_frame = frame.copy()
        time.sleep(0.01)

    cap.release()

def detection_inference_thread():
    global g_latest_annotated_jpeg, g_latest_metrics, g_running
    global g_red_gain, g_green_gain, g_blue_gain, g_defog, g_sharpness, g_brightness, g_contrast

    print("[EIM Engine] Launching working .eim model:", EIM_FILE)
    runner = ImpulseRunner(EIM_FILE)
    try:
        model_info = runner.init()
        model_params = model_info.get("model_parameters", {})
        input_w = model_params.get("image_input_width", 640)
        input_h = model_params.get("image_input_height", 640)

        print(f"[EIM Engine] Loaded Project: {model_info.get('project', {}).get('name')}")
        print(f"[EIM Engine] Target Model Resolution: {input_w}x{input_h}")
        print(f"[EIM Engine] Control Panel ACTIVE!")

        frame_count = 0

        while g_running:
            frame = None
            with g_lock:
                if g_latest_raw_frame is not None:
                    frame = g_latest_raw_frame.copy()

            if frame is None:
                time.sleep(0.05)
                continue

            frame_count += 1
            t_start = time.time()

            h_orig, w_orig = frame.shape[:2]

            # Fast 640x640 Pre-Resize for Sub-Second Ultra-Fast Latency
            frame_640 = cv2.resize(frame, (input_w, input_h))

            # Atomic Snapshot of Tuning Parameters
            r_g, g_g, b_g = g_red_gain, g_green_gain, g_blue_gain
            defog, sharp, bright, contrast = g_defog, g_sharpness, g_brightness, g_contrast

            # 1. Apply User Tuned Dehaze/Defog, RGB Gains, Focus/Sharpness, Brightness & Contrast on 640x640 Frame
            tuned_bgr = apply_user_image_tune(frame_640, r_g, g_g, b_g, defog, sharp, bright, contrast)

            # 2. Convert to RGB for Model Input
            img_rgb = cv2.cvtColor(tuned_bgr, cv2.COLOR_BGR2RGB)
            img_u32 = img_rgb.astype(np.uint32)
            packed_features = ((img_u32[:, :, 0] << 16) | (img_u32[:, :, 1] << 8) | img_u32[:, :, 2]).astype(np.float32).reshape(-1)

            res = runner.classify(packed_features)
            t_duration_ms = (time.time() - t_start) * 1000.0

            boxes = []
            max_score = 0.0

            # Scale Display Frame back to Full 1920x1080 Resolution
            annotated_frame = cv2.resize(tuned_bgr, (w_orig, h_orig))
            scale_x = w_orig / float(input_w)
            scale_y = h_orig / float(input_h)

            if "result" in res and "bounding_boxes" in res["result"]:
                for bb in res["result"]["bounding_boxes"]:
                    score = float(bb.get("value", 0.0))
                    label = bb.get("label", "object")

                    if score > max_score:
                        max_score = score

                    if score >= CONFIDENCE_THRESHOLD:
                        x_m, y_m, w_m, h_m = int(bb.get("x", 0)), int(bb.get("y", 0)), int(bb.get("width", 0)), int(bb.get("height", 0))
                        
                        x = int(x_m * scale_x)
                        y = int(y_m * scale_y)
                        w = int(w_m * scale_x)
                        h = int(h_m * scale_y)

                        boxes.append({
                            "label": label,
                            "confidence": score,
                            "x": x, "y": y, "w": w, "h": h
                        })

                        cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), (255, 190, 0), 3)
                        label_str = f"{label}: {score:.2f} ({score*100:.1f}%)"
                        cv2.rectangle(annotated_frame, (x, max(y - 28, 0)), (x + len(label_str)*11, max(y, 28)), (255, 190, 0), -1)
                        cv2.putText(annotated_frame, label_str, (x + 4, max(y - 7, 20)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2, cv2.LINE_AA)

            # SAVE FULL HD FRAME PHOTO TO DISK FOR EVERY SYNC FRAME
            frame_filename = os.path.join(SAVE_DIR, f"sync_frame_{frame_count:04d}.jpg")
            latest_filename = os.path.join(SAVE_DIR, "latest_frame.jpg")
            
            cv2.imwrite(frame_filename, annotated_frame)
            cv2.imwrite(latest_filename, annotated_frame)

            ret_jpg, jpeg_buf = cv2.imencode('.jpg', annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            
            if ret_jpg:
                with g_lock:
                    g_latest_annotated_jpeg = jpeg_buf.tobytes()
                    g_latest_metrics = {
                        "boxes": boxes,
                        "max_score": float(max_score),
                        "time_ms": float(t_duration_ms),
                        "frame_count": int(frame_count)
                    }

            print(f"[Full HD SYNC FRAME #{frame_count}] Res: {w_orig}x{h_orig} | Latency: {t_duration_ms:.1f} ms | Max Score: {max_score:.4f} (Defog:{defog} Sharp:{sharp} R:{r_g:.2f} G:{g_g:.2f} B:{b_g:.2f})")
            if boxes:
                for idx, b in enumerate(boxes):
                    print(f"  ├─ [{idx+1}] {b['label']:<12} | Conf: {b['confidence']:.4f} ({b['confidence']*100:.1f}%) | Pos: ({b['x']}, {b['y']}, {b['w']}, {b['h']})")
            sys.stdout.flush()

    finally:
        runner.stop()

def main():
    if not os.path.exists(EIM_FILE):
        print(f"[ERROR] {EIM_FILE} not found!")
        sys.exit(1)

    os.chmod(EIM_FILE, 0o755)

    print("==================================================")
    print("  Arduino UNO Q 1920x1080 MIPI Camera Server (server.py)")
    print(f"  Target EIM: {EIM_FILE}")
    print(f"  True Scaled Output: {TARGET_WIDTH}x{TARGET_HEIGHT} Full HD")
    print(f"  Saved Frames Dir: {SAVE_DIR}")
    print("==================================================")

    # Start Multithreaded Non-blocking Web Server Thread
    threading.Thread(target=lambda: ThreadedHTTPServer(('0.0.0.0', 7000), WebServerHandler).serve_forever(), daemon=True).start()
    print("WebUI running at: http://localhost:7000")

    # Start Independent Camera Thread
    threading.Thread(target=camera_capture_thread, daemon=True).start()

    # Start Independent Inference Loop Thread
    detection_inference_thread()

if __name__ == "__main__":
    main()
