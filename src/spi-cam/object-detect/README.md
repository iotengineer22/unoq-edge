# SPI Camera Connection Test for Arduino Uno Q and Arducam Mega 3MP

This is a simple Zephyr RTOS test application that verifies the SPI communication between the **Arduino Uno Q** development board (STM32U585) and the **Arducam Mega 3MP** SPI camera module.

## Features
- **Visual Status & Object Detection Indicator**: 
  - **At Bootup**:
    - 🟢 **Green LED** (`led3_green`) lights up if the camera is successfully initialized.
    - 🔴 **Red LED** (`led3_red`) lights up if the camera is not detected.
  - **During Runtime Object Detection (threshold >= 0.5)**:
    - 🔵 **Blue LED** (`led3_blue`) turns on when `"pico"` is detected.
    - 🟢 **Green LED** (`led3_green`) turns on when `"xiao"` is detected.
    - 🔴 **Red LED** (`led3_red`) turns on when `"nrf54l15"` is detected.
    - 🟡 **Yellow Color** (Red + Green) turns on when `"fpc"` is detected.
    - 📴 **All LEDs turn OFF** when no objects are detected (idle state).
- Uses the **JSPI / ICSP connector** pins for SPI communication instead of standard digital pin headers to avoid signal routing mismatches.

## Hardware Connections

Connect the Arducam Mega 3MP to the Arduino Uno Q as follows:

| Arducam Mega Pin | Arduino Uno Q Pin | Connection Type / Target Port |
| :--- | :--- | :--- |
| **VCC** | **5V** (or 3.3V) | Power |
| **GND** | **GND** | Ground |
| **MOSI** | **MOSI (JSPI)** | `PC3` (SPI2_MOSI on ICSP) |
| **MISO** | **MISO (JSPI)** | `PC2` (SPI2_MISO on ICSP) |
| **SCK** | **SCK (JSPI)** | `PD1` (SPI2_SCK on ICSP) |
| **CS** | **D10** | `PB9` (GPIO Control) |

*Note: Ensure MOSI and MISO are not crossed. Connect MOSI to MOSI, and MISO to MISO.*

## Prerequisites & Driver Fixes
During the development of this project, two bugs in the upstream Zephyr Arducam driver (`zephyr/drivers/video/video_arducam_mega.c`) were resolved:

### 1. Compilation Bug
The first parameter of `arducam_mega_write_reg_wait()` was incorrectly defined with a non-existent type `struct arducam_mega_bus`. This was corrected to use `struct spi_dt_spec`:

```diff
-static int arducam_mega_write_reg_wait(const struct arducam_mega_bus *bus, uint16_t reg,
+static int arducam_mega_write_reg_wait(const struct spi_dt_spec *bus, uint16_t reg,
 				       uint8_t value, uint32_t idle_timeout_ms)
```

### 2. Resolution Mapping Bug (Diagonal Stripe Noise Fix)
A logical bug (around line 848) caused resolution mismatches between the camera sensor output and the Zephyr video format dimensions, resulting in severe line noise. The original code mapped resolution using naive modulo arithmetic:

```diff
-	ret = arducam_mega_set_resolution(dev, i % SUPPORT_RESOLUTION_NUM);
```

This was corrected to map width and height explicitly to the camera's register presets (QVGA/VGA/QQVGA):

```diff
+	enum mega_resolution res;
+	if (fmt->width == 320 && fmt->height == 240) {
+		res = MEGA_RESOLUTION_QVGA;
+	} else if (fmt->width == 640 && fmt->height == 480) {
+		res = MEGA_RESOLUTION_VGA;
+	} else if (fmt->width == 96 && fmt->height == 96) {
+		res = MEGA_RESOLUTION_QQVGA;
+	} else {
+		res = i % SUPPORT_RESOLUTION_NUM;
+	}
+	ret = arducam_mega_set_resolution(dev, res);
```

## How to Build and Flash

Because the Arduino Uno Q has a dual-brain architecture (Qualcomm Linux + STM32U585), the standard `west flash` command is not directly integrated. You must build locally and flash using the board's internal OpenOCD via ADB.

### 1. Build the Project
Run the following command from the root of this project:
```bash
west build -b arduino_uno_q
```

### 2. Push the Binary to the Board via ADB
Push the compiled ELF file to the board's Linux environment:
```bash
adb push build/zephyr/zephyr.elf /tmp/zephyr.elf
```

### 3. Flash the STM32 Microcontroller
Trigger the flashing process using the board's internal OpenOCD instance:
```bash
adb shell "/opt/openocd/bin/openocd -d2 -s /opt/openocd -f openocd_gpiod.cfg -c 'reset_config srst_only srst_push_pull; init; reset; halt; flash write_image erase /tmp/zephyr.elf; reset; shutdown'"
```

