import os
import re
import subprocess
import sys
import time
from datetime import datetime

# Configure settings
INTERVAL_SEC = 3.0    # Time interval between captures (in seconds)
SAVE_DIR = "./dataset" # Target directory to store images

# ADB and Map configurations (same as view_image.py)
user_profile = os.environ.get("USERPROFILE", "C:\\Users\\default")
ADB_PATH = os.path.join(
    user_profile, 
    "AppData", "Local", "Arduino15", "packages", "arduino", "tools", "adb", "32.0.0", "adb.exe"
)
MAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "zephyr", "zephyr.map")

RAW_FILE_ON_BOARD = "/tmp/captured.raw"
RAW_FILE_LOCAL = "./captured_tmp.raw"
BUFFER_SIZE = 18432  # 96 * 96 * 2 bytes

def get_symbol_address(symbol_name):
    if not os.path.exists(MAP_FILE):
        print(f"Error: Map file not found at {MAP_FILE}. Please build the project first.")
        sys.exit(1)
        
    with open(MAP_FILE, "r") as f:
        content = f.read()
        
    match = re.search(r"(0x[0-9a-fA-F]+)\s+" + re.escape(symbol_name) + r"\b", content)
    if not match:
        print(f"Error: Could not find '{symbol_name}' in map file.")
        sys.exit(1)
        
    return match.group(1)

def execute_cmd(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    return result.returncode == 0

def convert_rgb565_to_png(raw_path, png_path):
    from PIL import Image
    
    with open(raw_path, "rb") as f:
        raw_data = f.read()
        
    if len(raw_data) < BUFFER_SIZE:
        print(f"Warning: Raw file size ({len(raw_data)}) is too small. Skipping conversion.")
        return False
        
    width = 96
    height = 96
    
    # Decoded using Big Endian RGB565 (confirmed matching captured_be.png)
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    
    for y in range(height):
        for x in range(width):
            idx = (y * width + x) * 2
            b1 = raw_data[idx]
            b2 = raw_data[idx + 1]
            
            val = (b1 << 8) | b2
            r = ((val >> 11) & 0x1F) << 3
            g = ((val >> 5) & 0x3F) << 2
            b = (val & 0x1F) << 3
            pixels[x, y] = (r, g, b)
            
    img.save(png_path)
    return True

def main():
    # Make sure Pillow is installed
    try:
        from PIL import Image
    except ImportError:
        print("Installing Pillow dependency...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])

    # Create dataset directory
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
        print(f"Created dataset directory at: {os.path.abspath(SAVE_DIR)}")

    # Resolve image_buffer RAM address
    addr = get_symbol_address("image_buffer")
    print(f"Resolved 'image_buffer' RAM address: {addr}")
    print(f"Starting automatic dataset capture every {INTERVAL_SEC} seconds...")
    print("Move your target objects in front of the camera to collect diverse training images.")
    print("Press Ctrl+C to stop collecting.\n")

    counter = 1
    openocd_cmd = (
        f"init; halt; "
        f"dump_image {RAW_FILE_ON_BOARD} {addr} {BUFFER_SIZE}; "
        f"resume; shutdown"
    )
    dump_cmd = [
        ADB_PATH, "shell",
        f"/opt/openocd/bin/openocd -d2 -s /opt/openocd -f openocd_gpiod.cfg -c \"{openocd_cmd}\""
    ]
    pull_cmd = [ADB_PATH, "pull", RAW_FILE_ON_BOARD, RAW_FILE_LOCAL]

    try:
        while True:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            png_filename = f"img_{timestamp}_{counter:04d}.png"
            png_path = os.path.join(SAVE_DIR, png_filename)

            # 1. Dump image from STM32 RAM to board Linux /tmp
            if not execute_cmd(dump_cmd):
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: Failed to dump RAM from STM32.")
                time.sleep(INTERVAL_SEC)
                continue

            # 2. Pull raw image to Host PC
            if execute_cmd(pull_cmd):
                # 3. Convert raw RGB565 to standard PNG
                if convert_rgb565_to_png(RAW_FILE_LOCAL, png_path):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved: {png_path}")
                    counter += 1
                
                # Cleanup local temp raw file
                if os.path.exists(RAW_FILE_LOCAL):
                    os.remove(RAW_FILE_LOCAL)
            
            # Cleanup board temporary file
            execute_cmd([ADB_PATH, "shell", f"rm {RAW_FILE_ON_BOARD}"])

            time.sleep(INTERVAL_SEC)

    except KeyboardInterrupt:
        print("\nDataset collection stopped by user.")
        print(f"Successfully collected {counter - 1} images in '{SAVE_DIR}' folder.")

if __name__ == "__main__":
    main()
