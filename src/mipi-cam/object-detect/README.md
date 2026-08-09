# 🚀 Edge Impulse Real-Time MIPI-CSI2 Object Detector for Arduino UNO Q

A high-performance, real-time object detection and live image calibration web server for **Arduino UNO Q** (Qualcomm Linux / Debian 12) utilizing a **MIPI-CSI2 (`imx219`) Camera** and an **Edge Impulse C++ `.eim` Model**.

Featuring a built-in interactive WebUI, this server allows you to monitor live detections, inspect model metrics, and tune camera calibration controls (RGB Gains, Dehaze/Defog, Sharpness/Focus, Brightness, Contrast) in real-time.

---

## ✨ Features

- **High-Resolution Capture**: Seamlessly handles native 1912x1080 MIPI-CSI2 sensor streams and scales them to True **1920x1080 Full HD**.
- **Real-Time Edge Impulse Inference**: Low-latency C++ `.eim` model execution via Edge Impulse Linux Python SDK.
- **🎛️ Interactive WebUI Calibration Panel**:
  - 🔴🟢🔵 **RGB Gain Sliders**: Fine-tune Color Balance and completely eliminate MIPI camera Green Tint.
  - ☁️ **Defog / Dehaze Filter**: Instant CLAHE-based anti-haze filter for foggy or cloudy camera lenses.
  - 🔍 **Focus / Sharpness Filter**: Edge-enhancement filter to crisp up soft or out-of-focus optics.
  - ☀️ **Brightness & 🌗 Contrast Sliders**: Real-time exposure adjustment.
- **⚡ Non-Blocking Multithreaded Web Server**: Built with `ThreadedHTTPServer` on Port `7000`, ensuring live video streaming never blocks control panel API requests.
- **💾 Automatic Frame Saver**: Saves every processed frame with overlay boxes into `saved_frames/`.
- **📊 Real-Time Metrics**: Displays Max Confidence score, Object Counts, Processed Frame Numbers, and Terminal Latency (in ms).

---

## 💡 Example Console Output

Below is an actual runtime log from the Arduino UNO Q detecting multiple IC components in real-time at 1920x1080 Full HD resolution:

```text
arduino@misoji:~/test/mipi-object-detect$ python3 server.py 
==================================================
  Arduino UNO Q 1920x1080 MIPI Camera Server (server.py)
  Target EIM: /home/arduino/test/mipi-object-detect/camera-test-linux-aarch64-v10-impulse-#1.eim
  True Scaled Output: 1920x1080 Full HD
  Saved Frames Dir: /home/arduino/test/mipi-object-detect/saved_frames
==================================================
WebUI running at: http://localhost:7000
[EIM Engine] Launching working .eim model: /home/arduino/test/mipi-object-detect/camera-test-linux-aarch64-v10-impulse-#1.eim
[EIM Engine] Loaded Project: camera-test
[EIM Engine] Target Model Resolution: 640x640
[EIM Engine] Control Panel ACTIVE!
[0:02:26.487558877] [1536]  INFO Camera camera_manager.cpp:327 libcamera v0.4.0
[0:02:26.521161536] [1548]  WARN CameraSensor camera_sensor_legacy.cpp:354 'imx219 0-0010': Recommended V4L2 control 0x009a0922 not supported
[0:02:26.521251049] [1548]  WARN CameraSensor camera_sensor_legacy.cpp:426 'imx219 0-0010': The sensor kernel driver needs to be fixed
[0:02:26.521269274] [1548]  WARN CameraSensor camera_sensor_legacy.cpp:428 'imx219 0-0010': See Documentation/sensor_driver_requirements.rst in the libcamera sources for more information
[0:02:26.522098320] [1548]  WARN CameraSensor camera_sensor_legacy.cpp:594 'imx219 0-0010': Failed to retrieve the camera location
[0:02:26.522208297] [1548]  WARN CameraSensor camera_sensor_legacy.cpp:616 'imx219 0-0010': Rotation control not available, default to 0 degrees
[0:02:26.541309406] [1548]  WARN IPAProxy ipa_proxy.cpp:160 Configuration file 'imx219.yaml' not found for IPA module 'simple', falling back to 'uncalibrated.yaml'
[0:02:26.554302729] [1557]  INFO Camera camera.cpp:1202 configuring streams: (0) 1912x1080-ABGR8888
[0:02:26.564193994] [1548]  INFO IPASoft soft_simple.cpp:251 IPASoft: Exposure 4-1759, gain 1-10.6667 (0.0966667)
[ WARN:0@2.488] global cap_gstreamer.cpp:1754 open OpenCV | GStreamer warning: unable to query duration of stream
[ WARN:0@2.489] global cap_gstreamer.cpp:1777 open OpenCV | GStreamer warning: Cannot query video position: status=0, value=-1, duration=-1
[Camera] Native MIPI-CSI2 Pipeline Active (Auto-Scaling to True 1920x1080 Full HD)!
[0:02:29.873605464] [1559]  INFO Debayer debayer_cpu.cpp:788 Processed 30 frames in 1548416us, 51613 us/frame
[Full HD SYNC FRAME #1] Res: 1920x1080 | Latency: 8502.6 ms | Max Score: 0.0000 (Defog:0 Sharp:0 R:1.00 G:1.00 B:1.00)
[Full HD SYNC FRAME #2] Res: 1920x1080 | Latency: 8073.2 ms | Max Score: 0.7041 (Defog:0 Sharp:0 R:1.00 G:1.00 B:1.00)
  ├─ [1] IC           | Conf: 0.7041 (70.4%) | Pos: (273, 420, 171, 81)
  ├─ [2] IC           | Conf: 0.6666 (66.7%) | Pos: (459, 420, 186, 81)
  ├─ [3] IC           | Conf: 0.5019 (50.2%) | Pos: (1149, 403, 102, 57)
[Full HD SYNC FRAME #3] Res: 1920x1080 | Latency: 7887.7 ms | Max Score: 0.7416 (Defog:0 Sharp:0 R:1.00 G:1.00 B:1.00)
  ├─ [1] IC           | Conf: 0.7416 (74.2%) | Pos: (285, 420, 159, 81)
  ├─ [2] IC           | Conf: 0.6292 (62.9%) | Pos: (459, 420, 159, 81)
```

