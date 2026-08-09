# UNO Q High-FPS MIPI-CSI2 Camera Streamer & Frame Saver

A standalone, zero-dependency Python web application for the **Arduino® UNO Q** (Qualcomm Linux) that streams live video from a MIPI-CSI2 camera (IMX219) at high frame rates (**20–30+ FPS**) and allows one-click continuous frame saving with millisecond precision to local storage via an intuitive Web UI.

![UNO Q Camera Streamer UI](assets/docs_assets/video-object-detection.png)

---

## Key Features

- **🚀 High-FPS Streaming (~20–30+ FPS)**  
  Leverages Qualcomm Linux host GStreamer (`libcamerasrc`) with hardware-level sensor binning (`1280x720`) and fast IDCT JPEG encoding to minimize CPU debayering latency.
- **⚡ Zero Third-Party Python Dependencies**  
  Built entirely on Python 3's standard library (`http.server`, `threading`, `json`, `subprocess`). No `pip install` or external frameworks (FastAPI/Flask/uvicorn) required.
- **💾 Millisecond-Precision Continuous Frame Saver**  
  Save incoming live camera frames directly to local storage (`output_images/frame_YYYYMMDD_HHMMSS_ffffff.jpg`) at full speed with a single click.
- **🎨 Premium Dark Glassmorphism Web UI**  
  Features a modern, responsive web interface on port `7000` with live FPS overlays, status indicators, and real-time control buttons.

---

## Hardware & Software Requirements

### Hardware
- [Arduino® UNO Q Board](https://store.arduino.cc/products/uno-q) (Qualcomm Snapdragon / Linux)
- MIPI-CSI2 Camera Module (e.g., Raspberry Pi Camera v2 / Sony IMX219)
- Power supply (5 V, 3 A)
- Personal Computer / Smartphone on the same network

### Software
- Linux OS (Qualcomm CamSS kernel driver)
- Python 3.8+ (Standard installation)
- GStreamer 1.0 (`gstreamer1.0-tools`, `gstreamer1.0-plugins-good`, `libcamerasrc`)

---

## Quick Start & Usage

### 1. Stop any running App Lab instances
If Arduino App Lab is currently running an application using the camera, stop it first by clicking **"Stop App"** in App Lab or terminating background camera processes:

```bash
pkill -f python3
pkill -f gst-launch-1.0
```

### 2. Launch the Standalone Server
Run the single `server.py` script from the terminal:

```bash
python3 server.py
```

### 3. Open the Web Interface
Open your web browser (Chrome, Edge, Safari, Firefox) and navigate to:

```text
http://localhost:7000
```
*or access remotely on your network via:*
```text
http://<YOUR-BOARD-IP>:7000
```

---

## Web UI Controls

- **Live Video Feed**: Displays the real-time 1280x720 stream from the MIPI-CSI2 camera.
- **Live FPS & Resolution Badge**: Displays real-time frame rates (~20–30 FPS) and resolution overlays in the top-left corner.
- **▶ Start Frame Saving**: Begins continuously saving every incoming frame into the `output_images/` directory with a microsecond-precision timestamp.
- **■ Stop Saving**: Pauses frame saving immediately.

---

## API Endpoints Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Serves the standalone HTML5 Glassmorphism Web UI |
| `/video_feed` | `GET` | MJPEG live video stream (`multipart/x-mixed-replace`) |
| `/api/status` | `GET` | Returns JSON status (`fps`, `resolution`, `is_saving`, `save_count`) |
| `/api/start_save` | `POST` | Enables background frame saving to `output_images/` |
| `/api/stop_save` | `POST` | Disables background frame saving |

---

## Command Line Single Photo Capture (GStreamer CLI)

You can also capture standalone single photos directly from the terminal without starting the web server:

### Full HD (1920x1080) Photo Capture:
```bash
sudo timeout 3 gst-launch-1.0 libcamerasrc ! videoconvert ! videoscale ! video/x-raw,width=1920,height=1080 ! jpegenc quality=85 ! multifilesink location=photo_1080p.jpg max-files=1
```

### Lightweight (640x360) Quick Photo Capture:
```bash
sudo timeout 3 gst-launch-1.0 libcamerasrc ! videoconvert ! videoscale ! video/x-raw,width=640,height=360 ! jpegenc quality=80 ! multifilesink location=light_photo.jpg max-files=1
```

---

## Project Structure

```text
.
├── server.py             # Main standalone HTTP server & camera engine
├── output_images/        # Storage folder for captured frames (Auto-created)
└── README.md             # Project documentation
```

---

## License

This project is open-source and released under the MIT License.
