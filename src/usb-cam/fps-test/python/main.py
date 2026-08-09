# SPDX-FileCopyrightText: Copyright (C) Arduino s.r.l. and/or its affiliated companies
#
# SPDX-License-Identifier: MPL-2.0

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import Camera
from fastapi.responses import StreamingResponse
import time
import io
import os
from datetime import datetime

# Setup WebUI
ui = WebUI()

# Initialize saving state
is_saving = False

def toggle_saving(state: bool):
    global is_saving
    is_saving = state
    ui.send_message("save_status", message={"is_saving": is_saving})

ui.on_message("start_save", lambda sid, data: toggle_saving(True))
ui.on_message("stop_save", lambda sid, data: toggle_saving(False))

# Initialize Camera
camera = Camera()

# Setup image encoder
try:
    import cv2
    def encode_jpeg(frame):
        # Camera might return BGR (common for OpenCV based feeds in python) 
        # or RGB. If colors are swapped (blueish tint), we can convert it.
        ret, jpeg = cv2.imencode('.jpg', frame)
        if ret:
            return jpeg.tobytes()
        return None
except ImportError:
    try:
        from PIL import Image
        def encode_jpeg(frame):
            img = Image.fromarray(frame)
            buf = io.BytesIO()
            img.save(buf, format='JPEG')
            return buf.getvalue()
    except ImportError:
        def encode_jpeg(frame):
            return None

fps_start_time = None
frame_count = 0

def gen_frames():
    global fps_start_time, frame_count, is_saving
    
    save_dir = "output_images"
    if not os.path.exists(save_dir):
        try:
            os.makedirs(save_dir)
        except Exception as e:
            print(f"Error creating directory {save_dir}: {e}")
    
    while True:
        frame = None
        # Attempt to read frame using available methods
        if hasattr(camera, '_read_frame'):
            frame = camera._read_frame()
        elif hasattr(camera, 'read'):
            ret, frame = camera.read()
            if not ret:
                frame = None

        if frame is None:
            # Prevent high CPU usage when no frame is available
            time.sleep(0.01)
            continue
            
        jpeg_bytes = encode_jpeg(frame)
        if jpeg_bytes is None:
            time.sleep(0.01)
            continue

        # Save frame to file if saving is enabled
        if is_saving:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = os.path.join(save_dir, f"frame_{timestamp}.jpg")
            try:
                with open(filename, "wb") as f:
                    f.write(jpeg_bytes)
            except Exception as e:
                print(f"Error saving image {filename}: {e}")
            
        # FPS Calculation
        now = time.time()
        if fps_start_time is None:
            fps_start_time = now
        frame_count += 1
        
        elapsed = now - fps_start_time
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            height, width = frame.shape[:2]
            # Send current camera FPS and resolution to the WebUI
            ui.send_message("fps", message={
                "fps": round(fps, 1),
                "width": width,
                "height": height
            })
            frame_count = 0
            fps_start_time = now
            
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')

# Expose a custom GET route for video streaming
def video_feed():
    return StreamingResponse(gen_frames(), media_type='multipart/x-mixed-replace; boundary=frame')

ui.expose_api("GET", "/video_feed", video_feed)

App.run()

