# Hardware Design & BOM (board)

This directory contains the Bill of Materials (BOM) and connection references for **The Hybrid Guard** multi-camera quality assurance system.

---

## 1. Contents

*   **[BOMlist.xlsx](file:///C:/Users/ioten/zephyrproject/test/unoq-invent-up/board/BOMlist.xlsx)**: A styled Excel spreadsheet listing the exact components, quantities, connection interfaces, and system roles for the 8 core items in the inspection pipeline.

---

## 2. Component Design & References

### 📸 Custom MIPI-CSI2 Add-on Board
Connecting a standard high-resolution camera like the Raspberry Pi Camera v2 (Sony IMX219) to the Arduino® UNO Q requires a hardware interface adapter board to match the MIPI CSI-2 pinout of the Qualcomm host CPU.

*   **Design Reference**: The custom add-on board used in this project is based on and references the open-source design from the **camboard-uno-q** repository:
    👉 **[camboard-uno-q Repository (GitHub)](https://github.com/RevLmt/camboard-uno-q)**
*   **Purpose**: Routes the camera lanes to the flat-flex connector of the UNO Q, supplying stable power and signal integrity.

---

## 3. Peripheral Connections

### 🔌 Arducam Mega 3MP SPI Camera
The SPI macro camera is connected directly to the JSPI/ICSP header pins on the STM32 MCU side of the UNO Q:

| Signal | Component Pin | Arduino Uno Q Pin | Connection Port |
| :--- | :--- | :--- | :--- |
| **VCC** | Power | **5V** (or 3.3V) | Power Supply |
| **GND** | Ground | **GND** | Ground Reference |
| **MOSI** | SPI Data Input | **MOSI (JSPI)** | `PC3` (SPI2_MOSI on ICSP) |
| **MISO** | SPI Data Output | **MISO (JSPI)** | `PC2` (SPI2_MISO on ICSP) |
| **SCK** | SPI Serial Clock | **SCK (JSPI)** | `PD1` (SPI2_SCK on ICSP) |
| **CS** | Chip Select | **D10** | `PB9` (GPIO active-low) |

### 🚨 PIR Motion Sensor
The conveyor line trigger sensor is configured to wake the MCU from deep sleep and initiate camera capture:

*   **VCC** ➔ **3.3V** or **5V**
*   **GND** ➔ **GND**
*   **OUT** ➔ **D7** (`PB2` Interrupt Input on the STM32 MCU)