Upon a successful flash, the board will reset, and the onboard LED will indicate the status (Green for Success, Red for Failure).

Once successfully initialized, the green LED will toggle every 3 seconds to indicate active frame capture.

## Verifying Captured Images

The application continuously captures frames in **320x240 QVGA (RGB565)** format every 3 seconds and copies the latest frame to a static RAM buffer.

You can automatically pull the raw memory buffer from the STM32 and convert it into a PNG image on your PC using the provided [view_image.py](./view_image.py) helper script.

### How to Retrieve and View the Photo:
1. Ensure the board is connected to your PC via USB.
2. Run the script on your host PC:
   ```bash
   python view_image.py
   ```
3. Open **`captured_be.png`** (Big Endian representation) in your project directory to see the camera's actual output.

The script automatically parses `zephyr.map` to find the exact RAM address of the image buffer, issues an OpenOCD dump command over ADB, pulls the raw binary, and decodes it.

## Edge Impulse Inference & SPI Performance Benchmarks

### 1. Edge Impulse Object Detection (FOMO)
The firmware integrates a C++ Edge Impulse **FOMO** object detection model designed for **96x96 grayscale** inputs:
* **Image Pipeline:** Captures a 320x320 square frame, resizes it to 96x96 target resolution in RAM using average pooling scaling to prevent aliasing, normalizes pixel outputs to `0.0 - 1.0` (with `0x00RRGGBB` packing), and feeds it to `run_classifier()`.
* **Inference Latency:** DSP (image processing): `13 ms`, Classification (model inference): `298 ms`.
* **BBox Overlay:** `view_image.py` automatically parses the model's bounding box output from `inference_log_buffer` and overlays the bounding boxes onto the saved image (`captured_with_bbox.png`).

### 2. SPI Clock Frequency Comparison (4MHz vs 8MHz)
To optimize data acquisition speed, the SPI clock frequency configured in `app.overlay` was profiled. Below is the measured time from camera capture triggers to full SPI transfer completion of a **320x240 RGB565 frame (153.6 KB)**:

| SPI Frequency | Raw Data Size | Measured Capture + Transfer Time | Speedup / Improvement |
| :--- | :--- | :--- | :--- |
| **4 MHz** | 153,600 Bytes | **`984 ms`** | Baseline |
| **8 MHz** | 153,600 Bytes | **`677 ms`** | **`-307 ms` (31.2% faster)** |

*Note: For 320x320 RGB565 frames (200 KB), the SPI transfer takes approximately **`860 ms`** at 8 MHz.*

## RAM & FLASH Memory Allocation Breakdown

To run the 320x320 resolution capture pipeline alongside the Edge Impulse object detection model, the microcontroller's RAM (768 KB) is tightly budgeted. Below is the memory allocation breakdown for the current stable build:

### 1. Overall Memory Usage
* **FLASH (ROM):** `135,608 Bytes` / `2 MB` (**6.47 %** used) — Houses program instructions and static neural network weights.
* **RAM (SRAM):** `672,688 Bytes` / `768 KB` (**85.54 %** used) — Houses execution state, variables, and frame buffers.

### 2. RAM Allocation Breakdown

| RAM Section | Allocated Capacity | % of Total RAM | Description / Purpose |
| :--- | :--- | :--- | :--- |
| **Video Buffer Pool** | `440,000 Bytes` | **55.95 %** | Double buffering (`CONFIG_VIDEO_BUFFER_POOL_NUM_MAX=2`) for 320x320 RGB565 frames (200 KB per frame) to enable concurrent camera capture and inference. |
| **TFLite Tensor Arena** | `185,075 Bytes` | **23.53 %** | Dynamic scratch memory allocated by the Edge Impulse C++ SDK to store intermediate feature maps during CNN execution. |
| **Main Thread Stack** | `32,768 Bytes` | **4.17 %** | Thread execution space (`CONFIG_MAIN_STACK_SIZE=32768`) to handle function calls and local variables safely. |
| **System Kernel & Data** | `14,845 Bytes` | **1.89 %** | Zephyr RTOS kernel overhead, GPIO/SPI driver state, and global BSS/DATA variables. |
| **Unused Free Memory** | **`113,744 Bytes` (111 KB)** | **14.46 %** | Safety margin left to prevent stack overflow and dynamic allocation runtime OOM crashes. |

*Note on Double Buffering (2 Frames):* Allocating two frames in the video buffer pool allows the camera to stream the next capture frame into Buffer A *concurrently* while the Edge Impulse model processes the current frame in Buffer B, eliminating CPU wait times and maximizing pipeline throughput.