---

## 🛠️ Prerequisites & Installation

### 1. System Dependencies (Qualcomm Linux / Debian)

Install the required GStreamer and OpenCV system libraries:

```bash
sudo apt update
sudo apt install -y \
    python3-opencv \
    python3-numpy \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    libgstreamer1.0-dev \
    libcamera-dev
```

### 2. Edge Impulse Linux SDK Installation

Install the `edge_impulse_linux` Python library:

```bash
# For PEP 668 Externally Managed Environments (Debian 12 / Python 3.13)
pip3 install edge_impulse_linux --break-system-packages

# Or using virtualenv (recommended)
python3 -m venv venv
source venv/bin/activate
pip install edge_impulse_linux opencv-python numpy
```

---

## 📦 Edge Impulse Model Setup

1. **Export `.eim` Model**:
   - Go to your **Edge Impulse Studio** project.
   - Navigate to **Deployment** -> Select **Linux (aarch64)**.
   - Build and download the `.eim` binary file (e.g., `camera-test-linux-aarch64-v10-impulse-#1.eim`).

2. **Place Model in Project Root**:
   Copy the `.eim` file into your project folder:
   ```bash
   cp /path/to/your-model.eim ./camera-test-linux-aarch64-v10-impulse-#1.eim
   ```

3. **Grant Execution Permissions**:
   ```bash
   chmod +x camera-test-linux-aarch64-v10-impulse-#1.eim
   ```

---

## 🚀 Usage

### 1. Start the Detection Server

Run the main server script:

```bash
python3 server.py
```

### 2. Access the WebUI

Open your browser and navigate to:
```text
http://<your-arduino-uno-q-ip>:7000
```
*(Or `http://localhost:7000` if viewing locally)*

---

## 📸 WebUI Calibration Guide

| Control | Range | Description |
| :--- | :--- | :--- |
| ☁️ **Defog / Dehaze** | `0` - `10` | Removes white haze/fog from cloudy lenses using adaptive CLAHE contrast enhancement. |
| 🔍 **Focus / Sharpness** | `0` - `10` | Enhances object edges and sharpens soft focus. |
| 🔴 **Red Gain** | `0.50` - `2.50` | Adjusts Red channel multiplier to fix color balance. |
| 🟢 **Green Gain** | `0.50` - `2.50` | Adjusts Green channel gain to eliminate MIPI green tint. |
| 🔵 **Blue Gain** | `0.50` - `2.50` | Adjusts Blue channel multiplier. |
| ☀️ **Brightness** | `-100` - `100` | Adjusts image brightness offset. |
| 🌗 **Contrast** | `0.50` - `2.00` | Multiplies image contrast. |

---

## 📁 Project Structure

```text
mipi-object-detect/
├── server.py                                    # Main Multithreaded Full HD Object Detection & Calibration Server
├── camera-test-linux-aarch64-v10-impulse-#1.eim # Compiled Edge Impulse C++ Model
├── saved_frames/                                # Directory auto-created for saved detected frames
└── README.md                                    # Project documentation
```

---

## ❓ Troubleshooting

- **Green Tint Issue**:
  MIPI-CSI2 sensors (`imx219`) on Linux may display a strong green tint due to uncalibrated white balance. Use the 🟢 **Green Gain** and 🔴 **Red Gain** sliders on the WebUI to instantly balance colors.
- **Cloudy / Hazy Image**:
  If the lens appears foggy or washed out, increase the ☁️ **Defog / Dehaze** slider to `3` - `6` to restore crisp contrast.
- **Port 7000 in Use**:
  If Port 7000 is occupied, update the port number in `server.py` (`ThreadedHTTPServer(('0.0.0.0', 7000), ...)`).

---

## 📜 License

Distributed under the MIT License. Feel free to modify and adapt for your own Arduino UNO Q vision projects!
