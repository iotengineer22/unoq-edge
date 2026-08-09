---

# Arduino UNO Q - IMX219 Camera Setup & Kernel Configuration

This repository provides setup scripts and device tree configurations for operating the IMX219 camera module on the Arduino UNO Q.

> **Note & Credits:**
> This project builds upon and references the device tree work from [RevLmt/camboard-uno-q](https://github.com/RevLmt/camboard-uno-q).

---

## 📋 Overview

Using the IMX219 camera module on newer Linux kernels (e.g., Kernel 7.0.0) may result in device tree dependency errors (`Fixed dependency cycle`). This repository details the workflow to:

1. Compile and apply the custom Device Tree Overlay for power management fixes.
2. Roll back `systemd-boot` to the stable **Kernel 6.16.7**.
3. Install `libcamera` dependencies and verify offscreen camera streaming.

---

## 🛠️ Quick Start

### 1. Compile & Apply Device Tree

Navigate to the device tree directory and run the automated setup script:

```bash
cd ArduinoApps/
cd camboard-uno-q-test/software/device_trees/
sudo ./setup_device.sh

```

#### What `setup_device.sh` performs:

```bash
#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Change directory to where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Compile DTS files to DTB/DTBO
dtc -@ -I dts -O dtb -o unoq-imx219-powerfix.dtbo unoq-imx219-powerfix.dts
dtc -@ -I dts -O dtb -o qrb2210-arduino-imola-camera-rpiv2.dtb qrb2210-arduino-imola-camera-rpiv2.dts

# 2. Apply device tree overlay
fdtoverlay -i qrb2210-arduino-imola-camera-rpiv2.dtb unoq-imx219-powerfix.dtbo -o qrb2210-arduino-imola-camera-rpiv2-r1b.dtb

# 3. Create destination directory and copy output file
mkdir -p /boot/efi/dtb/r1b/
cp qrb2210-arduino-imola-camera-rpiv2-r1b.dtb /boot/efi/dtb/r1b/

echo "Setup completed successfully!"

```

---

### 2. Bootloader Configuration (Kernel Rollback)

Check your current kernel and update systemd-boot configuration to target Kernel **6.16.7**:

```bash
# Check current active kernel
uname -r

# Edit the bootloader entry
sudo nano /boot/efi/loader/entries/3e660e15577e4d88ad85a3673a183368-6.16.7-g0dd6551ae96b.conf

# Edit the default loader configuration
sudo nano /boot/efi/loader/loader.conf

```

In `/boot/efi/loader/loader.conf`, set the default boot entry to Kernel 6.16.7:

```ini
#timeout 3
#console-mode keep
#default 3e660e15577e4d88ad85a3673a183368-*
default 3e660e15577e4d88ad85a3673a183368-6.16.7-g0dd6551ae96b.conf

```

Reboot the system to boot into Kernel 6.16.7:

```bash
sudo reboot

```

---

### 3. Install Camera Tools

After rebooting, confirm the active kernel version and install the required tools:

```bash
# Verify kernel version
uname -r

# Update package repository and install libcamera tools
sudo apt update
sudo apt install libcamera-tools gstreamer1.0-libcamera

```

---

### 4. Verify Camera Stream

Test offscreen frame processing via `qcam`:

```bash
QT_QPA_PLATFORM=offscreen qcam

```

### 5. CLI Photo Capture Commands (MIPI-CSI2 Camera via GStreamer)
You can also capture a single, lightweight JPEG photo directly from the UNO Q Linux terminal (SSH) using the following `gst-launch-1.0` commands:

* **1920x1080 (Full HD) Photo Capture (Recommended)**:
  ```bash
  sudo timeout 3 gst-launch-1.0 libcamerasrc ! videoconvert ! videoscale ! video/x-raw,width=1920,height=1080 ! jpegenc quality=85 ! multifilesink location=photo_1080p.jpg max-files=1
  ```
  > **Note**: Runs for 3 seconds allowing auto-exposure to adjust, writes a crisp 1080p JPEG (`photo_1080p.jpg`, ~150KB–250KB), and automatically exits back to the shell prompt without needing `Ctrl+C`.

* **640x360 (Ultra-Lightweight) Photo Capture**:
  ```bash
  sudo timeout 3 gst-launch-1.0 libcamerasrc ! videoconvert ! videoscale ! video/x-raw,width=640,height=360 ! jpegenc quality=80 ! multifilesink location=light_photo.jpg max-files=1
  ```
  > **Note**: Saves a tiny 640x360 JPEG (`light_photo.jpg`, ~40KB–60KB) that can be downloaded and opened instantly.

---

## 🔗 References

* [RevLmt/camboard-uno-q](https://github.com/RevLmt/camboard-uno-q) - Original reference implementation and device tree sources.