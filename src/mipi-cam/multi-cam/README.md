# UNO Q Triple Camera Streamer (`multi-cam.py`)

A high-performance simultaneous **3-camera live streaming and frame recording web application** designed for the **Arduino UNO Q** (ARM64 Linux + STM32 Zephyr RTOS).

---

## 📸 Triple Camera Specifications

| Camera Interface | Resolution | Capture Engine | Performance / Use Case |
| :--- | :--- | :--- | :--- |
| **1. MIPI-CSI2 Camera** | **1280x720 (HD)** | GStreamer `libcamerasrc` Direct Pipeline | **30 FPS Real-time Stream (Featured Large View)** |
| **2. USB Web Camera** | **Dynamic (640x360 ~ HD)** | V4L2 `cv2.VideoCapture` Auto-Detect | **30 FPS Real-time Stream (Featured Large View)** |
| **3. SPI Camera** | **320x240 (RGB565)** | SWD 150KB High-Speed RAM Dump | **15s Polling Snapshot (Compact Sub-View)** |

---

## ⚡ Core Features & Optimizations

1. **Auto Pixel Roll Alignment (`Auto Seam Stitching`)**
   - Automatically detects the vertical frame seam and stitches split left/right screen artifacts seamlessly into a single pristine image.
2. **Black Horizontal Line Inpainting Filter**
   - Detects black stripe noise artifacts (zero-brightness lines caused by transfer timing jitter) and linearly interpolates them using adjacent rows to deliver crystal-clear images.
3. **Optimized Responsive WebUI (Port 7000)**
   - Tuned 3-column layout: MIPI (1280x720) and USB cameras are presented in prominent large cards (2.2 : 2.2 aspect ratio), while the SPI camera is neatly hosted in a compact side panel (1.2 aspect ratio).
4. **Synchronized Multi-Camera Frame Recording**
   - Clicking **"▶ Start Triple Frame Saving"** records synchronized time-stamped images from all 3 cameras into the `./output_images/` directory.

---

## 🚀 Quick Start Guide

Run the streamer from your Arduino UNO Q Linux terminal:

```bash
cd /home/arduino/test/multi-cam
python3 multi-cam.py
```

### 🌐 Accessing the WebUI
Open your web browser and navigate to:
- **`http://localhost:7000`** (Board Local)
- **`http://<Arduino_UNO_Q_IP>:7000`** (Network Access)

---

## 📁 Repository Structure

- **`multi-cam.py`**: Primary multi-camera streaming application server (MIPI @ 1280x720 HD).
- **`spi_camera.png`**: Latest processed PNG frame from the SPI camera.
- **`output_images/`**: Output directory for synchronized recorded frames.
- **`README-multi.md`**: Project documentation (English).
